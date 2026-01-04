#!/usr/bin/env python3
"""
Windows GUI程序：建立SSH隧道、启动Ollama服务、运行调研代码
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import time
import sys
import os
import json
import csv
import signal
import requests
import threading
import shutil
import tempfile
import subprocess
from pathlib import Path
from io import StringIO
from concurrent.futures import ThreadPoolExecutor, as_completed

# 尝试导入openai库（用于批处理功能）
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# 尝试导入paramiko（优先使用，Windows上最可靠）
USE_PARAMIKO = False
try:
    import paramiko
    USE_PARAMIKO = True
except ImportError:
    USE_PARAMIKO = False


# 默认模型列表
DEFAULT_MODELS = [
    "deepseek-r1",
    "deepseek-chat",
    "llama3",
    "llama3.1",
    "mistral",
    "qwen2.5",
    "gemma2",
    "phi3"
]

# 版本信息
CURRENT_VERSION = "0.1.0"  # 当前版本号
GITHUB_REPO_OWNER = "WindyJnsa"
GITHUB_REPO_NAME = "Papers_Research"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"

# 获取程序运行目录（支持打包后的exe）
def get_app_dir():
    """获取应用程序目录（支持打包后的exe）"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后的exe，使用exe所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境，使用脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))

# 获取用户数据目录（用于存储锁定状态等敏感文件）
def get_user_data_dir():
    """获取用户数据目录（隐藏目录，用户不容易找到）"""
    if sys.platform == 'win32':
        # Windows: 使用 AppData\Local
        appdata = os.getenv('LOCALAPPDATA')
        if appdata:
            user_dir = os.path.join(appdata, "PaperResearchTool")
        else:
            # 备用方案：使用用户目录
            user_dir = os.path.join(os.path.expanduser("~"), ".paper_research_tool")
    else:
        # Linux/Mac: 使用 ~/.config 或 ~/.local/share
        user_dir = os.path.join(os.path.expanduser("~"), ".paper_research_tool")
    
    # 确保目录存在
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

APP_DIR = get_app_dir()
USER_DATA_DIR = get_user_data_dir()

# 配置文件路径（在exe目录，方便用户查看和修改）
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
# 模型缓存文件路径（在exe目录）
MODELS_CACHE_FILE = os.path.join(APP_DIR, "models_cache.json")
# 锁定状态文件路径（在用户数据目录，隐藏，用户不容易找到）
LOCK_FILE = os.path.join(USER_DATA_DIR, ".lock")
# 解锁码（可以修改）
UNLOCK_CODE = "unlock_hzq"

# 用于线程安全的锁（用于日志输出和结果收集）
results_lock = threading.Lock()

# 全局配置（用于线程安全的配置访问）
_global_client_config = {}

# 全局变量：ollama 命令的完整路径（如果找到）
_ollama_path = None

def get_ollama_cmd():
    """获取 ollama 命令（直接使用指定的路径）"""
    global _ollama_path
    if _ollama_path:
        return _ollama_path
    # 如果没有设置，返回None，让调用者处理错误
    return None

def get_full_model_name(base_name, size=""):
    """获取完整的模型名称（如果指定了大小，则使用 model_name:size 格式）"""
    if size:
        return f"{base_name}:{size}"
    return base_name


class ResearchGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"论文调研工具 v{CURRENT_VERSION}")
        self.root.geometry("1400x800")
        self.root.minsize(1200, 700)
        # 窗口默认最大化
        self.root.state('zoomed')  # Windows上最大化窗口
        
        # 配置中文字体（使用微软雅黑，Windows上最美观的中文字体）
        self.chinese_font = "Microsoft YaHei"  # 微软雅黑
        # 如果系统没有微软雅黑，尝试其他中文字体
        try:
            import tkinter.font as tkfont
            available_fonts = tkfont.families()
            if self.chinese_font not in available_fonts:
                # 尝试其他中文字体
                for font_name in ["SimHei", "SimSun", "KaiTi"]:
                    if font_name in available_fonts:
                        self.chinese_font = font_name
                        break
        except:
            self.chinese_font = "Arial"  # 如果都不可用，使用Arial
        
        # 配置ttk样式，让Combobox和Treeview内容居中
        style = ttk.Style()
        # 配置Combobox样式，让文本居中
        style.configure("TCombobox", anchor="center")
        # 配置Treeview样式，让文本居中
        style.configure("Treeview", anchor="center")
        style.configure("Treeview.Heading", anchor="center")
        
        # 运行状态
        self.is_running = False
        self.ssh_client = None  # paramiko SSH客户端
        self.ssh_tunnel_thread = None  # SSH隧道线程
        self.crawler_is_running = False  # 爬虫运行状态
        self.is_downloading = False  # 下载/上传状态标志
        self._saved_category_selection = None  # 临时保存的分类选择（用于配置加载）
        self.is_locked = False  # 软件锁定状态
        self.ip_warning_count = 0  # 全局警告计数（不区分IP）
        self.pending_update_file = None  # 待更新的文件路径（用于自动替换）
        
        # IP白名单
        self.allowed_ips = ["222.195.78.54", "211.86.155.236", "211.86.152.184","10.8.0.2"]
        
        # 检查锁定状态（在创建界面之前，但需要先显示root窗口）
        if self.check_lock_status():
            # 如果被锁定，先显示主窗口（即使最小化），以便解锁对话框能正确显示
            self.root.deiconify()
            self.root.update()
            if not self.show_unlock_dialog():
                # 解锁失败，销毁程序
                self.root.destroy()
                sys.exit(1)
            else:
                # 解锁成功，清除锁定状态
                self.clear_lock_status()
        else:
            # 如果没有锁定，先隐藏主窗口，等界面创建完成后再显示
            self.root.withdraw()
        
        # 初始化模型缓存（必须在创建界面之前初始化）
        self.ollama_models_cache = {}
        
        # 初始化模式选择和在线API配置变量（必须在创建界面之前初始化）
        # 先尝试从config读取，如果没有则使用默认值
        config_values = self._load_config_values()
        
        self.api_mode_var = tk.StringVar(value=config_values.get("api_mode", "online"))  # "ollama" 或 "online"，默认在线API
        self.online_api_key_var = tk.StringVar(value=config_values.get("online_api_key", ""))
        self.online_api_url_var = tk.StringVar(value=config_values.get("online_api_url", "https://api.siliconflow.cn/v1/chat/completions"))
        self.online_model_var = tk.StringVar(value=config_values.get("online_model", "moonshotai/Kimi-K2-Instruct-0905"))
        self.online_api_provider_var = tk.StringVar(value=config_values.get("online_api_provider", "siliconflow"))  # "siliconflow", "custom"
        # 在线API模型缓存
        self.online_models_cache = {}  # {provider: [model_list]}
        # 在线API调用参数
        self.online_api_temperature_var = tk.StringVar(value=config_values.get("online_api_temperature", "0.7"))
        self.online_api_max_tokens_var = tk.StringVar(value=config_values.get("online_api_max_tokens", "4096"))
        self.online_api_top_p_var = tk.StringVar(value=config_values.get("online_api_top_p", "0.7"))
        self.online_api_enable_thinking_var = tk.StringVar(value=config_values.get("online_api_enable_thinking", "False"))
        self.online_api_thinking_budget_var = tk.StringVar(value=config_values.get("online_api_thinking_budget", "4096"))
        
        # 批处理配置
        self.batch_processing_var = tk.BooleanVar(value=False)  # 批处理开关
        self.batch_model_var = tk.StringVar(value="deepseek-ai/DeepSeek-V3")  # 批处理模型选择
        self.batch_output_dir_var = tk.StringVar(value="")  # 批处理结果保存目录
        self.batch_task_id_var = tk.StringVar(value="")  # 当前批处理任务ID
        self.batch_status_var = tk.StringVar(value="未开始")  # 批处理任务状态
        
        # 批处理支持的模型列表
        self.batch_supported_models = [
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
            "Qwen/QwQ-32B",
            "deepseek-ai/DeepSeek-V3.1-Terminus",
            "moonshotai/Kimi-K2-Instruct-0905",
            "MiniMaxAI/MiniMax-M2",
            "Qwen/Qwen3-235B-A22B-Thinking-2507"
        ]
        
        # 监控相关变量
        self.monitor_enabled_var = tk.BooleanVar(value=True)  # 监控开关
        self.rpm_var = tk.StringVar(value="0")  # 当前RPM
        self.tpm_var = tk.StringVar(value="0")  # 当前TPM
        self.total_tokens_var = tk.StringVar(value="0")  # 总token数
        self.avg_tokens_per_prompt_var = tk.StringVar(value="0")  # 平均每个prompt的token数
        self.rpm_limit_var = tk.StringVar(value="1000")  # RPM上限
        self.tpm_limit_var = tk.StringVar(value="100000")  # TPM上限
        self.total_tokens_limit_var = tk.StringVar(value="1000000")  # 总token数上限
        
        # 监控数据存储
        self.request_times = []  # 请求时间戳列表（用于计算RPM）
        self.token_counts = []  # 每分钟的token数列表（用于计算TPM）
        self.total_tokens_count = 0  # 总token数
        self.monitor_start_time = None  # 监控开始时间（用于计算实际运行时间）
        self.monitor_update_interval = 1000  # 监控更新间隔（毫秒）
        
        # 创建界面
        self.create_widgets()
        
        # 如果之前隐藏了主窗口，现在显示它
        if not self.root.winfo_viewable():
            self.root.deiconify()
        
        # 加载保存的配置
        self.load_config()
        
        # 如果批处理已启用，更新控件状态（延迟执行，确保界面已完全创建）
        if hasattr(self, 'batch_processing_var') and self.batch_processing_var.get():
            self.root.after(100, self.on_batch_processing_changed)
        
        # 加载模型缓存（在界面创建后）
        self.load_models_cache()
        
        # 加载在线模型缓存
        self.load_online_models_cache()
        
        # 加载在线模型到下拉框（在界面创建后）
        if hasattr(self, 'online_model_combo') and hasattr(self, 'online_api_provider_var'):
            provider = self.online_api_provider_var.get()
            if provider in self.online_models_cache:
                models = self.online_models_cache[provider]
                self.online_model_combo['values'] = models
        
        # 初始化SSH连接状态
        self.update_ssh_status()
        
        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        """创建GUI组件"""
        # 创建Notebook（标签页容器）
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # 创建第一个Tab：论文调研
        research_tab = ttk.Frame(notebook)
        notebook.add(research_tab, text="论文调研")
        self.create_research_tab(research_tab)
        
        # 创建第二个Tab：论文爬虫
        crawler_tab = ttk.Frame(notebook)
        notebook.add(crawler_tab, text="论文爬虫")
        self.create_crawler_tab(crawler_tab)
        
        # 创建第三个Tab：模型管理
        model_mgmt_tab = ttk.Frame(notebook)
        notebook.add(model_mgmt_tab, text="模型管理")
        self.create_model_management_tab(model_mgmt_tab)
        
        # 创建第四个Tab：帮助
        help_tab = ttk.Frame(notebook)
        notebook.add(help_tab, text="帮助")
        self.create_help_tab(help_tab)
        
    
    def create_research_tab(self, parent):
        """创建论文调研Tab"""
        # 主框架
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        main_frame.columnconfigure(0, weight=0)  # 左侧模式Tab，固定宽度
        main_frame.columnconfigure(1, weight=1)  # 中间内容区域（Prompt等）
        main_frame.columnconfigure(2, weight=1)  # 右侧新栏（运行日志）
        main_frame.rowconfigure(0, weight=1)  # 左侧和中间栏占据全部高度
        main_frame.rowconfigure(1, weight=0)  # 按钮区域不扩展
        main_frame.rowconfigure(2, weight=0)  # 底部按钮区域不扩展
        
        # 创建左侧模式选择Tab（垂直布局，占据全部高度）
        mode_notebook = ttk.Notebook(main_frame, width=400)  # 设置固定宽度，确保内容可见（能显示模型全称）
        mode_notebook.grid(row=0, column=0, rowspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # 在线API Tab
        online_tab = ttk.Frame(mode_notebook)
        mode_notebook.add(online_tab, text="在线API")
        
        # Ollama Tab
        ollama_tab = ttk.Frame(mode_notebook)
        mode_notebook.add(ollama_tab, text="Ollama")
        
        # 绑定Tab切换事件
        mode_notebook.bind("<<NotebookTabChanged>>", self.on_mode_tab_changed)
        
        # 创建中间内容区域（Prompt等，占据全部高度）
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 5))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=0)  # 表格配置不扩展
        right_frame.rowconfigure(1, weight=1)  # Prompt区域可扩展
        right_frame.rowconfigure(2, weight=1)  # 列名区域可扩展
        
        # 创建右侧新栏（运行日志）
        right_extra_frame = ttk.Frame(main_frame)
        right_extra_frame.grid(row=0, column=2, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 0))
        right_extra_frame.columnconfigure(0, weight=1)
        right_extra_frame.rowconfigure(0, weight=1)
        
        # === 左侧：在线API配置 ===
        self.create_online_api_tab(online_tab)
        
        # === 左侧：Ollama配置 ===
        self.create_ollama_tab(ollama_tab)
        
        # 保存mode_notebook引用
        self.mode_notebook = mode_notebook
        
        # 默认显示在线API Tab
        mode_notebook.select(0)
        self.api_mode_var.set("online")
        
        # 创建表格配置区域（两个Tab共用）
        self.create_table_config(main_frame, right_frame)
        
        # 创建中间内容区域（Prompt等）
        self.create_right_content(right_frame)
        
        # 创建控制按钮和输出区域
        self.create_control_buttons_and_output(main_frame)
        
        # 初始化模式显示（确保界面状态正确）
        self.on_mode_changed()
        
        # 确保按钮在初始化时可见（延迟执行，确保界面已完全创建）
        self.root.after(100, self._ensure_buttons_visible)
    
    def create_online_api_tab(self, parent):
        """创建在线API配置Tab"""
        parent.columnconfigure(0, weight=0)  # 标签列不扩展
        parent.columnconfigure(1, weight=1)   # 输入列扩展
        parent.rowconfigure(6, weight=1)     # 按钮行下方留空间
        
        # API提供商选择
        ttk.Label(parent, text="API提供商:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=5)
        provider_combo = ttk.Combobox(
            parent, 
            textvariable=self.online_api_provider_var, 
            values=["siliconflow", "custom"],
            width=20,
            state="readonly"
        )
        provider_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        provider_combo.bind("<<ComboboxSelected>>", self.on_api_provider_changed)
        parent.columnconfigure(1, weight=1)
        
        # API Key
        ttk.Label(parent, text="API Key:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=5)
        self.online_api_key_entry = ttk.Entry(parent, textvariable=self.online_api_key_var, width=30, show="*")
        self.online_api_key_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.online_api_key_entry.bind("<KeyRelease>", lambda e: self.on_online_api_config_changed())
        
        # API地址
        ttk.Label(parent, text="API地址:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=5)
        self.online_api_url_entry = ttk.Entry(parent, textvariable=self.online_api_url_var, width=30)
        self.online_api_url_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.online_api_url_entry.bind("<KeyRelease>", lambda e: self.on_online_api_config_changed())
        
        # 模型选择（下拉列表+刷新按钮）
        model_frame = ttk.Frame(parent)
        model_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=5)
        model_frame.columnconfigure(1, weight=1)
        
        ttk.Label(model_frame, text="模型名称:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.online_model_combo = ttk.Combobox(model_frame, textvariable=self.online_model_var, width=25)
        self.online_model_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.online_model_combo.bind("<<ComboboxSelected>>", lambda e: self.on_online_api_config_changed())
        # 绑定输入事件，实现自动完成
        self.online_model_combo.bind('<KeyRelease>', self._on_online_model_input)
        self.online_model_refresh_btn = ttk.Button(model_frame, text="刷新", command=self.fetch_online_models, width=8)
        self.online_model_refresh_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # API调用参数
        params_frame = ttk.LabelFrame(parent, text="API参数", padding="5")
        params_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10, padx=5)
        params_frame.columnconfigure(1, weight=1)
        params_frame.columnconfigure(3, weight=1)
        
        ttk.Label(params_frame, text="Temperature:").grid(row=0, column=0, sticky=tk.W, pady=3, padx=5)
        self.online_api_temperature_entry = ttk.Entry(params_frame, textvariable=self.online_api_temperature_var, width=18)
        self.online_api_temperature_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(params_frame, text="Max Tokens:").grid(row=0, column=2, sticky=tk.W, pady=3, padx=5)
        self.online_api_max_tokens_entry = ttk.Entry(params_frame, textvariable=self.online_api_max_tokens_var, width=18)
        self.online_api_max_tokens_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(params_frame, text="Top P:").grid(row=1, column=0, sticky=tk.W, pady=3, padx=5)
        self.online_api_top_p_entry = ttk.Entry(params_frame, textvariable=self.online_api_top_p_var, width=18)
        self.online_api_top_p_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(params_frame, text="Enable Thinking:").grid(row=1, column=2, sticky=tk.W, pady=3, padx=5)
        self.online_api_thinking_combo = ttk.Combobox(params_frame, textvariable=self.online_api_enable_thinking_var, values=["False", "True"], width=15, state="readonly")
        self.online_api_thinking_combo.grid(row=1, column=3, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(params_frame, text="Thinking Budget:").grid(row=2, column=0, sticky=tk.W, pady=3, padx=5)
        self.online_api_thinking_budget_entry = ttk.Entry(params_frame, textvariable=self.online_api_thinking_budget_var, width=18)
        self.online_api_thinking_budget_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=3)
        
        # 并发配置区域（移到左侧Tab中）
        concurrency_frame = ttk.LabelFrame(parent, text="并发配置", padding="10")
        concurrency_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10, padx=5)
        concurrency_frame.columnconfigure(1, weight=1)
        concurrency_frame.columnconfigure(3, weight=1)
        
        # 并发数量（左列）
        ttk.Label(concurrency_frame, text="并发数量:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.max_workers_var = tk.StringVar(value="8")
        self.workers_entry = ttk.Entry(concurrency_frame, textvariable=self.max_workers_var, width=15)
        self.workers_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Label(concurrency_frame, text="(线程数)", font=(self.chinese_font, 8), foreground="gray").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        
        # 并发间隔（右列）
        ttk.Label(concurrency_frame, text="间隔(秒):").grid(row=0, column=3, sticky=tk.W, pady=5, padx=(10, 0))
        self.api_delay_var = tk.StringVar(value="0.5")
        self.delay_entry = ttk.Entry(concurrency_frame, textvariable=self.api_delay_var, width=5)
        self.delay_entry.grid(row=0, column=4, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Label(concurrency_frame, text="(延迟)", font=(self.chinese_font, 8), foreground="gray").grid(row=0, column=5, sticky=tk.W, padx=5, pady=5)
        
        # 批处理配置区域
        batch_frame = ttk.LabelFrame(parent, text="批处理配置", padding="10")
        batch_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10, padx=5)
        batch_frame.columnconfigure(1, weight=1)
        
        # 批处理开关
        batch_switch_frame = ttk.Frame(batch_frame)
        batch_switch_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        ttk.Label(batch_switch_frame, text="启用批处理:").grid(row=0, column=0, sticky=tk.W, padx=5)
        batch_switch = ttk.Checkbutton(batch_switch_frame, variable=self.batch_processing_var, 
                                       command=self.on_batch_processing_changed)
        batch_switch.grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Label(batch_switch_frame, text="(批处理任务耗时较长)", 
                  font=(self.chinese_font, 8), foreground="gray").grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # 批处理模型选择
        ttk.Label(batch_frame, text="模型选择:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=5)
        self.batch_model_combo = ttk.Combobox(batch_frame, textvariable=self.batch_model_var, 
                                               values=self.batch_supported_models, width=30, state="readonly")
        self.batch_model_combo.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 批处理结果保存目录
        ttk.Label(batch_frame, text="结果保存目录:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=5)
        self.batch_dir_entry = ttk.Entry(batch_frame, textvariable=self.batch_output_dir_var, width=30, state="disabled")
        self.batch_dir_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.batch_dir_browse_btn = ttk.Button(batch_frame, text="浏览...", command=self.browse_batch_output_dir, state="disabled")
        self.batch_dir_browse_btn.grid(row=2, column=2, padx=5, pady=5)
        
        # 批处理API参数
        batch_params_frame = ttk.LabelFrame(batch_frame, text="批处理API参数", padding="5")
        batch_params_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10, padx=5)
        batch_params_frame.columnconfigure(1, weight=1)
        batch_params_frame.columnconfigure(3, weight=1)
        
        ttk.Label(batch_params_frame, text="Temperature:").grid(row=0, column=0, sticky=tk.W, pady=3, padx=5)
        self.batch_temperature_var = tk.StringVar(value="0.7")
        self.batch_temperature_entry = ttk.Entry(batch_params_frame, textvariable=self.batch_temperature_var, width=18, state="disabled")
        self.batch_temperature_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(batch_params_frame, text="Max Tokens:").grid(row=0, column=2, sticky=tk.W, pady=3, padx=5)
        self.batch_max_tokens_var = tk.StringVar(value="4096")
        self.batch_max_tokens_entry = ttk.Entry(batch_params_frame, textvariable=self.batch_max_tokens_var, width=18, state="disabled")
        self.batch_max_tokens_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(batch_params_frame, text="Top P:").grid(row=1, column=0, sticky=tk.W, pady=3, padx=5)
        self.batch_top_p_var = tk.StringVar(value="0.7")
        self.batch_top_p_entry = ttk.Entry(batch_params_frame, textvariable=self.batch_top_p_var, width=18, state="disabled")
        self.batch_top_p_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(batch_params_frame, text="Enable Thinking:").grid(row=1, column=2, sticky=tk.W, pady=3, padx=5)
        self.batch_enable_thinking_var = tk.StringVar(value="False")
        self.batch_thinking_combo = ttk.Combobox(batch_params_frame, textvariable=self.batch_enable_thinking_var, 
                                                  values=["False", "True"], width=15, state="disabled")
        self.batch_thinking_combo.grid(row=1, column=3, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(batch_params_frame, text="Thinking Budget:").grid(row=2, column=0, sticky=tk.W, pady=3, padx=5)
        self.batch_thinking_budget_var = tk.StringVar(value="4096")
        self.batch_thinking_budget_entry = ttk.Entry(batch_params_frame, textvariable=self.batch_thinking_budget_var, width=18, state="disabled")
        self.batch_thinking_budget_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=3)
        
        # 批处理任务状态
        batch_status_frame = ttk.Frame(batch_frame)
        batch_status_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(batch_status_frame, text="任务状态:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.batch_status_label = ttk.Label(batch_status_frame, textvariable=self.batch_status_var, foreground="gray")
        self.batch_status_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # 批处理控制按钮（放在下一行）
        batch_control_frame = ttk.Frame(batch_frame)
        batch_control_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        self.batch_check_status_btn = ttk.Button(batch_control_frame, text="检查状态", 
                                                 command=self.check_batch_status, state="disabled")
        self.batch_check_status_btn.grid(row=0, column=0, padx=5)
        
        self.batch_cancel_btn = ttk.Button(batch_control_frame, text="取消任务", 
                                           command=self.cancel_batch_task, state="disabled")
        self.batch_cancel_btn.grid(row=0, column=1, padx=5)
        
        self.batch_download_btn = ttk.Button(batch_control_frame, text="下载结果", 
                                              command=self.download_batch_results, state="disabled")
        self.batch_download_btn.grid(row=0, column=2, padx=5)
        
        # 在线API模式的开始/停止按钮（移到主界面底部，这里只保存引用）
        self.online_start_button = None  # 将在主界面底部创建
        self.online_stop_button = None   # 将在主界面底部创建
        
        # 更新API提供商默认值
        self.on_api_provider_changed()
    
    def create_ollama_tab(self, parent):
        """创建Ollama配置Tab"""
        parent.columnconfigure(0, weight=0)  # 标签列不扩展
        parent.columnconfigure(1, weight=1)   # 输入列扩展
        parent.rowconfigure(2, weight=1)       # 按钮行下方留空间
        
        # SSH连接配置区域（单列竖排）
        self.config_frame = ttk.LabelFrame(parent, text="SSH连接配置", padding="10")
        self.config_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10), padx=5)
        self.config_frame.columnconfigure(1, weight=1)
        config_frame = self.config_frame
        
        # 用户名
        ttk.Label(config_frame, text="用户名:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.username_var = tk.StringVar(value="hzq")
        ttk.Entry(config_frame, textvariable=self.username_var, width=20).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # SSH端口
        ttk.Label(config_frame, text="SSH端口:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ssh_port_var = tk.StringVar(value="7001")
        ttk.Entry(config_frame, textvariable=self.ssh_port_var, width=20).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 服务器IP
        ttk.Label(config_frame, text="服务器IP:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.host_var = tk.StringVar(value="211.86.155.236")
        ttk.Entry(config_frame, textvariable=self.host_var, width=20).grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 密码
        ttk.Label(config_frame, text="密码:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar(value="你猜呀？")
        ttk.Entry(config_frame, textvariable=self.password_var, show="*", width=20).grid(row=3, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 连接和断开按钮
        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        self.connect_btn = ttk.Button(button_frame, text="连接", command=self.connect_ssh, width=10)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        self.disconnect_btn = ttk.Button(button_frame, text="断开", command=self.disconnect_ssh, width=10, state="disabled")
        self.disconnect_btn.pack(side=tk.LEFT, padx=5)
        self.ssh_status_label = ttk.Label(button_frame, text="未连接", foreground="gray")
        self.ssh_status_label.pack(side=tk.LEFT, padx=10)
        
        # Ollama配置区域
        self.ollama_frame = ttk.LabelFrame(parent, text="Ollama配置", padding="10")
        self.ollama_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10), padx=5)
        ollama_frame = self.ollama_frame
        ollama_frame.columnconfigure(1, weight=1)
        
        # 竖着排列所有配置项
        # 本地端口
        ttk.Label(ollama_frame, text="本地端口:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.local_port_var = tk.StringVar(value="11435")
        ttk.Entry(ollama_frame, textvariable=self.local_port_var, width=20).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 远程端口
        ttk.Label(ollama_frame, text="远程端口:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.remote_port_var = tk.StringVar(value="11434")
        ttk.Entry(ollama_frame, textvariable=self.remote_port_var, width=20).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Ollama路径（默认路径，不显示输入框）
        # 默认路径会在连接SSH后根据服务器实际情况确定
        self.ollama_path_var = tk.StringVar(value="")
        
        # Ollama自定义位置（用户输入的上级目录，如 /data/xxx）- 移到Ollama配置栏
        ttk.Label(ollama_frame, text="Ollama位置:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.ollama_custom_dir_var = tk.StringVar(value="")
        ollama_dir_entry = ttk.Entry(ollama_frame, textvariable=self.ollama_custom_dir_var, width=20)
        ollama_dir_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Label(ollama_frame, text="(如: /data/xxx)", font=(self.chinese_font, 8), foreground="gray").grid(row=3, column=1, sticky=tk.W, padx=5, pady=(0, 5))
        
        # 模型名称
        ttk.Label(ollama_frame, text="模型名称:").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.model_var = tk.StringVar(value="deepseek-r1")
        model_combo = ttk.Combobox(ollama_frame, textvariable=self.model_var, values=DEFAULT_MODELS, width=17)
        model_combo.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        model_combo.bind("<<ComboboxSelected>>", lambda e: self.on_model_selected())
        # 绑定输入事件，实现自动完成
        model_combo.bind('<KeyRelease>', self._on_ollama_model_input)
        self.model_combo = model_combo  # 保存引用以便更新
        
        # 刷新按钮（在模型名称旁边）
        ttk.Button(ollama_frame, text="刷新", command=self.fetch_models_from_ollama, width=8).grid(row=4, column=2, padx=5, pady=5)
        
        # 模型大小选择
        ttk.Label(ollama_frame, text="模型大小:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.model_size_var = tk.StringVar(value="")
        model_size_combo = ttk.Combobox(ollama_frame, textvariable=self.model_size_var, width=17, state="readonly")
        model_size_combo.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.model_size_combo = model_size_combo  # 保存引用以便更新
        
        # GPU选择
        ttk.Label(ollama_frame, text="GPU设备:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.gpu_var = tk.StringVar(value="0")
        gpu_entry = ttk.Entry(ollama_frame, textvariable=self.gpu_var, width=20)
        gpu_entry.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Label(ollama_frame, text="(如: 0,1 或留空使用所有GPU)", font=(self.chinese_font, 8), foreground="gray").grid(row=7, column=1, sticky=tk.W, padx=5, pady=(0, 5))
        
        # Ollama模式的开始/停止按钮（移到主界面底部，这里只保存引用）
        self.ollama_start_button = None  # 将在主界面底部创建
        self.ollama_stop_button = None   # 将在主界面底部创建
    
    def create_table_config(self, main_frame, right_frame):
        """创建表格配置区域（两个Tab共用）"""
        # 表格配置区域 - 放在右侧顶部
        table_frame = ttk.LabelFrame(right_frame, text="表格配置", padding="10")
        table_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        table_frame.columnconfigure(1, weight=1)
        table_frame.columnconfigure(3, weight=1)
        
        # 表格文件路径（第一行：表格文件输入框变长，刷新列名放在后面）
        ttk.Label(table_frame, text="表格文件:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.table_var = tk.StringVar(value="NeurIPS 2025 Events.csv")
        table_entry = ttk.Entry(table_frame, textvariable=self.table_var, width=30)
        table_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(table_frame, text="浏览...", command=self.browse_table).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(table_frame, text="刷新列名", command=self.auto_analyze_columns).grid(row=0, column=3, padx=5, pady=5)
        
        # 输出文件名（第二行）
        ttk.Label(table_frame, text="输出文件:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.output_file_var = tk.StringVar(value="调研报告.csv")
        output_entry = ttk.Entry(table_frame, textvariable=self.output_file_var, width=30)
        output_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(table_frame, text="浏览...", command=self.browse_output_file).grid(row=1, column=2, padx=5, pady=5)
        
        # 输出列名配置（第三行）
        ttk.Label(table_frame, text="输出列名:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.output_columns_var = tk.StringVar(value="title,category,method,team")
        output_cols_entry = ttk.Entry(table_frame, textvariable=self.output_columns_var, width=30)
        output_cols_entry.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(table_frame, text="添加到Prompt", command=self.add_output_columns_to_prompt).grid(row=2, column=3, padx=5, pady=5)
        ttk.Label(table_frame, text="(用逗号分隔，如: title,category,method)", font=(self.chinese_font, 8), foreground="gray").grid(row=3, column=1, columnspan=3, sticky=tk.W, padx=5, pady=(0, 5))
    
    def create_right_content(self, right_frame):
        """创建中间内容区域（Prompt等）"""
        # 设置right_frame的列权重，让Prompt栏变窄
        right_frame.columnconfigure(0, weight=1)
        
        prompt_frame = ttk.LabelFrame(right_frame, text="分析Prompt配置", padding="10")
        prompt_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))  # 改为row=1，表格配置在row=0
        prompt_frame.columnconfigure(0, weight=1)
        prompt_frame.rowconfigure(1, weight=1)  # 让prompt输入框可以扩展
        
        # Prompt说明
        prompt_help = "提示：点击下方列名标签到Prompt中，或直接输入 {列名}"
        ttk.Label(prompt_frame, text=prompt_help, foreground="gray", font=(self.chinese_font, 8)).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        # Prompt输入框（恢复高度）
        self.prompt_text = scrolledtext.ScrolledText(
            prompt_frame,
            wrap=tk.WORD,
            width=50,
            height=20,  # 恢复原来的高度
            font=("Consolas", 9)
        )
        default_prompt = """请分析以下论文是否与"神经算子预训练"（neural operator pretraining）或者physics fundation model（物理基础模型）相关。

标题: {name}
作者: {speakers/authors}
摘要: {abstract}

如果相关，请提供以下信息（JSON格式）：
{{
    "title": "论文标题",
    "category": "论文的分类（例如：神经算子预训练、算子学习、预训练方法等）",
    "method": "论文提出的具体方法和技术",
    "team": "研究团队（作者所属机构或团队名称）"
}}

如果不相关，请返回
{{
    "title": "不相关",
    "category": "",
    "method": "",
    "team": ""
}}

请只返回JSON格式的响应，不要添加其他解释。"""
        self.prompt_text.insert(1.0, default_prompt)
        self.prompt_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        
        # 列名标签区域
        columns_frame = ttk.LabelFrame(right_frame, text="表格列名（点击插入到Prompt）", padding="10")
        columns_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))  # 改为row=2
        columns_frame.columnconfigure(0, weight=1)
        
        # 创建列名标签容器（可滚动）
        columns_canvas = tk.Canvas(columns_frame, height=100)  # 降低高度
        columns_scrollbar = ttk.Scrollbar(columns_frame, orient="vertical", command=columns_canvas.yview)
        self.columns_container = ttk.Frame(columns_canvas)
        
        # 保存canvas引用以便后续使用
        self.columns_canvas = columns_canvas
        
        def update_scroll_region(event=None):
            """更新滚动区域"""
            columns_canvas.configure(scrollregion=columns_canvas.bbox("all"))
        
        def on_mousewheel(event):
            """鼠标滚轮滚动"""
            columns_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        self.columns_container.bind("<Configure>", update_scroll_region)
        
        # 绑定鼠标滚轮事件（Windows）
        columns_canvas.bind("<MouseWheel>", on_mousewheel)
        # 绑定鼠标滚轮事件（Linux）
        columns_canvas.bind("<Button-4>", lambda e: columns_canvas.yview_scroll(-1, "units"))
        columns_canvas.bind("<Button-5>", lambda e: columns_canvas.yview_scroll(1, "units"))
        # 让容器也支持滚轮
        self.columns_container.bind("<MouseWheel>", on_mousewheel)
        self.columns_container.bind("<Button-4>", lambda e: columns_canvas.yview_scroll(-1, "units"))
        self.columns_container.bind("<Button-5>", lambda e: columns_canvas.yview_scroll(1, "units"))
        
        columns_canvas.create_window((0, 0), window=self.columns_container, anchor="nw")
        columns_canvas.configure(yscrollcommand=columns_scrollbar.set)
        
        columns_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        columns_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        columns_frame.rowconfigure(0, weight=1)
        columns_frame.columnconfigure(0, weight=1)
        
        # 存储列名标签
        self.column_labels = []
    
    def create_control_buttons_and_output(self, main_frame):
        """创建控制按钮和输出区域"""
        # === 输出区域（置于右下角，占整个UI的一半） ===
        output_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="10")
        # 放在第2列（右侧新栏），从第0行开始，占据三行（与左栏对齐）
        output_frame.grid(row=0, column=2, rowspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0), pady=(0, 0))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(1, weight=1)  # 日志文本区域可扩展
        
        # === 监控区域（在运行日志上方） ===
        monitor_frame = ttk.LabelFrame(output_frame, text="使用量监控", padding="5")
        monitor_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        monitor_frame.columnconfigure(1, weight=1)
        monitor_frame.columnconfigure(3, weight=1)
        monitor_frame.columnconfigure(5, weight=1)
        
        # 监控开关
        monitor_switch_frame = ttk.Frame(monitor_frame)
        monitor_switch_frame.grid(row=0, column=0, columnspan=8, sticky=(tk.W, tk.E), pady=(0, 3))
        ttk.Label(monitor_switch_frame, text="启用监控:").grid(row=0, column=0, sticky=tk.W, padx=5)
        monitor_switch = ttk.Checkbutton(monitor_switch_frame, variable=self.monitor_enabled_var, 
                                         command=self.on_monitor_enabled_changed)
        monitor_switch.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # 监控内容容器（用于显示/隐藏）
        self.monitor_content_frame = ttk.Frame(monitor_frame)
        self.monitor_content_frame.grid(row=1, column=0, columnspan=8, sticky=(tk.W, tk.E), pady=3)
        
        # RPM监控
        ttk.Label(self.monitor_content_frame, text="RPM:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.rpm_label = ttk.Label(self.monitor_content_frame, textvariable=self.rpm_var, foreground="blue", font=("Arial", 10, "bold"))
        self.rpm_label.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        ttk.Label(self.monitor_content_frame, text="/").grid(row=0, column=2, padx=2, pady=3)
        rpm_limit_entry = ttk.Entry(self.monitor_content_frame, textvariable=self.rpm_limit_var, width=8)
        rpm_limit_entry.grid(row=0, column=3, padx=5, pady=3)
        
        # TPM监控
        ttk.Label(self.monitor_content_frame, text="TPM:").grid(row=0, column=4, sticky=tk.W, padx=5, pady=3)
        self.tpm_label = ttk.Label(self.monitor_content_frame, textvariable=self.tpm_var, foreground="blue", font=("Arial", 10, "bold"))
        self.tpm_label.grid(row=0, column=5, sticky=tk.W, padx=5, pady=3)
        ttk.Label(self.monitor_content_frame, text="/").grid(row=0, column=6, padx=2, pady=3)
        tpm_limit_entry = ttk.Entry(self.monitor_content_frame, textvariable=self.tpm_limit_var, width=8)
        tpm_limit_entry.grid(row=0, column=7, padx=5, pady=3)
        
        # 总Token数监控
        ttk.Label(self.monitor_content_frame, text="总Token:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.total_tokens_label = ttk.Label(self.monitor_content_frame, textvariable=self.total_tokens_var, foreground="blue", font=("Arial", 10, "bold"))
        self.total_tokens_label.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        ttk.Label(self.monitor_content_frame, text="/").grid(row=1, column=2, padx=2, pady=3)
        total_tokens_limit_entry = ttk.Entry(self.monitor_content_frame, textvariable=self.total_tokens_limit_var, width=8)
        total_tokens_limit_entry.grid(row=1, column=3, padx=5, pady=3)
        
        # 平均每个prompt的token数监控
        ttk.Label(self.monitor_content_frame, text="平均Token/Prompt:").grid(row=1, column=4, sticky=tk.W, padx=5, pady=3)
        self.avg_tokens_per_prompt_label = ttk.Label(self.monitor_content_frame, textvariable=self.avg_tokens_per_prompt_var, foreground="blue", font=("Arial", 10, "bold"))
        self.avg_tokens_per_prompt_label.grid(row=1, column=5, sticky=tk.W, padx=5, pady=3)
        
        # 根据初始状态设置监控显示
        if not self.monitor_enabled_var.get():
            self.monitor_content_frame.grid_remove()
        
        # 滚动文本框（调整宽度以适应一半UI）
        self.output_text = scrolledtext.ScrolledText(
            output_frame,
            wrap=tk.WORD,
            width=50,  # 调整宽度以适应一半UI
            height=35,  # 调整高度
            font=("Consolas", 9)
        )
        self.output_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 进度条
        self.progress_var = tk.StringVar(value="就绪")
        ttk.Label(output_frame, textvariable=self.progress_var).grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        
        # === 控制按钮区域（放在整个界面中间底部） ===
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=1, pady=(10, 5), sticky=(tk.W, tk.E))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(2, weight=1)
        
        # 左侧占位（用于居中）
        ttk.Frame(button_frame, width=1).grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # 按钮容器（居中）
        self.button_container = ttk.Frame(button_frame)
        self.button_container.grid(row=0, column=1)
        
        # 在线API模式的开始/停止按钮
        self.online_start_button = ttk.Button(self.button_container, text="开始运行", command=self.start_research, width=15, state="disabled")
        self.online_stop_button = ttk.Button(self.button_container, text="停止", command=self.stop_research, width=15, state=tk.DISABLED)
        
        # Ollama模式的开始/停止按钮
        self.ollama_start_button = ttk.Button(self.button_container, text="开始运行", command=self.start_research, width=15, state="disabled")
        self.ollama_stop_button = ttk.Button(self.button_container, text="停止", command=self.stop_research, width=15, state=tk.DISABLED)
        
        # 清空输出按钮（始终显示）
        self.clear_button = ttk.Button(self.button_container, text="清空输出", command=self.clear_output, width=15)
        
        # 右侧占位（用于居中）
        ttk.Frame(button_frame, width=1).grid(row=0, column=2, sticky=(tk.W, tk.E))
    
    def create_crawler_tab(self, parent):
        """创建论文爬虫Tab"""
        # ArXiv学科分类（完整列表）
        ARXIV_CATEGORIES = {
            "astro-ph": "天体物理",
            "astro-ph.CO": "宇宙学与非规则天体物理学",
            "astro-ph.EP": "地球与行星天体物理学",
            "astro-ph.GA": "星系的天体物理学",
            "astro-ph.HE": "高能天体物理现象",
            "astro-ph.IM": "天体物理学的仪器和方法",
            "astro-ph.SR": "太阳与恒星天体物理学",
            "cond-mat.dis-nn": "无序系统与神经网络",
            "cond-mat.mes-hall": "中尺度和纳米尺度物理学",
            "cond-mat.mtrl-sci": "材料科学",
            "cond-mat.other": "其他凝聚态",
            "cond-mat.quant-gas": "量子气体",
            "cond-mat.soft": "软凝聚物",
            "cond-mat.stat-mech": "统计力学",
            "cond-mat.str-el": "强关联电子",
            "cond-mat.supr-con": "超导现象",
            "cs.AI": "人工智能",
            "cs.AR": "硬件架构",
            "cs.CC": "计算复杂性",
            "cs.CE": "计算工程，金融和科学",
            "cs.CG": "计算几何",
            "cs.CL": "计算与语言",
            "cs.CR": "密码学与保安",
            "cs.CV": "计算机视觉与模式识别",
            "cs.CY": "电脑与社会",
            "cs.DB": "数据库",
            "cs.DC": "分布式、并行和集群计算",
            "cs.DL": "数字仓库",
            "cs.DM": "离散数学",
            "cs.DS": "数据结构和算法",
            "cs.ET": "新兴科技",
            "cs.FL": "形式语言与自动机理论",
            "cs.GL": "一般文学",
            "cs.GR": "图形",
            "cs.GT": "计算机科学与博弈论",
            "cs.HC": "人机交互",
            "cs.IR": "信息检索",
            "cs.IT": "信息理论",
            "cs.LG": "学习",
            "cs.LO": "计算机科学中的逻辑",
            "cs.MA": "多代理系统",
            "cs.MM": "多媒体",
            "cs.MS": "数学软件",
            "cs.NA": "数值分析",
            "cs.NE": "神经和进化计算",
            "cs.NI": "网络与互联网架构",
            "cs.OH": "其他计算机科学",
            "cs.OS": "操作系统",
            "cs.PF": "性能",
            "cs.PL": "编程语言",
            "cs.RO": "机器人技术",
            "cs.SC": "符号计算",
            "cs.SD": "声音",
            "cs.SE": "软件工程",
            "cs.SI": "社会和信息网络",
            "cs.SY": "系统及控制",
            "econ.EM": "计量经济学",
            "eess.AS": "音频及语音处理",
            "eess.IV": "图像和视频处理",
            "eess.SP": "信号处理",
            "gr-qc": "广义相对论和量子宇宙学",
            "hep-ex": "高能物理实验",
            "hep-lat": "高能物理-晶格",
            "hep-ph": "高能物理-现象学",
            "hep-th": "高能物理理论",
            "math.AC": "交换代数",
            "math.AG": "代数几何",
            "math.AP": "偏微分方程分析",
            "math.AT": "代数拓扑",
            "math.CA": "传统分析和微分方程",
            "math.CO": "组合数学",
            "math.CT": "范畴理论",
            "math.CV": "复杂变量",
            "math.DG": "微分几何",
            "math.DS": "动力系统",
            "math.FA": "功能分析",
            "math.GM": "普通数学",
            "math.GN": "点集拓扑学",
            "math.GR": "群论",
            "math.GT": "几何拓扑学",
            "math.HO": "历史和概述",
            "math.IT": "信息理论",
            "math.KT": "K 理论与同调",
            "math.LO": "逻辑",
            "math.MG": "度量几何学",
            "math.MP": "数学物理",
            "math.NA": "数值分析",
            "math.NT": "数论",
            "math.OA": "算子代数",
            "math.OC": "优化和控制",
            "math.PR": "概率",
            "math.QA": "量子代数",
            "math.RA": "环与代数",
            "math.RT": "表示论",
            "math.SG": "辛几何",
            "math.SP": "光谱理论",
            "math.ST": "统计学理论",
            "math-ph": "数学物理",
            "nlin.AO": "适应与自组织系统",
            "nlin.CD": "混沌动力学",
            "nlin.CG": "元胞自动机与格子气体",
            "nlin.PS": "模式形成与孤子",
            "nlin.SI": "严格可解可积系统",
            "nucl-ex": "核试验",
            "nucl-th": "核理论",
            "physics.acc-ph": "加速器物理学",
            "physics.ao-ph": "大气和海洋物理学",
            "physics.app-ph": "应用物理学",
            "physics.atm-clus": "原子和分子团簇",
            "physics.atom-ph": "原子物理学",
            "physics.bio-ph": "生物物理学",
            "physics.chem-ph": "化学物理",
            "physics.class-ph": "经典物理学",
            "physics.comp-ph": "计算物理学",
            "physics.data-an": "数据分析、统计和概率",
            "physics.ed-ph": "物理教育",
            "physics.flu-dyn": "流体动力学",
            "physics.gen-ph": "普通物理",
            "physics.geo-ph": "地球物理学",
            "physics.hist-ph": "物理学的历史与哲学",
            "physics.ins-det": "仪器和探测器",
            "physics.med-ph": "医学物理学",
            "physics.optics": "光学",
            "physics.plasm-ph": "等离子体物理",
            "physics.pop-ph": "大众物理",
            "physics.soc-ph": "物理学与社会",
            "physics.space-ph": "空间物理学",
            "q-bio.BM": "生物分子",
            "q-bio.CB": "细胞行为",
            "q-bio.GN": "基因组学",
            "q-bio.MN": "分子网络",
            "q-bio.NC": "神经元与认知",
            "q-bio.OT": "其他定量生物学",
            "q-bio.PE": "种群与进化",
            "q-bio.QM": "定量方法",
            "q-bio.SC": "亚细胞突起",
            "q-bio.TO": "组织和器官",
            "q-fin.CP": "金融工程",
            "q-fin.EC": "经济学",
            "q-fin.GN": "财务概述",
            "q-fin.MF": "数学金融",
            "q-fin.PM": "投资组合管理",
            "q-fin.PR": "证券定价",
            "q-fin.RM": "风险管理",
            "q-fin.ST": "金融统计",
            "q-fin.TR": "交易与市场微观结构",
            "quant-ph": "量子物理学",
            "stat.AP": "应用",
            "stat.CO": "计算",
            "stat.ME": "方法论",
            "stat.ML": "机器学习",
            "stat.OT": "其他统计学",
            "stat.TH": "统计学理论"
        }
        
        # 主框架
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === 配置区域 ===
        config_frame = ttk.LabelFrame(main_frame, text="爬虫配置", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))
        config_frame.columnconfigure(1, weight=1)
        
        # 数据源选择（暂时只有arxiv）
        ttk.Label(config_frame, text="数据源:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.crawler_source_var = tk.StringVar(value="arxiv")
        source_combo = ttk.Combobox(config_frame, textvariable=self.crawler_source_var, 
                                    values=["arxiv"], state="readonly", width=20)
        source_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 学科分类（多选）- 两个Treeview（支持折叠展开）
        ttk.Label(config_frame, text="学科分类:").grid(row=1, column=0, sticky=(tk.W, tk.N), pady=5)
        
        # 创建分类选择框架（两个Treeview）
        category_frame = ttk.Frame(config_frame)
        category_frame.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        category_frame.columnconfigure(0, weight=1)
        category_frame.columnconfigure(1, weight=1)
        category_frame.rowconfigure(0, weight=1)
        
        # 存储所有分类数据
        self.all_categories = ARXIV_CATEGORIES.copy()
        self.category_selected_items = set()  # 存储已选中的分类代码（直接存储代码，不是item ID）
        self.unselected_tree_items = {}  # {cat_code: item_id} 未选列表的映射
        self.selected_tree_items = {}  # {cat_code: item_id} 已选列表的映射
        self.unselected_main_items = {}  # {main_cat: item_id} 未选列表的主分类映射
        self.selected_main_items = {}  # {main_cat: item_id} 已选列表的主分类映射
        
        # 左侧：未选中的分类
        unselected_frame = ttk.LabelFrame(category_frame, text="未选", padding="5")
        unselected_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        unselected_frame.columnconfigure(0, weight=1)
        unselected_frame.rowconfigure(0, weight=1)
        
        unselected_scrollbar = ttk.Scrollbar(unselected_frame)
        unselected_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.unselected_tree = ttk.Treeview(
            unselected_frame,
            columns=("desc",),
            show="tree headings",
            height=10,
            yscrollcommand=unselected_scrollbar.set,
            selectmode="browse"
        )
        self.unselected_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        unselected_scrollbar.config(command=self.unselected_tree.yview)
        
        # 配置列（居中显示）
        self.unselected_tree.heading("#0", text="分类代码")
        self.unselected_tree.heading("desc", text="分类描述")
        self.unselected_tree.column("#0", width=180, anchor=tk.CENTER)
        self.unselected_tree.column("desc", width=250, anchor=tk.CENTER)
        
        # 配置标签样式（使用中文字体）
        self.unselected_tree.tag_configure("main", foreground="gray", font=(self.chinese_font, 10, "bold"))
        self.unselected_tree.tag_configure("sub", foreground="black", font=(self.chinese_font, 10))
        
        # 右侧：已选中的分类
        selected_frame = ttk.LabelFrame(category_frame, text="已选", padding="5")
        selected_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        selected_frame.columnconfigure(0, weight=1)
        selected_frame.rowconfigure(0, weight=1)
        
        selected_scrollbar = ttk.Scrollbar(selected_frame)
        selected_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.selected_tree = ttk.Treeview(
            selected_frame,
            columns=("desc",),
            show="tree headings",
            height=10,
            yscrollcommand=selected_scrollbar.set,
            selectmode="browse"
        )
        self.selected_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        selected_scrollbar.config(command=self.selected_tree.yview)
        
        # 配置列（居中显示）
        self.selected_tree.heading("#0", text="分类代码")
        self.selected_tree.heading("desc", text="分类描述")
        self.selected_tree.column("#0", width=180, anchor=tk.CENTER)
        self.selected_tree.column("desc", width=250, anchor=tk.CENTER)
        
        # 配置标签样式（使用中文字体）
        self.selected_tree.tag_configure("main", foreground="gray", font=(self.chinese_font, 10, "bold"))
        self.selected_tree.tag_configure("sub", foreground="black", font=(self.chinese_font, 10))
        
        # 辅助函数：从item获取分类代码
        def get_cat_code_from_item(tree, item_id):
            """从Treeview item获取分类代码"""
            item_text = tree.item(item_id, "text")
            # 检查是否是主分类（没有对应的cat_code）
            if item_id in tree.get_children():
                # 这是主分类，返回None
                return None
            # 这是子分类，从映射中查找
            for cat_code, stored_item_id in (self.unselected_tree_items if tree == self.unselected_tree else self.selected_tree_items).items():
                if stored_item_id == item_id:
                    return cat_code
            return None
        
        # 辅助函数：移动分类（从未选到已选）
        def move_to_selected(event=None):
            """从未选列表移动到已选列表"""
            selection = self.unselected_tree.selection()
            if not selection:
                return
            item_id = selection[0]
            cat_code = get_cat_code_from_item(self.unselected_tree, item_id)
            if cat_code is None:
                return  # 主分类不能移动
            
            # 获取分类信息
            item_text = self.unselected_tree.item(item_id, "text")
            item_values = self.unselected_tree.item(item_id, "values")
            main_item_id = self.unselected_tree.parent(item_id)
            main_cat = self.unselected_tree.item(main_item_id, "text") if main_item_id else None
            
            # 从未选列表删除
            self.unselected_tree.delete(item_id)
            del self.unselected_tree_items[cat_code]
            
            # 添加到已选列表
            if main_cat:
                # 检查主分类是否已存在
                if main_cat not in self.selected_main_items:
                    main_item = self.selected_tree.insert("", tk.END, text=main_cat, values=("",), tags=("main",))
                    self.selected_main_items[main_cat] = main_item
                else:
                    main_item = self.selected_main_items[main_cat]
                sub_item = self.selected_tree.insert(main_item, tk.END, text=item_text, values=item_values, tags=("sub",))
            else:
                sub_item = self.selected_tree.insert("", tk.END, text=item_text, values=item_values, tags=("sub",))
            
            self.selected_tree_items[cat_code] = sub_item
            self.category_selected_items.add(cat_code)
            
            # 展开主分类
            if main_cat and main_item:
                self.selected_tree.item(main_item, open=True)
        
        # 辅助函数：移动分类（从已选到未选）
        def move_to_unselected(event=None):
            """从已选列表移动到未选列表"""
            selection = self.selected_tree.selection()
            if not selection:
                return
            item_id = selection[0]
            cat_code = get_cat_code_from_item(self.selected_tree, item_id)
            if cat_code is None:
                return  # 主分类不能移动
            
            # 获取分类信息
            item_text = self.selected_tree.item(item_id, "text")
            item_values = self.selected_tree.item(item_id, "values")
            main_item_id = self.selected_tree.parent(item_id)
            main_cat = self.selected_tree.item(main_item_id, "text") if main_item_id else None
            
            # 从已选列表删除
            self.selected_tree.delete(item_id)
            del self.selected_tree_items[cat_code]
            
            # 如果主分类下没有子项了，删除主分类
            if main_cat and main_item_id:
                remaining_children = self.selected_tree.get_children(main_item_id)
                if not remaining_children:
                    self.selected_tree.delete(main_item_id)
                    del self.selected_main_items[main_cat]
            
            # 添加到未选列表
            if main_cat:
                # 检查主分类是否已存在
                if main_cat not in self.unselected_main_items:
                    main_item = self.unselected_tree.insert("", tk.END, text=main_cat, values=("",), tags=("main",))
                    self.unselected_main_items[main_cat] = main_item
                else:
                    main_item = self.unselected_main_items[main_cat]
                sub_item = self.unselected_tree.insert(main_item, tk.END, text=item_text, values=item_values, tags=("sub",))
            else:
                sub_item = self.unselected_tree.insert("", tk.END, text=item_text, values=item_values, tags=("sub",))
            
            self.unselected_tree_items[cat_code] = sub_item
            self.category_selected_items.discard(cat_code)
            
            # 展开主分类
            if main_cat and main_item:
                self.unselected_tree.item(main_item, open=True)
        
        # 绑定单击事件
        def on_unselected_click(event):
            selection = self.unselected_tree.selection()
            if selection:
                move_to_selected()
        
        def on_selected_click(event):
            selection = self.selected_tree.selection()
            if selection:
                move_to_unselected()
        
        self.unselected_tree.bind("<Button-1>", on_unselected_click)
        self.selected_tree.bind("<Button-1>", on_selected_click)
        
        # 按主分类分组
        main_categories = {}
        for cat_code, cat_desc in ARXIV_CATEGORIES.items():
            main_cat = cat_code.split('.')[0] if '.' in cat_code else cat_code.split('-')[0] if '-' in cat_code else cat_code
            if main_cat not in main_categories:
                main_categories[main_cat] = []
            main_categories[main_cat].append((cat_code, cat_desc))
        
        # 初始化未选列表：所有分类都在未选列表中，按主分类分组
        for main_cat in sorted(main_categories.keys()):
            main_item = self.unselected_tree.insert("", tk.END, text=main_cat, values=("",), tags=("main",))
            self.unselected_main_items[main_cat] = main_item
            for cat_code, cat_desc in sorted(main_categories[main_cat]):
                item_id = self.unselected_tree.insert(main_item, tk.END, text=cat_code, values=(cat_desc,), tags=("sub",))
                self.unselected_tree_items[cat_code] = item_id
        
        # 展开所有主分类
        for main_item in self.unselected_tree.get_children():
            self.unselected_tree.item(main_item, open=True)
        
        # 恢复保存的分类选择
        if hasattr(self, '_saved_category_selection') and self._saved_category_selection:
            # _saved_category_selection 现在应该包含分类代码（不是item ID）
            saved_codes = set(self._saved_category_selection)
            # 从未选列表中移除已保存的分类，添加到已选列表
            items_to_move = []
            for cat_code in saved_codes:
                if cat_code in self.unselected_tree_items:
                    items_to_move.append(cat_code)
            
            # 移动分类
            for cat_code in items_to_move:
                item_id = self.unselected_tree_items[cat_code]
                item_text = self.unselected_tree.item(item_id, "text")
                item_values = self.unselected_tree.item(item_id, "values")
                main_item_id = self.unselected_tree.parent(item_id)
                main_cat = self.unselected_tree.item(main_item_id, "text") if main_item_id else None
                
                # 从未选列表删除
                self.unselected_tree.delete(item_id)
                del self.unselected_tree_items[cat_code]
                
                # 添加到已选列表
                if main_cat:
                    if main_cat not in self.selected_main_items:
                        main_item = self.selected_tree.insert("", tk.END, text=main_cat, values=("",), tags=("main",))
                        self.selected_main_items[main_cat] = main_item
                    else:
                        main_item = self.selected_main_items[main_cat]
                    sub_item = self.selected_tree.insert(main_item, tk.END, text=item_text, values=item_values, tags=("sub",))
                else:
                    sub_item = self.selected_tree.insert("", tk.END, text=item_text, values=item_values, tags=("sub",))
                
                self.selected_tree_items[cat_code] = sub_item
                self.category_selected_items.add(cat_code)
                
                # 展开主分类
                if main_cat and main_item:
                    self.selected_tree.item(main_item, open=True)
            
            # 清除临时保存的选择
            delattr(self, '_saved_category_selection')
        elif not self.category_selected_items:
            # 默认选中cs.AI分类
            if "cs.AI" in self.unselected_tree_items:
                item_id = self.unselected_tree_items["cs.AI"]
                # 模拟点击移动
                self.unselected_tree.selection_set(item_id)
                move_to_selected()
            elif self.unselected_tree_items:
                # 如果cs.AI不存在，选中第一个分类
                first_cat_code = list(self.unselected_tree_items.keys())[0]
                item_id = self.unselected_tree_items[first_cat_code]
                # 模拟点击移动
                self.unselected_tree.selection_set(item_id)
                move_to_selected()
        
        # 时间区间（使用日历控件）
        ttk.Label(config_frame, text="开始日期:").grid(row=2, column=0, sticky=tk.W, pady=5)
        date_frame_start = ttk.Frame(config_frame)
        date_frame_start.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        self.crawler_start_date_var = tk.StringVar(value="2025-12-31")
        start_date_entry = ttk.Entry(date_frame_start, textvariable=self.crawler_start_date_var, width=18)
        start_date_entry.pack(side=tk.LEFT)
        
        def open_start_calendar():
            self._open_calendar(self.crawler_start_date_var, start_date_entry)
        
        ttk.Button(date_frame_start, text="📅", command=open_start_calendar, width=3).pack(side=tk.LEFT, padx=(5, 0))
        
        ttk.Label(config_frame, text="结束日期:").grid(row=3, column=0, sticky=tk.W, pady=5)
        date_frame_end = ttk.Frame(config_frame)
        date_frame_end.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        self.crawler_end_date_var = tk.StringVar(value="2026-01-01")
        end_date_entry = ttk.Entry(date_frame_end, textvariable=self.crawler_end_date_var, width=18)
        end_date_entry.pack(side=tk.LEFT)
        
        def open_end_calendar():
            self._open_calendar(self.crawler_end_date_var, end_date_entry)
        
        ttk.Button(date_frame_end, text="📅", command=open_end_calendar, width=3).pack(side=tk.LEFT, padx=(5, 0))
        
        # 提示信息
        ttk.Label(config_frame, text="提示:", font=(self.chinese_font, 8, "bold")).grid(row=4, column=0, sticky=tk.W, pady=5)
        ttk.Label(config_frame, text="将爬取指定时间段和分类的全部论文（无数量限制）", 
                 font=(self.chinese_font, 8), foreground="blue").grid(row=4, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        # 输出文件
        ttk.Label(config_frame, text="输出文件:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.crawler_output_file_var = tk.StringVar(value="arxiv_papers.csv")
        output_file_entry = ttk.Entry(config_frame, textvariable=self.crawler_output_file_var, width=20)
        output_file_entry.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(config_frame, text="浏览...", command=self.browse_crawler_output).grid(row=5, column=2, padx=5, pady=5)
        
        # === 控制按钮 ===
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.crawler_start_button = ttk.Button(button_frame, text="开始爬取", command=self.start_crawler, width=15)
        self.crawler_start_button.pack(side=tk.LEFT, padx=5)
        
        self.crawler_stop_button = ttk.Button(button_frame, text="停止", command=self.stop_crawler, 
                                              width=15, state=tk.DISABLED)
        self.crawler_stop_button.pack(side=tk.LEFT, padx=5)
        
        self.crawler_clear_button = ttk.Button(button_frame, text="清空输出", command=self.clear_crawler_output, width=15)
        self.crawler_clear_button.pack(side=tk.LEFT, padx=5)
        
        # === 输出区域 ===
        output_frame = ttk.LabelFrame(main_frame, text="爬取日志", padding="10")
        output_frame.pack(fill=tk.BOTH, expand=True)
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        
        self.crawler_output_text = scrolledtext.ScrolledText(
            output_frame,
            wrap=tk.WORD,
            width=80,
            height=20,
            font=("Consolas", 9)
        )
        self.crawler_output_text.pack(fill=tk.BOTH, expand=True)
        
        # 爬虫运行状态
        self.crawler_is_running = False
    
    def create_model_management_tab(self, parent):
        """创建模型管理Tab"""
        # 主框架
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # 顶部控制区域
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        control_frame.columnconfigure(2, weight=1)
        
        # Ollama自定义位置输入框
        ttk.Label(control_frame, text="Ollama位置:").grid(row=0, column=0, padx=5, sticky=tk.W)
        ollama_dir_entry = ttk.Entry(control_frame, textvariable=self.ollama_custom_dir_var, width=30)
        ollama_dir_entry.grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))
        ttk.Label(control_frame, text="(如: /data/xxx，实际路径为 /data/xxx/ollama/bin/ollama)", 
                  font=(self.chinese_font, 8), foreground="gray").grid(row=0, column=2, padx=5, sticky=tk.W)
        
        # 刷新按钮
        self.refresh_model_btn = ttk.Button(control_frame, text="刷新模型列表", command=self.refresh_model_list)
        self.refresh_model_btn.grid(row=1, column=0, padx=5, pady=5)
        
        # 删除按钮
        self.delete_model_btn = ttk.Button(control_frame, text="删除选中模型", command=self.delete_selected_model, state="disabled")
        self.delete_model_btn.grid(row=1, column=1, padx=5, sticky=tk.W, pady=5)
        
        # 状态标签
        self.model_status_label = ttk.Label(control_frame, text="点击'刷新模型列表'获取模型信息", foreground="gray")
        self.model_status_label.grid(row=1, column=2, padx=10, sticky=tk.E, pady=5)
        
        # 模型列表区域
        list_frame = ttk.LabelFrame(main_frame, text="已下载的模型", padding="10")
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 创建Treeview显示模型列表
        columns = ("name", "size", "modified", "id")
        self.model_tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        
        # 设置列标题和宽度
        self.model_tree.heading("name", text="模型名称")
        self.model_tree.heading("size", text="大小")
        self.model_tree.heading("modified", text="修改时间")
        self.model_tree.heading("id", text="ID")
        
        self.model_tree.column("name", width=300, anchor="center")
        self.model_tree.column("size", width=150, anchor="center")
        self.model_tree.column("modified", width=200, anchor="center")
        self.model_tree.column("id", width=100, anchor="center")
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.model_tree.yview)
        self.model_tree.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        self.model_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 绑定选择事件
        self.model_tree.bind("<<TreeviewSelect>>", self.on_model_select)
        
        # 日志输出区域
        log_frame = ttk.LabelFrame(main_frame, text="操作日志", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        self.model_mgmt_output = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            height=8,
            font=("Consolas", 9)
        )
        self.model_mgmt_output.pack(fill=tk.BOTH, expand=True)
    
    def _ensure_buttons_visible(self):
        """确保按钮在初始化时可见"""
        # 直接调用 on_mode_changed 来确保按钮正确显示
        self.on_mode_changed()
    
    def on_mode_tab_changed(self, event=None):
        """当模式Tab切换时的回调"""
        if hasattr(self, 'mode_notebook'):
            selected_tab = self.mode_notebook.index(self.mode_notebook.select())
            if selected_tab == 0:  # 在线API Tab
                self.api_mode_var.set("online")
            else:  # Ollama Tab
                self.api_mode_var.set("ollama")
            self.on_mode_changed()
    
    def on_mode_changed(self):
        """当模式切换时的回调"""
        mode = self.api_mode_var.get()
        
        # 先移除所有按钮
        if hasattr(self, 'button_container'):
            for widget in self.button_container.winfo_children():
                widget.pack_forget()
        
        if mode == "ollama":
            # 更新Ollama按钮状态（基于SSH连接状态）
            if hasattr(self, 'ollama_start_button') and self.ollama_start_button:
                if self.check_ssh_connection():
                    self.ollama_start_button.config(state=tk.NORMAL)
                else:
                    self.ollama_start_button.config(state=tk.DISABLED)
                # 按顺序显示按钮：开始、停止、清空
                self.ollama_start_button.pack(side=tk.LEFT, padx=5)
                self.ollama_stop_button.pack(side=tk.LEFT, padx=5)
                self.clear_button.pack(side=tk.LEFT, padx=5)
        else:  # online
            # 更新在线API按钮状态（基于API配置）
            if hasattr(self, 'online_start_button') and self.online_start_button:
                api_key = self.online_api_key_var.get().strip()
                api_url = self.online_api_url_var.get().strip()
                model_name = self.online_model_var.get().strip()
                if api_key and api_url and model_name:
                    self.online_start_button.config(state=tk.NORMAL)
                else:
                    self.online_start_button.config(state=tk.DISABLED)
                # 按顺序显示按钮：开始、停止、清空
                self.online_start_button.pack(side=tk.LEFT, padx=5)
                self.online_stop_button.pack(side=tk.LEFT, padx=5)
                self.clear_button.pack(side=tk.LEFT, padx=5)
    
    def on_api_provider_changed(self, event=None):
        """当API提供商改变时的回调"""
        provider = self.online_api_provider_var.get()
        if provider == "siliconflow":
            self.online_api_url_var.set("https://api.siliconflow.cn/v1/chat/completions")
            if not self.online_model_var.get() or "moonshotai" not in self.online_model_var.get().lower():
                self.online_model_var.set("moonshotai/Kimi-K2-Instruct-0905")
            # 加载缓存的模型列表
            self.load_online_models_from_cache()
        # custom模式不改变默认值，让用户自己输入
        self.on_online_api_config_changed()  # 更新按钮状态
    
    def get_current_start_button(self):
        """获取当前模式的开始按钮"""
        mode = self.api_mode_var.get()
        if mode == "online":
            return self.online_start_button if hasattr(self, 'online_start_button') else None
        else:
            return self.ollama_start_button if hasattr(self, 'ollama_start_button') else None
    
    def get_current_stop_button(self):
        """获取当前模式的停止按钮"""
        mode = self.api_mode_var.get()
        if mode == "online":
            return self.online_stop_button if hasattr(self, 'online_stop_button') else None
        else:
            return self.ollama_stop_button if hasattr(self, 'ollama_stop_button') else None
    
    def _on_online_model_input(self, event):
        """在线模型输入时的自动完成处理"""
        if event.keysym in ['Return', 'Tab', 'Up', 'Down', 'Left', 'Right']:
            return  # 忽略导航键
        
        current_text = self.online_model_var.get().lower()
        if not current_text:
            # 如果输入为空，显示所有模型
            provider = self.online_api_provider_var.get()
            if provider in self.online_models_cache:
                self.online_model_combo['values'] = self.online_models_cache[provider]
            return
        
        # 过滤匹配的模型
        provider = self.online_api_provider_var.get()
        if provider in self.online_models_cache:
            all_models = self.online_models_cache[provider]
            matched_models = [m for m in all_models if current_text in m.lower()]
            self.online_model_combo['values'] = matched_models
            # 自动展开下拉列表（直接调用Combobox的内部方法）
            if matched_models:
                def expand_dropdown():
                    widget = self.online_model_combo
                    try:
                        # 方法1：尝试直接调用Combobox的内部popdown方法
                        # 获取Combobox的tkinter内部对象
                        tk_widget = widget.tk
                        # 尝试调用内部方法展开下拉列表
                        try:
                            # 使用eval直接调用Tcl命令来展开下拉列表
                            widget.tk.call(widget._w, 'set', widget._w, '')
                            widget.tk.call('ttk::combobox::Popdown', widget._w)
                            widget.tk.call('ttk::combobox::Post', widget._w)
                        except:
                            # 方法2：如果内部方法失败，使用鼠标点击下拉箭头
                            widget.update_idletasks()
                            x = widget.winfo_width() - 15  # 下拉箭头在右侧
                            y = widget.winfo_height() // 2
                            # 模拟点击下拉箭头区域（不会影响输入光标）
                            widget.event_generate('<Button-1>', x=x, y=y)
                            widget.event_generate('<ButtonRelease-1>', x=x, y=y)
                    except:
                        pass
                # 延迟执行，确保输入已完成
                self.root.after(10, expand_dropdown)
    
    def _on_ollama_model_input(self, event):
        """Ollama模型输入时的自动完成处理"""
        if event.keysym in ['Return', 'Tab', 'Up', 'Down', 'Left', 'Right']:
            return  # 忽略导航键
        
        current_text = self.model_var.get().lower()
        if not current_text:
            # 如果输入为空，显示所有模型
            if hasattr(self, 'ollama_models_cache') and self.ollama_models_cache:
                model_list = sorted(self.ollama_models_cache.keys())
                self.model_combo['values'] = model_list
            else:
                self.model_combo['values'] = DEFAULT_MODELS
            return
        
        # 获取所有可用模型
        if hasattr(self, 'ollama_models_cache') and self.ollama_models_cache:
            all_models = sorted(self.ollama_models_cache.keys())
        else:
            all_models = DEFAULT_MODELS
        
        # 过滤匹配的模型
        matched_models = [m for m in all_models if current_text in m.lower()]
        self.model_combo['values'] = matched_models
        # 自动展开下拉列表（直接调用Combobox的内部方法）
        if matched_models:
            def expand_dropdown():
                widget = self.model_combo
                try:
                    # 方法1：尝试直接调用Combobox的内部popdown方法
                    try:
                        # 使用eval直接调用Tcl命令来展开下拉列表
                        widget.tk.call('ttk::combobox::Post', widget._w)
                    except:
                        # 方法2：如果内部方法失败，使用鼠标点击下拉箭头
                        widget.update_idletasks()
                        x = widget.winfo_width() - 15  # 下拉箭头在右侧
                        y = widget.winfo_height() // 2
                        # 模拟点击下拉箭头区域（不会影响输入光标）
                        widget.event_generate('<Button-1>', x=x, y=y)
                        widget.event_generate('<ButtonRelease-1>', x=x, y=y)
                except:
                    pass
            # 延迟执行，确保输入已完成
            self.root.after(10, expand_dropdown)
    
    def on_online_api_config_changed(self):
        """当在线API配置改变时的回调"""
        if self.api_mode_var.get() == "online" and hasattr(self, 'online_start_button') and self.online_start_button is not None:
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            model_name = self.online_model_var.get().strip()
            if api_key and api_url and model_name:
                self.online_start_button.config(state=tk.NORMAL)
            else:
                self.online_start_button.config(state=tk.DISABLED)
    
    def fetch_online_models(self):
        """获取在线API的模型列表"""
        provider = self.online_api_provider_var.get()
        api_key = self.online_api_key_var.get().strip()
        
        if not api_key:
            self.log("✗ 请先输入API Key", "ERROR")
            return
        
        self.log(f"正在获取 {provider} 的模型列表...", "INFO")
        
        try:
            if provider == "siliconflow":
                url = "https://api.siliconflow.cn/v1/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                models = [item["id"] for item in data.get("data", [])]
            else:
                self.log(f"✗ {provider} 暂不支持自动获取模型列表", "WARN")
                return
            
            if models:
                # 保存到缓存
                self.online_models_cache[provider] = models
                self.save_online_models_cache()
                
                # 更新下拉列表
                if hasattr(self, 'online_model_combo'):
                    self.online_model_combo['values'] = models
                
                self.log(f"✓ 已获取 {len(models)} 个模型", "SUCCESS")
            else:
                self.log("✗ 未获取到模型列表", "WARN")
        except Exception as e:
            self.log(f"✗ 获取模型列表失败: {e}", "ERROR")
    
    def load_online_models_from_cache(self):
        """从缓存加载模型列表"""
        provider = self.online_api_provider_var.get()
        if provider in self.online_models_cache and hasattr(self, 'online_model_combo'):
            models = self.online_models_cache[provider]
            self.online_model_combo['values'] = models
    
    def save_online_models_cache(self):
        """保存在线模型缓存到文件"""
        try:
            cache_file = os.path.join(APP_DIR, "online_models_cache.json")
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.online_models_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            pass  # 静默失败
    
    def load_online_models_cache(self):
        """从文件加载在线模型缓存"""
        try:
            cache_file = os.path.join(APP_DIR, "online_models_cache.json")
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    self.online_models_cache = json.load(f)
                    total_models = sum(len(models) for models in self.online_models_cache.values())
                    if hasattr(self, 'log'):
                        self.log(f"已加载在线模型缓存（{len(self.online_models_cache)} 个提供商，共 {total_models} 个模型）", "INFO")
            else:
                self.online_models_cache = {}
        except Exception as e:
            self.online_models_cache = {}
            if hasattr(self, 'log'):
                self.log(f"加载在线模型缓存失败: {e}", "WARN")
    
    def refresh_model_list(self):
        """刷新模型列表（使用SSH连接）"""
        self.model_mgmt_log("正在获取模型列表...", "INFO")
        self.model_status_label.config(text="正在获取模型列表...")
        self.delete_model_btn.config(state="disabled")
        
        # 清空现有列表
        for item in self.model_tree.get_children():
            self.model_tree.delete(item)
        
        # 检查SSH连接是否已建立
        self.model_mgmt_log("检查SSH连接...", "INFO")
        
        # 临时保存原来的log方法，使用model_mgmt_log
        original_log = self.log
        def model_mgmt_log_wrapper(message, level="INFO"):
            self.model_mgmt_log(message, level)
        self.log = model_mgmt_log_wrapper
        
        try:
            # 检查SSH连接是否存在
            if not self.check_ssh_connection():
                self.model_mgmt_log("✗ SSH连接未建立，请先在'论文调研'页面点击'连接'按钮", "ERROR")
                self.model_status_label.config(text="SSH未连接")
                self.log = original_log  # 恢复原来的log方法
                return
            self.model_mgmt_log("✓ SSH连接已就绪", "SUCCESS")
        finally:
            self.log = original_log  # 恢复原来的log方法
        
        # 优先使用用户自定义的Ollama路径
        ollama_path = None
        custom_dir = self.ollama_custom_dir_var.get().strip()
        
        if custom_dir:
            # 用户输入了自定义路径，检查该路径下是否有ollama
            # 用户输入的是上级目录，如 /data/xxx，实际路径为 /data/xxx/ollama/bin/ollama
            custom_ollama_path = f"{custom_dir.rstrip('/')}/ollama/bin/ollama"
            self.model_mgmt_log(f"检查用户指定的Ollama路径: {custom_ollama_path}", "INFO")
            success_custom, output_custom, _ = self.run_ssh_command(
                f"test -x {custom_ollama_path} && {custom_ollama_path} --version 2>&1 || echo 'NOT_FOUND'", 
                show_console=False
            )
            found_custom = success_custom and "NOT_FOUND" not in output_custom
            
            if found_custom:
                ollama_path = custom_ollama_path
                self.model_mgmt_log(f"✓ 使用用户指定的 ollama 路径: {ollama_path}", "SUCCESS")
            else:
                # 用户指定的路径不存在，尝试安装到该位置
                self.model_mgmt_log(f"✗ 用户指定的路径不存在，将安装到: {custom_ollama_path}", "WARN")
                self.model_status_label.config(text="正在安装Ollama...")
                
                # 执行安装（使用model_mgmt_log输出日志）
                original_log = self.log
                def model_mgmt_log_wrapper(message, level="INFO"):
                    self.model_mgmt_log(message, level)
                self.log = model_mgmt_log_wrapper
                
                try:
                    install_success = self.install_ollama(custom_ollama_path)
                finally:
                    self.log = original_log  # 恢复原来的log方法
                
                if install_success:
                    self.model_mgmt_log("✓ Ollama安装成功，继续获取模型列表...", "SUCCESS")
                    # 安装成功后，再次检查
                    success_custom, output_custom, _ = self.run_ssh_command(
                        f"test -x {custom_ollama_path} && {custom_ollama_path} --version 2>&1 || echo 'NOT_FOUND'", 
                        show_console=False
                    )
                    found_custom = success_custom and "NOT_FOUND" not in output_custom
                    if found_custom:
                        ollama_path = custom_ollama_path
                    else:
                        self.model_mgmt_log("✗ 安装后仍无法找到Ollama", "ERROR")
                        self.model_status_label.config(text="安装失败")
                        return
                else:
                    self.model_mgmt_log("✗ Ollama安装失败", "ERROR")
                    self.model_status_label.config(text="安装失败")
                    return
        
        # 如果用户没有指定路径或用户指定的路径不可用，使用默认检测逻辑
        if not ollama_path:
            username = self.username_var.get()
            data_path = f"/data/{username}/ollama/bin/ollama"
            home_path = f"/home/{username}/ollama/bin/ollama"
            
            # 检测 /data/<username>/ollama/bin/ollama
            success1, output1, _ = self.run_ssh_command(f"test -x {data_path} && {data_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
            found_in_data = success1 and "NOT_FOUND" not in output1
            
            # 检测 /home/<username>/ollama/bin/ollama
            success2, output2, _ = self.run_ssh_command(f"test -x {home_path} && {home_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
            found_in_home = success2 and "NOT_FOUND" not in output2
            
            if found_in_data:
                ollama_path = data_path
                self.model_mgmt_log(f"使用检测到的 ollama 路径: {ollama_path}", "INFO")
            elif found_in_home:
                ollama_path = home_path
                self.model_mgmt_log(f"使用检测到的 ollama 路径: {ollama_path}", "INFO")
            else:
                # 未找到Ollama，尝试自动安装
                self.model_mgmt_log("✗ 未找到Ollama，尝试自动安装...", "WARN")
                self.model_status_label.config(text="正在安装Ollama...")
                
                # 确定安装路径（根据是否有/data/目录）
                success_check, output_check, _ = self.run_ssh_command("test -d /data && echo 'EXISTS' || echo 'NOT_EXISTS'", show_console=False)
                output_check_clean = output_check.strip() if output_check else ""
                if success_check and output_check_clean == "EXISTS":
                    install_path = f"/data/{username}/ollama/bin/ollama"
                else:
                    install_path = f"/home/{username}/ollama/bin/ollama"
                
                # 执行安装（使用model_mgmt_log输出日志）
                original_log = self.log
                def model_mgmt_log_wrapper(message, level="INFO"):
                    self.model_mgmt_log(message, level)
                self.log = model_mgmt_log_wrapper
                
                try:
                    install_success = self.install_ollama(install_path)
                finally:
                    self.log = original_log  # 恢复原来的log方法
                
                if install_success:
                    self.model_mgmt_log("✓ Ollama安装成功，继续获取模型列表...", "SUCCESS")
                    # 安装成功后，重新检测ollama路径
                    success1, output1, _ = self.run_ssh_command(f"test -x {data_path} && {data_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
                    found_in_data = success1 and "NOT_FOUND" not in output1
                    success2, output2, _ = self.run_ssh_command(f"test -x {home_path} && {home_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
                    found_in_home = success2 and "NOT_FOUND" not in output2
                    
                    if found_in_data:
                        ollama_path = data_path
                    elif found_in_home:
                        ollama_path = home_path
                    else:
                        self.model_mgmt_log("✗ 安装后仍无法找到Ollama", "ERROR")
                        self.model_status_label.config(text="安装失败")
                        return
                else:
                    self.model_mgmt_log("✗ Ollama安装失败", "ERROR")
                    self.model_status_label.config(text="安装失败")
                    return
        
        # 通过SSH命令获取模型列表（模拟控制台）
        try:
            # run_ssh_command会自动显示命令提示符和输出（控制台风格）
            success, output, code = self.run_ssh_command(f"{ollama_path} list")
            
            if success and output:
                lines = output.strip().split('\n')
                if len(lines) > 1:  # 有表头
                    # 解析表头，确定列的顺序
                    header = lines[0].strip().upper()
                    # 查找各列在表头中的位置
                    name_idx = -1
                    id_idx = -1
                    size_idx = -1
                    modified_idx = -1
                    
                    header_parts = lines[0].strip().split()
                    for i, part in enumerate(header_parts):
                        part_upper = part.upper()
                        if 'NAME' in part_upper:
                            name_idx = i
                        elif 'ID' in part_upper:
                            id_idx = i
                        elif 'SIZE' in part_upper:
                            size_idx = i
                        elif 'MODIFIED' in part_upper:
                            modified_idx = i
                    
                    count = 0
                    for line in lines[1:]:  # 跳过表头
                        line = line.strip()
                        if not line:
                            continue
                        
                        parts = line.split()
                        if len(parts) < 2:
                            continue
                        
                        # 根据表头确定的索引提取各列
                        name = parts[name_idx] if name_idx >= 0 and name_idx < len(parts) else "N/A"
                        model_id = parts[id_idx] if id_idx >= 0 and id_idx < len(parts) else "N/A"
                        
                        # SIZE 列可能包含单位（如 "5.2 GB"），需要合并
                        if size_idx >= 0 and size_idx < len(parts):
                            size = parts[size_idx]
                            # 如果下一个部分是单位（GB、MB、KB等），合并它们
                            if size_idx + 1 < len(parts):
                                next_part = parts[size_idx + 1].upper()
                                if next_part in ['GB', 'MB', 'KB', 'B', 'TB', 'PB', 'EB', 'ZB', 'YB']:
                                    size = f"{size} {parts[size_idx + 1]}"
                                    # 如果合并了单位，MODIFIED 列应该从 size_idx + 2 开始
                                    modified_start_idx = size_idx + 2
                                else:
                                    modified_start_idx = size_idx + 1
                            else:
                                modified_start_idx = size_idx + 1
                        else:
                            size = "N/A"
                            modified_start_idx = size_idx + 1 if size_idx >= 0 else modified_idx
                        
                        # MODIFIED 列可能包含多个词（如 "2 hours ago"），从 SIZE 列之后开始
                        # 优先使用 modified_start_idx（基于 SIZE 列计算），而不是表头中的 modified_idx
                        if modified_start_idx >= 0 and modified_start_idx < len(parts):
                            modified = " ".join(parts[modified_start_idx:])
                        else:
                            # 如果 modified_start_idx 无效，尝试使用 modified_idx，但要确保它大于 size_idx
                            if modified_idx >= 0 and modified_idx < len(parts) and (size_idx < 0 or modified_idx > size_idx):
                                modified = " ".join(parts[modified_idx:])
                            else:
                                modified = "N/A"
                        
                        self.model_tree.insert("", tk.END, values=(name, size, modified, model_id))
                        count += 1
                    
                    if count > 0:
                        self.model_mgmt_log(f"✓ 成功获取 {count} 个模型", "SUCCESS")
                        self.model_status_label.config(text=f"已加载 {count} 个模型")
                    else:
                        self.model_mgmt_log("未找到任何模型", "WARN")
                        self.model_status_label.config(text="未找到任何模型")
                else:
                    self.model_mgmt_log("未找到任何模型", "WARN")
                    self.model_status_label.config(text="未找到任何模型")
            else:
                self.model_mgmt_log(f"✗ 命令执行失败 (退出码: {code})", "ERROR")
                if output:
                    self.model_mgmt_log(f"错误输出: {output}", "ERROR")
                self.model_status_label.config(text="获取失败")
        except Exception as e:
            self.model_mgmt_log(f"✗ 获取模型列表失败: {e}", "ERROR")
            self.model_status_label.config(text="获取失败")
    
    def on_model_select(self, event):
        """当选择模型时，启用删除按钮"""
        selection = self.model_tree.selection()
        if selection:
            self.delete_model_btn.config(state="normal")
        else:
            self.delete_model_btn.config(state="disabled")
    
    def delete_selected_model(self):
        """删除选中的模型（使用SSH连接）"""
        selection = self.model_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个模型")
            return
        
        # 获取选中的模型名称
        item = self.model_tree.item(selection[0])
        model_name = item['values'][0]
        
        # 二次确认
        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除模型 '{model_name}' 吗？\n\n此操作不可恢复！",
            icon="warning"
        )
        
        if not confirm:
            return
        
        # 确保SSH连接已建立（establish_ssh_tunnel会自动检查并复用现有连接）
        self.model_mgmt_log("检查SSH连接...", "INFO")
        
        # 临时保存原来的log方法，使用model_mgmt_log
        original_log = self.log
        def model_mgmt_log_wrapper(message, level="INFO"):
            self.model_mgmt_log(message, level)
        self.log = model_mgmt_log_wrapper
        
        try:
            # 检查SSH连接是否存在
            if not self.check_ssh_connection():
                self.model_mgmt_log("✗ SSH连接未建立，请先在'论文调研'页面点击'连接'按钮", "ERROR")
                messagebox.showerror("错误", "SSH连接未建立，请先在'论文调研'页面点击'连接'按钮")
                self.log = original_log  # 恢复原来的log方法
                return
            self.model_mgmt_log("✓ SSH连接已就绪", "SUCCESS")
        finally:
            self.log = original_log  # 恢复原来的log方法
        
        # 优先使用用户自定义的Ollama路径
        ollama_path = None
        custom_dir = self.ollama_custom_dir_var.get().strip()
        
        if custom_dir:
            # 用户输入了自定义路径，检查该路径下是否有ollama
            custom_ollama_path = f"{custom_dir.rstrip('/')}/ollama/bin/ollama"
            success_custom, output_custom, _ = self.run_ssh_command(
                f"test -x {custom_ollama_path} && {custom_ollama_path} --version 2>&1 || echo 'NOT_FOUND'", 
                show_console=False
            )
            found_custom = success_custom and "NOT_FOUND" not in output_custom
            if found_custom:
                ollama_path = custom_ollama_path
                self.model_mgmt_log(f"使用用户指定的 ollama 路径: {ollama_path}", "INFO")
        
        # 如果用户没有指定路径或用户指定的路径不可用，使用默认检测逻辑
        if not ollama_path:
            username = self.username_var.get()
            data_path = f"/data/{username}/ollama/bin/ollama"
            home_path = f"/home/{username}/ollama/bin/ollama"
            
            # 检测 /data/<username>/ollama/bin/ollama
            success1, output1, _ = self.run_ssh_command(f"test -x {data_path} && {data_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
            found_in_data = success1 and "NOT_FOUND" not in output1
            
            # 检测 /home/<username>/ollama/bin/ollama
            success2, output2, _ = self.run_ssh_command(f"test -x {home_path} && {home_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
            found_in_home = success2 and "NOT_FOUND" not in output2
            
            if found_in_data:
                ollama_path = data_path
                self.model_mgmt_log(f"使用检测到的 ollama 路径: {ollama_path}", "INFO")
            elif found_in_home:
                ollama_path = home_path
                self.model_mgmt_log(f"使用检测到的 ollama 路径: {ollama_path}", "INFO")
            else:
                self.model_mgmt_log("✗ 错误: 未找到Ollama", "ERROR")
                self.model_mgmt_log("提示: 请先在'论文调研'页面启动服务，系统会自动检测Ollama路径", "INFO")
                messagebox.showerror("错误", "未找到Ollama，无法删除模型")
                return
        
        # 执行删除（模拟控制台）
        self.model_mgmt_log(f"正在删除模型: {model_name}...", "INFO")
        self.delete_model_btn.config(state="disabled")
        
        try:
            # run_ssh_command会自动显示命令提示符和输出（控制台风格）
            success, output, code = self.run_ssh_command(f"{ollama_path} rm {model_name}")
            
            if success:
                self.model_mgmt_log(f"✓ 成功删除模型: {model_name} (退出码: {code})", "SUCCESS")
                # 从列表中移除
                self.model_tree.delete(selection[0])
                self.model_status_label.config(text=f"已删除模型: {model_name}")
            else:
                self.model_mgmt_log(f"✗ 删除模型失败 (退出码: {code})", "ERROR")
                if output:
                    self.model_mgmt_log(f"错误输出: {output}", "ERROR")
                messagebox.showerror("错误", f"删除模型失败:\n{output}")
        except Exception as e:
            self.model_mgmt_log(f"✗ 删除模型时发生错误: {e}", "ERROR")
            messagebox.showerror("错误", f"删除模型时发生错误:\n{e}")
    
    def model_mgmt_log(self, message, level="INFO"):
        """在模型管理页面输出日志"""
        try:
            # 确保message是字符串，并处理可能的编码问题
            if isinstance(message, bytes):
                message = message.decode('utf-8', errors='replace')
            elif not isinstance(message, str):
                message = str(message)
            
            # 清理可能导致乱码的控制字符
            message = message.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            # 移除控制字符（保留换行符和制表符）
            import re
            message = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', message)
            
            timestamp = time.strftime("%H:%M:%S")
            color_map = {
                "INFO": "black",
                "SUCCESS": "green",
                "WARN": "orange",
                "ERROR": "red"
            }
            color = color_map.get(level, "black")
            
            log_message = f"[{timestamp}] [{level}] {message}\n"
            self.model_mgmt_output.insert(tk.END, log_message)
            self.model_mgmt_output.see(tk.END)
            self.model_mgmt_output.update()
        except Exception as e:
            # 如果日志输出本身出错，至少尝试输出基本信息
            try:
                safe_message = f"[日志输出错误: {str(e)}]"
                self.model_mgmt_output.insert(tk.END, safe_message + "\n")
                self.model_mgmt_output.see(tk.END)
            except:
                pass
    
    def create_help_tab(self, parent):
        """创建帮助Tab"""
        # 主框架
        main_frame = ttk.Frame(parent, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=3)  # 使用指南列权重增加，使其更宽
        main_frame.columnconfigure(1, weight=1)  # 联系方式列权重减少
        main_frame.rowconfigure(0, weight=1)
        
        # === 左侧：使用指南 ===
        left_frame = ttk.Frame(main_frame, padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        left_frame.columnconfigure(0, weight=1)
        
        # 左侧标题
        left_title = tk.Label(
            left_frame,
            text="使用指南",
            font=(self.chinese_font, 20, "bold"),
            fg="#2c3e50"
        )
        left_title.pack(pady=(0, 15))
        
        # 使用指南内容 - 分为两列（可滚动）
        left_guide_frame = ttk.Frame(left_frame)
        left_guide_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        left_guide_frame.columnconfigure(0, weight=1)
        left_guide_frame.columnconfigure(1, weight=1)
        left_guide_frame.rowconfigure(0, weight=1)
        
        # 左列内容
        left_guide_text = """一、论文调研模块使用步骤

【模式选择】
程序支持两种运行模式：
• 在线API模式：使用硅基流动等在线API服务（无需SSH）
• Ollama模式：使用本地或远程Ollama服务（需要SSH）

【在线API模式】
1. 选择API提供商（硅基流动/自定义）
2. 配置API密钥和URL
3. 选择模型（支持自动刷新模型列表）
4. 配置API参数（温度、最大Token等）

【Ollama模式】
1. 配置SSH连接
   • 填写服务器用户名、IP、SSH端口和密码
   • 点击"连接"建立SSH隧道
2. 配置Ollama服务
   • 系统自动检测或安装Ollama
   • 设置本地端口（默认11435）和远程端口（默认11434）
   • 选择模型并点击"刷新"获取最新模型列表

【表格配置】
1. 选择要分析的CSV或Excel文件
2. 点击"刷新列名"自动分析表格列名
3. 设置输出文件名和输出列名（逗号分隔）

【Prompt配置】
1. 在Prompt输入框编写分析提示词
2. 使用 {列名} 引用表格中的列（自动替换）
3. 点击列名标签快速插入到Prompt
4. 点击"添加到Prompt"格式化输出列名为JSON结构

【并发配置】
• 设置并发线程数（建议8-16）
• 设置API延迟时间（秒），避免请求过快
• 启用批处理时，并发设置会被禁用

【批处理模式】
1. 勾选"启用批处理"
2. 选择批处理专用模型（仅支持特定模型）
3. 配置批处理API参数
4. 设置输出目录
5. 使用"检查状态"、"取消任务"、"下载结果"管理任务

【用量监控】
1. 勾选"启用监控"查看实时用量
2. 监控指标：RPM、TPM、总Token数、平均Token/提示
3. 可自定义各项指标的上限（超限会变红提示）

【开始运行】
• 点击"开始"按钮开始分析
• 在运行日志区域查看实时进度
• 可随时点击"停止"按钮中断运行"""
        
        left_guide_text_widget = scrolledtext.ScrolledText(
            left_guide_frame,
            wrap=tk.WORD,
            font=(self.chinese_font, 10),
            fg="#34495e",
            bg="#fafafa",
            relief=tk.FLAT,
            borderwidth=0,
            padx=5,
            pady=5
        )
        left_guide_text_widget.insert(1.0, left_guide_text.strip())
        left_guide_text_widget.config(state=tk.DISABLED)  # 设置为只读
        left_guide_text_widget.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 15))
        
        # 右列内容
        right_guide_text = """二、论文爬虫模块使用步骤

1. 选择数据源
   • 目前支持ArXiv API

2. 选择学科分类
   • 从分类树中选择一个或多个学科分类
   • 支持176个ArXiv学科分类
   • 点击分类项切换选择状态
   • 使用左右箭头按钮批量移动分类

3. 设置时间范围
   • 点击日期输入框旁的日历图标选择日期
   • 程序自动爬取该时间段内的所有论文

4. 设置输出文件
   • 选择输出文件路径
   • 支持CSV和Excel格式
   • 文件名会自动包含分类和时间信息

5. 开始爬取
   • 点击"开始"按钮开始爬取
   • 程序自动遵守ArXiv API限制
   • 在日志区域查看爬取进度

三、模型管理模块

1. 查看模型列表
   • 自动显示已安装的Ollama模型
   • 显示模型大小和最后更新时间

2. 下载模型
   • 输入模型名称（如：deepseek-r1）
   • 点击"下载"按钮下载模型
   • 显示下载进度

3. 删除模型
   • 选择要删除的模型
   • 点击"删除"按钮删除模型

四、注意事项

• 所有配置会自动保存，下次启动时自动恢复
• SSH连接需要确保网络畅通
• 表格文件的第一行必须是列名
• Prompt中的 {列名} 会被自动替换为表格中的实际值
• 输出列名需要与LLM返回的JSON字段对应
• 批处理模式仅支持特定模型，详见批处理配置
• 用量监控基于实际请求时间计算，运行时间不足1分钟时按真实时间计算"""
        
        right_guide_text_widget = scrolledtext.ScrolledText(
            left_guide_frame,
            wrap=tk.WORD,
            font=(self.chinese_font, 10),
            fg="#34495e",
            bg="#fafafa",
            relief=tk.FLAT,
            borderwidth=0,
            padx=5,
            pady=5
        )
        right_guide_text_widget.insert(1.0, right_guide_text.strip())
        right_guide_text_widget.config(state=tk.DISABLED)  # 设置为只读
        right_guide_text_widget.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(15, 0))
        
        # === 右侧：软件介绍和联系方式 ===
        right_frame = ttk.Frame(main_frame, padding="10")
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(10, 0))
        right_frame.columnconfigure(0, weight=1)
        
        # 右侧标题
        
        
        # 联系方式标题
        contact_title = tk.Label(
            right_frame,
            text="联系方式",
            font=(self.chinese_font, 18, "bold"),
            fg="#2c3e50"
        )
        contact_title.pack(pady=(0, 15))
        
        # 联系方式内容
        contact_text = """如有问题或建议，欢迎联系：

胡子谦 中国科学技术大学 信息科学与计算学院
"""
        
        contact_label = tk.Label(
            right_frame,
            text=contact_text.strip(),
            font=(self.chinese_font, 12),
            fg="#34495e",
            justify=tk.LEFT,
            anchor="w"
        )
        contact_label.pack(pady=10)
        
        # 邮箱链接（可点击）
        email_frame = ttk.Frame(right_frame)
        email_frame.pack(pady=10)
        
        email_link = tk.Label(
            email_frame,
            text="huziqian@mail.ustc.edu.cn",
            font=(self.chinese_font, 12, "underline"),
            fg="#3498db",
            cursor="hand2"
        )
        email_link.pack(side=tk.LEFT)
        
        # 绑定点击事件（复制到剪贴板）
        def copy_email(event=None):
            self.root.clipboard_clear()
            self.root.clipboard_append("huziqian@mail.ustc.edu.cn")
            # 显示提示
            tooltip = tk.Toplevel(self.root)
            tooltip.wm_overrideredirect(True)
            if event:
                tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            else:
                tooltip.wm_geometry("+100+100")
            label = tk.Label(tooltip, text="邮箱已复制到剪贴板", bg="yellow", font=(self.chinese_font, 10))
            label.pack()
            tooltip.after(2000, tooltip.destroy)
        
        email_link.bind("<Button-1>", copy_email)
        
        # 检查更新按钮（醒目的样式）
        update_check_frame = ttk.Frame(right_frame)
        update_check_frame.pack(pady=30)
        
        check_update_btn = tk.Button(
            update_check_frame,
            text="检查更新",
            font=(self.chinese_font, 14, "bold"),
            bg="#3498db",
            fg="white",
            activebackground="#2980b9",
            activeforeground="white",
            relief=tk.RAISED,
            bd=2,
            padx=30,
            pady=10,
            cursor="hand2",
            command=self.check_for_updates
        )
        check_update_btn.pack()
        
        # === 更新内容 ===
        update_title = tk.Label(
            right_frame,
            text="更新内容",
            font=(self.chinese_font, 18, "bold"),
            fg="#2c3e50"
        )
        update_title.pack(pady=(30, 15))
        
        update_text = """• 2026-01-02: 初始版本V0.1.0发布
• 加入硅基流动在线API支持
• 加入更新功能
• 加入批处理任务功能
• 加入模型用量监控
"""
        
        update_label = tk.Label(
            right_frame,
            text=update_text.strip(),
            font=(self.chinese_font, 11),
            fg="#34495e",
            justify=tk.LEFT,
            anchor="w"
        )
        update_label.pack(pady=10, padx=10)
        
        # === 待添加内容 ===
        todo_title = tk.Label(
            right_frame,
            text="待添加内容",
            font=(self.chinese_font, 18, "bold"),
            fg="#2c3e50"
        )
        todo_title.pack(pady=(30, 15))
        
        todo_text = """• 支持更多数据源（如openreview等）
• 支持更多在线模型API
• 支持embedding模型
"""
        
        todo_label = tk.Label(
            right_frame,
            text=todo_text.strip(),
            font=(self.chinese_font, 11),
            fg="#34495e",
            justify=tk.LEFT,
            anchor="w"
        )
        todo_label.pack(pady=10, padx=10)
    
    def insert_column_to_prompt(self, column_name):
        """将列名插入到Prompt光标位置"""
        placeholder = f"{{{column_name}}}"
        self.prompt_text.insert(tk.INSERT, placeholder)
        self.prompt_text.focus()
    
    def create_column_labels(self, columns):
        """创建列名标签"""
        # 清除现有标签
        for label in self.column_labels:
            label.destroy()
        self.column_labels.clear()
        
        # 创建新标签
        row = 0
        col = 0
        max_cols = 4  # 每行最多4个标签
        
        for column_name in columns:
            # 创建标签按钮
            label = ttk.Button(
                self.columns_container,
                text=f"{{{column_name}}}",
                command=lambda cn=column_name: self.insert_column_to_prompt(cn),
                width=15
            )
            label.grid(row=row, column=col, padx=5, pady=5, sticky=tk.W)
            self.column_labels.append(label)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        # 更新滚动区域，确保可以滚动
        if hasattr(self, 'columns_canvas'):
            self.columns_canvas.update_idletasks()
            self.columns_canvas.configure(scrollregion=self.columns_canvas.bbox("all"))
    
    def browse_table(self):
        """浏览选择表格文件"""
        filename = filedialog.askopenfilename(
            title="选择表格文件",
            filetypes=[
                ("CSV文件", "*.csv"),
                ("Excel文件", "*.xlsx *.xls"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.table_var.set(filename)
            # 自动分析列名并创建标签
            self.auto_analyze_columns()
    
    def fetch_models_from_ollama(self):
        """从Ollama官网获取模型列表和大小信息"""
        self.log("正在从Ollama官网获取模型列表...", "INFO")
        
        try:
            # 尝试从ollama.com/library获取模型列表
            import re
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                self.log("需要安装 beautifulsoup4: pip install beautifulsoup4 lxml", "ERROR")
                return
            
            # 获取ollama library页面
            url = "https://ollama.com/library"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                self.log(f"无法访问Ollama官网 (状态码: {response.status_code})，尝试从本地API获取", "WARN")
                self.fetch_models_from_local_api()
                return
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 解析模型信息
            models_dict = {}  # {model_name: [size1, size2, ...]}
            
            # 查找所有模型链接，格式通常是 /library/model_name
            import re
            model_links = soup.find_all('a', href=re.compile(r'/library/[^/]+$'))
            
            model_names = set()
            for link in model_links:
                href = link.get('href', '')
                model_name = href.replace('/library/', '').strip()
                if model_name and model_name not in model_names:
                    model_names.add(model_name)
                    models_dict[model_name] = []  # 初始化，稍后填充
            
            if not model_names:
                # 如果解析失败，尝试从API获取
                self.log("网页解析失败，尝试从本地Ollama API获取...", "INFO")
                self.fetch_models_from_local_api()
                return
            
            # 更新模型下拉框（先更新，让用户可以看到模型列表）
            model_list = sorted(model_names)
            if hasattr(self, 'model_combo') and self.model_combo:
                self.model_combo['values'] = model_list
            
            self.log(f"✓ 已获取 {len(model_list)} 个模型", "SUCCESS")
            self.log("正在获取各模型的大小信息（后台进行，不影响使用）...", "INFO")
            
            # 并发获取每个模型的大小信息
            self._fetch_model_sizes_concurrently(model_names, models_dict)
            
            # 保存模型信息到缓存
            self.ollama_models_cache = models_dict
            
            # 保存缓存到文件
            self.save_models_cache()
            
            # 如果当前选择的模型有大小选项，更新大小下拉框
            self.on_model_selected()
            
        except Exception as e:
            self.log(f"获取模型列表失败: {e}，尝试从本地API获取", "WARN")
            import traceback
            self.log(f"详细错误: {traceback.format_exc()[:200]}", "WARN")
            # 尝试从本地API获取
            self.fetch_models_from_local_api()
    
    def _fetch_model_sizes_concurrently(self, model_names, models_dict):
        """并发获取所有模型的大小信息"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import re
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        def fetch_single_model_size(model_name):
            """获取单个模型的大小信息"""
            try:
                url = f"https://ollama.com/library/{model_name}"
                response = requests.get(url, headers=headers, timeout=8)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    sizes = []
                    
                    # 查找大小信息
                    text_content = soup.get_text()
                    size_pattern = re.compile(r'\b(\d+(?:\.\d+)?)\s*(b|B)\b', re.IGNORECASE)
                    matches = size_pattern.findall(text_content)
                    
                    for match in matches:
                        size_str = f"{match[0]}{match[1].lower()}"
                        if size_str not in sizes:
                            sizes.append(size_str)
                    
                    # 查找链接中的大小信息（如 /library/llama3:7b）
                    links = soup.find_all('a', href=re.compile(rf'/library/{re.escape(model_name)}:\d+'))
                    for link in links:
                        href = link.get('href', '')
                        if ':' in href:
                            size_part = href.split(':')[-1]
                            if size_part not in sizes:
                                sizes.append(size_part)
                    
                    return model_name, sizes
            except Exception as e:
                # 静默失败，不影响其他模型
                pass
            return model_name, []
        
        # 使用线程池并发获取（最多10个并发，避免过多请求）
        completed = 0
        total = len(model_names)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_model = {executor.submit(fetch_single_model_size, name): name for name in model_names}
            
            for future in as_completed(future_to_model):
                try:
                    model_name, sizes = future.result()
                    models_dict[model_name] = sizes
                    completed += 1
                    # 每完成10个模型，更新一次日志并保存缓存
                    if completed % 10 == 0 or completed == total:
                        self.log(f"已获取 {completed}/{total} 个模型的大小信息...", "INFO")
                        # 定期保存缓存，避免数据丢失
                        self.ollama_models_cache.update(models_dict)
                        self.save_models_cache()
                except Exception:
                    pass
        
        # 最终保存缓存
        self.ollama_models_cache.update(models_dict)
        self.save_models_cache()
        self.log(f"✓ 已完成所有模型大小信息的获取", "SUCCESS")
    
    def fetch_models_from_local_api(self):
        """从本地Ollama API获取模型列表（如果SSH隧道已建立）"""
        try:
            local_port = int(self.local_port_var.get())
            api_url = f"http://localhost:{local_port}/api/tags"
            response = requests.get(api_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                models = []
                if 'models' in data:
                    for model in data['models']:
                        model_name = model.get('name', '')
                        if model_name:
                            # 提取基础模型名（去掉标签）
                            base_name = model_name.split(':')[0]
                            if base_name not in models:
                                models.append(base_name)
                
                if models:
                    # 更新模型下拉框
                    model_list = sorted(models)
                    if hasattr(self, 'model_combo') and self.model_combo:
                        self.model_combo['values'] = model_list
                    self.log(f"✓ 从本地API获取了 {len(model_list)} 个模型", "SUCCESS")
        except Exception as e:
            self.log(f"从本地API获取模型列表失败: {e}", "WARN")
    
    def on_model_selected(self):
        """当选择模型时，更新模型大小选项（从缓存读取，不进行网络请求）"""
        model_name = self.model_var.get()
        if not model_name or not self.model_size_combo:
            return
        
        # 确保缓存已初始化
        if not hasattr(self, 'ollama_models_cache'):
            self.ollama_models_cache = {}
        
        # 优先从缓存读取大小信息
        sizes = self.ollama_models_cache.get(model_name, [])
        
        # 如果缓存中没有，尝试从本地API获取
        if not sizes:
            try:
                local_port = int(self.local_port_var.get())
                api_url = f"http://localhost:{local_port}/api/tags"
                response = requests.get(api_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if 'models' in data:
                        for model in data['models']:
                            model_full_name = model.get('name', '')
                            if model_full_name.startswith(model_name + ':'):
                                size = model_full_name.split(':')[1] if ':' in model_full_name else ''
                                if size and size not in sizes:
                                    sizes.append(size)
                        # 保存到缓存
                        if sizes:
                            self.ollama_models_cache[model_name] = sizes
                            # 保存缓存到文件
                            self.save_models_cache()
            except:
                pass
        
        # 更新大小下拉框
        if sizes:
            self.model_size_combo['values'] = sorted(sizes, key=lambda x: (len(x), x))
            self.model_size_combo['state'] = 'readonly'
            if sizes:
                self.model_size_var.set(sizes[0])  # 默认选择第一个
        else:
            self.model_size_combo['values'] = []
            self.model_size_combo['state'] = 'disabled'
            self.model_size_var.set("")
    
    def browse_output_file(self):
        """浏览选择输出文件夹"""
        # 获取当前输入的文件名（可能是完整路径或只有文件名）
        current_value = self.output_file_var.get().strip()
        if current_value:
            # 如果包含路径，提取文件名；否则直接使用
            if os.path.dirname(current_value):
                default_filename = os.path.basename(current_value)
            else:
                default_filename = current_value
        else:
            default_filename = "调研报告.csv"
        
        # 选择文件夹
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            # 将文件夹路径和文件名组合
            full_path = os.path.join(folder, default_filename)
            self.output_file_var.set(full_path)
    
    def add_output_columns_to_prompt(self):
        """将输出列名添加到Prompt中"""
        output_cols = self.output_columns_var.get().strip()
        if not output_cols:
            messagebox.showwarning("警告", "请输入输出列名")
            return
        
        # 解析列名（支持逗号分隔）
        columns = [col.strip() for col in output_cols.split(',') if col.strip()]
        
        # 构建JSON格式的输出列名说明
        json_format = "{\n"
        for i, col in enumerate(columns):
            json_format += f'    "{col}": "该字段的描述",'
            if i < len(columns) - 1:
                json_format += "\n"
        json_format += "\n}"
        
        # 添加到Prompt末尾
        current_prompt = self.prompt_text.get(1.0, tk.END)
        if not current_prompt.strip().endswith('\n'):
            self.prompt_text.insert(tk.END, "\n")
        
        self.prompt_text.insert(tk.END, f"\n请按照以下格式返回JSON（包含以下字段）：\n{json_format}\n")
        self.prompt_text.see(tk.END)
        self.prompt_text.focus()
    
    def auto_analyze_columns(self):
        """自动分析表格列名并创建标签"""
        table_path = self.table_var.get()
        if not table_path or not os.path.exists(table_path):
            return
        
        try:
            # 读取CSV文件 - 第一行就是列名，不需要跳过
            if table_path.endswith('.csv'):
                with open(table_path, 'r', encoding='utf-8') as f:
                    # 只读取第一行作为列名
                    first_line = f.readline().strip()
                    if not first_line:
                        self.log("⚠ CSV文件第一行为空", "WARN")
                        return
                    
                    # 使用csv.reader解析第一行
                    reader = csv.reader([first_line])
                    columns = next(reader)
                    # 清理列名（去除前后空格）
                    columns = [col.strip() for col in columns if col.strip()]
            else:
                # Excel文件 - 第一行是列名，skiprows=0表示不跳过
                import pandas as pd
                df = pd.read_excel(table_path, skiprows=0, nrows=0)
                columns = df.columns.tolist()
            
            if columns:
                self.log(f"✓ 检测到 {len(columns)} 个列: {', '.join(columns)}", "SUCCESS")
                # 创建列名标签
                self.create_column_labels(columns)
            else:
                self.log("⚠ 无法读取表格列名，请检查文件格式", "WARN")
        except Exception as e:
            self.log(f"✗ 读取表格列名失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
    
    def preview_columns(self):
        """预览表格列名（显示消息框）"""
        table_path = self.table_var.get()
        if not table_path or not os.path.exists(table_path):
            messagebox.showwarning("警告", "请先选择有效的表格文件")
            return
        
        try:
            # 读取CSV文件 - 第一行就是列名
            if table_path.endswith('.csv'):
                with open(table_path, 'r', encoding='utf-8') as f:
                    # 只读取第一行作为列名
                    first_line = f.readline().strip()
                    if not first_line:
                        messagebox.showwarning("警告", "CSV文件第一行为空")
                        return
                    
                    # 使用csv.reader解析第一行
                    reader = csv.reader([first_line])
                    columns = next(reader)
                    # 清理列名（去除前后空格）
                    columns = [col.strip() for col in columns if col.strip()]
            else:
                # Excel文件 - 第一行是列名
                import pandas as pd
                df = pd.read_excel(table_path, skiprows=0, nrows=0)
                columns = df.columns.tolist()
            
            if columns:
                columns_str = ", ".join(columns)
                messagebox.showinfo("表格列名", f"表格包含以下列：\n\n{columns_str}\n\n可以在Prompt中使用 {{列名}} 来引用这些列")
            else:
                messagebox.showwarning("警告", "无法读取表格列名，请检查文件格式")
        except Exception as e:
            messagebox.showerror("错误", f"读取表格失败：{e}")
            import traceback
            messagebox.showerror("详细错误", traceback.format_exc())
    
    def log(self, message, level="INFO"):
        """在输出区域添加日志"""
        try:
            # 确保message是字符串，并处理可能的编码问题
            if isinstance(message, bytes):
                message = message.decode('utf-8', errors='replace')
            elif not isinstance(message, str):
                message = str(message)
            
            # 清理可能导致乱码的控制字符
            message = message.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            # 移除控制字符（保留换行符和制表符）
            import re
            message = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', message)
            
            timestamp = time.strftime("%H:%M:%S")
            log_message = f"[{timestamp}] [{level}] {message}\n"
            
            self.output_text.insert(tk.END, log_message)
            self.output_text.see(tk.END)
            self.root.update_idletasks()
        except Exception as e:
            # 如果日志输出本身出错，至少尝试输出基本信息
            try:
                safe_message = f"[日志输出错误: {str(e)}]"
                self.output_text.insert(tk.END, safe_message + "\n")
                self.output_text.see(tk.END)
            except:
                pass
    
    def clear_output(self):
        """清空输出区域"""
        self.output_text.delete(1.0, tk.END)
        self.progress_var.set("就绪")
    
    def browse_crawler_output(self):
        """浏览选择爬虫输出文件夹"""
        # 获取当前输入的文件名（可能是完整路径或只有文件名）
        current_value = self.crawler_output_file_var.get().strip()
        if current_value:
            # 如果包含路径，提取文件名；否则直接使用
            if os.path.dirname(current_value):
                default_filename = os.path.basename(current_value)
            else:
                default_filename = current_value
        else:
            default_filename = "arxiv_papers.csv"
        
        # 选择文件夹
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            # 将文件夹路径和文件名组合
            full_path = os.path.join(folder, default_filename)
            self.crawler_output_file_var.set(full_path)
    
    def crawler_log(self, message, level="INFO"):
        """爬虫日志输出"""
        try:
            # 确保message是字符串，并处理可能的编码问题
            if isinstance(message, bytes):
                message = message.decode('utf-8', errors='replace')
            elif not isinstance(message, str):
                message = str(message)
            
            # 清理可能导致乱码的控制字符
            message = message.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
            # 移除控制字符（保留换行符和制表符）
            import re
            message = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', message)
            
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"[{timestamp}] {message}\n"
            self.crawler_output_text.insert(tk.END, log_message)
            self.crawler_output_text.see(tk.END)
            self.root.update()
        except Exception as e:
            # 如果日志输出本身出错，至少尝试输出基本信息
            try:
                safe_message = f"[日志输出错误: {str(e)}]"
                self.crawler_output_text.insert(tk.END, safe_message + "\n")
                self.crawler_output_text.see(tk.END)
            except:
                pass
    
    def clear_crawler_output(self):
        """清空爬虫输出"""
        self.crawler_output_text.delete(1.0, tk.END)
    
    def start_crawler(self):
        """开始爬取论文"""
        if self.crawler_is_running:
            return
        
        self.crawler_is_running = True
        self.crawler_start_button.config(state=tk.DISABLED)
        self.crawler_stop_button.config(state=tk.NORMAL)
        
        # 在新线程中运行爬虫
        thread = threading.Thread(target=self._crawl_thread, daemon=True)
        thread.start()
    
    def stop_crawler(self):
        """停止爬取"""
        self.crawler_is_running = False
        self.crawler_start_button.config(state=tk.NORMAL)
        self.crawler_stop_button.config(state=tk.DISABLED)
        self.crawler_log("用户中断爬取", "WARN")
    
    def _crawl_thread(self):
        """爬虫线程"""
        try:
            source = self.crawler_source_var.get()
            if source == "arxiv":
                self.crawl_arxiv()
            else:
                self.crawler_log(f"不支持的数据源: {source}", "ERROR")
        except Exception as e:
            self.crawler_log(f"爬取过程出错: {e}", "ERROR")
            import traceback
            self.crawler_log(traceback.format_exc(), "ERROR")
        finally:
            self.crawler_is_running = False
            self.crawler_start_button.config(state=tk.NORMAL)
            self.crawler_stop_button.config(state=tk.DISABLED)
    
    def crawl_arxiv(self):
        """爬取ArXiv论文"""
        try:
            import arxiv
            from datetime import datetime, timedelta
            
            # 获取选中的分类（直接使用分类代码）
            if not self.category_selected_items:
                self.crawler_log("✗ 请至少选择一个学科分类", "ERROR")
                return
            
            # category_selected_items 现在直接存储分类代码
            selected_categories = [cat_code for cat_code in self.category_selected_items if cat_code in self.all_categories]
            
            if not selected_categories:
                self.crawler_log("✗ 请至少选择一个有效的学科分类", "ERROR")
                return
            
            # 备用：如果all_categories未定义，使用ARXIV_CATEGORIES
            if not hasattr(self, 'all_categories'):
                ARXIV_CATEGORIES = {
                "astro-ph": "天体物理",
                "astro-ph.CO": "宇宙学与非规则天体物理学",
                "astro-ph.EP": "地球与行星天体物理学",
                "astro-ph.GA": "星系的天体物理学",
                "astro-ph.HE": "高能天体物理现象",
                "astro-ph.IM": "天体物理学的仪器和方法",
                "astro-ph.SR": "太阳与恒星天体物理学",
                "cond-mat.dis-nn": "无序系统与神经网络",
                "cond-mat.mes-hall": "中尺度和纳米尺度物理学",
                "cond-mat.mtrl-sci": "材料科学",
                "cond-mat.other": "其他凝聚态",
                "cond-mat.quant-gas": "量子气体",
                "cond-mat.soft": "软凝聚物",
                "cond-mat.stat-mech": "统计力学",
                "cond-mat.str-el": "强关联电子",
                "cond-mat.supr-con": "超导现象",
                "cs.AI": "人工智能",
                "cs.AR": "硬件架构",
                "cs.CC": "计算复杂性",
                "cs.CE": "计算工程，金融和科学",
                "cs.CG": "计算几何",
                "cs.CL": "计算与语言",
                "cs.CR": "密码学与保安",
                "cs.CV": "计算机视觉与模式识别",
                "cs.CY": "电脑与社会",
                "cs.DB": "数据库",
                "cs.DC": "分布式、并行和集群计算",
                "cs.DL": "数字仓库",
                "cs.DM": "离散数学",
                "cs.DS": "数据结构和算法",
                "cs.ET": "新兴科技",
                "cs.FL": "形式语言与自动机理论",
                "cs.GL": "一般文学",
                "cs.GR": "图形",
                "cs.GT": "计算机科学与博弈论",
                "cs.HC": "人机交互",
                "cs.IR": "信息检索",
                "cs.IT": "信息理论",
                "cs.LG": "学习",
                "cs.LO": "计算机科学中的逻辑",
                "cs.MA": "多代理系统",
                "cs.MM": "多媒体",
                "cs.MS": "数学软件",
                "cs.NA": "数值分析",
                "cs.NE": "神经和进化计算",
                "cs.NI": "网络与互联网架构",
                "cs.OH": "其他计算机科学",
                "cs.OS": "操作系统",
                "cs.PF": "性能",
                "cs.PL": "编程语言",
                "cs.RO": "机器人技术",
                "cs.SC": "符号计算",
                "cs.SD": "声音",
                "cs.SE": "软件工程",
                "cs.SI": "社会和信息网络",
                "cs.SY": "系统及控制",
                "econ.EM": "计量经济学",
                "eess.AS": "音频及语音处理",
                "eess.IV": "图像和视频处理",
                "eess.SP": "信号处理",
                "gr-qc": "广义相对论和量子宇宙学",
                "hep-ex": "高能物理实验",
                "hep-lat": "高能物理-晶格",
                "hep-ph": "高能物理-现象学",
                "hep-th": "高能物理理论",
                "math.AC": "交换代数",
                "math.AG": "代数几何",
                "math.AP": "偏微分方程分析",
                "math.AT": "代数拓扑",
                "math.CA": "传统分析和微分方程",
                "math.CO": "组合数学",
                "math.CT": "范畴理论",
                "math.CV": "复杂变量",
                "math.DG": "微分几何",
                "math.DS": "动力系统",
                "math.FA": "功能分析",
                "math.GM": "普通数学",
                "math.GN": "点集拓扑学",
                "math.GR": "群论",
                "math.GT": "几何拓扑学",
                "math.HO": "历史和概述",
                "math.IT": "信息理论",
                "math.KT": "K 理论与同调",
                "math.LO": "逻辑",
                "math.MG": "度量几何学",
                "math.MP": "数学物理",
                "math.NA": "数值分析",
                "math.NT": "数论",
                "math.OA": "算子代数",
                "math.OC": "优化和控制",
                "math.PR": "概率",
                "math.QA": "量子代数",
                "math.RA": "环与代数",
                "math.RT": "表示论",
                "math.SG": "辛几何",
                "math.SP": "光谱理论",
                "math.ST": "统计学理论",
                "math-ph": "数学物理",
                "nlin.AO": "适应与自组织系统",
                "nlin.CD": "混沌动力学",
                "nlin.CG": "元胞自动机与格子气体",
                "nlin.PS": "模式形成与孤子",
                "nlin.SI": "严格可解可积系统",
                "nucl-ex": "核试验",
                "nucl-th": "核理论",
                "physics.acc-ph": "加速器物理学",
                "physics.ao-ph": "大气和海洋物理学",
                "physics.app-ph": "应用物理学",
                "physics.atm-clus": "原子和分子团簇",
                "physics.atom-ph": "原子物理学",
                "physics.bio-ph": "生物物理学",
                "physics.chem-ph": "化学物理",
                "physics.class-ph": "经典物理学",
                "physics.comp-ph": "计算物理学",
                "physics.data-an": "数据分析、统计和概率",
                "physics.ed-ph": "物理教育",
                "physics.flu-dyn": "流体动力学",
                "physics.gen-ph": "普通物理",
                "physics.geo-ph": "地球物理学",
                "physics.hist-ph": "物理学的历史与哲学",
                "physics.ins-det": "仪器和探测器",
                "physics.med-ph": "医学物理学",
                "physics.optics": "光学",
                "physics.plasm-ph": "等离子体物理",
                "physics.pop-ph": "大众物理",
                "physics.soc-ph": "物理学与社会",
                "physics.space-ph": "空间物理学",
                "q-bio.BM": "生物分子",
                "q-bio.CB": "细胞行为",
                "q-bio.GN": "基因组学",
                "q-bio.MN": "分子网络",
                "q-bio.NC": "神经元与认知",
                "q-bio.OT": "其他定量生物学",
                "q-bio.PE": "种群与进化",
                "q-bio.QM": "定量方法",
                "q-bio.SC": "亚细胞突起",
                "q-bio.TO": "组织和器官",
                "q-fin.CP": "金融工程",
                "q-fin.EC": "经济学",
                "q-fin.GN": "财务概述",
                "q-fin.MF": "数学金融",
                "q-fin.PM": "投资组合管理",
                "q-fin.PR": "证券定价",
                "q-fin.RM": "风险管理",
                "q-fin.ST": "金融统计",
                "q-fin.TR": "交易与市场微观结构",
                "quant-ph": "量子物理学",
                "stat.AP": "应用",
                "stat.CO": "计算",
                "stat.ME": "方法论",
                "stat.ML": "机器学习",
                "stat.OT": "其他统计学",
                "stat.TH": "统计学理论"
            }
            
            start_date = self.crawler_start_date_var.get()
            end_date = self.crawler_end_date_var.get()
            
            # 自动生成输出文件名（包含类别和时间）
            output_file = self._generate_crawler_filename(selected_categories, start_date, end_date)
            self.crawler_output_file_var.set(output_file)
            
            self.crawler_log(f"开始爬取ArXiv论文...")
            self.crawler_log(f"学科分类: {', '.join(selected_categories)}")
            self.crawler_log(f"时间区间: {start_date} 至 {end_date}")
            self.crawler_log(f"将爬取所有符合条件的论文（遵守API限制：每次2000条，间隔3秒）")
            
            # 构建多分类查询（使用OR连接）
            if len(selected_categories) == 1:
                base_query = f"cat:{selected_categories[0]}"
            else:
                # 多个分类使用OR连接
                cat_queries = [f"cat:{cat}" for cat in selected_categories]
                base_query = " OR ".join(cat_queries)
                base_query = f"({base_query})"
            
            # 解析日期
            start_dt = None
            end_dt = None
            if start_date and end_date:
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                except ValueError as e:
                    self.crawler_log(f"日期格式错误: {e}，将忽略时间区间", "WARN")
            
            # API限制：每次最多2000条，间隔3秒，硬限制50000条
            BATCH_SIZE = 2000
            API_DELAY = 3  # 秒
            MAX_TOTAL = 50000
            
            papers = []
            total_count = 0
            batch_num = 0
            
            # 如果超过50000条，需要按时间分段查询
            if start_dt and end_dt:
                days_diff = (end_dt - start_dt).days
                # 估算是否需要分段（假设每天平均论文数，这里用保守估计）
                # 如果时间跨度很大，可能需要分段
                if days_diff > 365:  # 超过1年，考虑分段
                    self.crawler_log(f"时间跨度较大（{days_diff}天），将按时间段分段查询", "INFO")
                    # 按月份分段
                    current_start = start_dt
                    while current_start < end_dt and total_count < MAX_TOTAL:
                        if not self.crawler_is_running:
                            break
                        
                        # 计算当前段的结束日期（一个月后或结束日期）
                        current_end = min(current_start + timedelta(days=30), end_dt)
                        
                        # 构建当前时间段的查询
                        query = base_query
                        query += f" AND submittedDate:[{current_start.strftime('%Y%m%d')}000000 TO {current_end.strftime('%Y%m%d')}235959]"
                        
                        self.crawler_log(f"查询时间段: {current_start.strftime('%Y-%m-%d')} 至 {current_end.strftime('%Y-%m-%d')}")
                        
                        # 分批获取当前时间段的数据
                        batch_papers = self._fetch_arxiv_batch(query, BATCH_SIZE, API_DELAY, MAX_TOTAL - total_count)
                        papers.extend(batch_papers)
                        total_count += len(batch_papers)
                        
                        if len(batch_papers) >= MAX_TOTAL - total_count:
                            self.crawler_log(f"已达到最大限制（{MAX_TOTAL}条），停止查询", "WARN")
                            break
                        
                        current_start = current_end + timedelta(days=1)
                else:
                    # 时间跨度不大，直接查询
                    query = base_query
                    if start_dt and end_dt:
                        query += f" AND submittedDate:[{start_dt.strftime('%Y%m%d')}000000 TO {end_dt.strftime('%Y%m%d')}235959]"
                    
                    self.crawler_log(f"查询语句: {query}")
                    papers = self._fetch_arxiv_batch(query, BATCH_SIZE, API_DELAY, MAX_TOTAL)
                    total_count = len(papers)
            else:
                # 没有时间限制，直接查询
                query = base_query
                self.crawler_log(f"查询语句: {query}")
                papers = self._fetch_arxiv_batch(query, BATCH_SIZE, API_DELAY, MAX_TOTAL)
                total_count = len(papers)
            
            if not self.crawler_is_running:
                self.crawler_log("爬取已中断", "WARN")
                if papers:
                    self._save_crawler_results(papers, output_file)
                return
            
            # 保存结果
            if papers:
                self._save_crawler_results(papers, output_file)
                self.crawler_log(f"✓ 成功爬取 {len(papers)} 篇论文", "SUCCESS")
                self.crawler_log(f"✓ 结果已保存到: {output_file}", "SUCCESS")
            else:
                self.crawler_log("未找到符合条件的论文", "WARN")
                
        except ImportError:
            self.crawler_log("✗ 未安装arxiv库，请运行: pip install arxiv", "ERROR")
        except Exception as e:
            self.crawler_log(f"✗ 爬取失败: {e}", "ERROR")
            import traceback
            self.crawler_log(traceback.format_exc(), "ERROR")
    
    def _fetch_arxiv_batch(self, query, batch_size, api_delay, max_total):
        """分批获取ArXiv论文（遵守API限制）"""
        import arxiv
        
        papers = []
        offset = 0
        batch_num = 0
        
        while offset < max_total:
            if not self.crawler_is_running:
                break
            
            # 计算当前批次的大小
            current_batch_size = min(batch_size, max_total - offset)
            
            batch_num += 1
            self.crawler_log(f"第 {batch_num} 批查询（{current_batch_size} 条）...")
            
            try:
                # 创建搜索对象
                search = arxiv.Search(
                    query=query,
                    max_results=current_batch_size,
                    sort_by=arxiv.SortCriterion.SubmittedDate,
                    sort_order=arxiv.SortOrder.Descending
                )
                
                batch_count = 0
                for paper in search.results():
                    if not self.crawler_is_running:
                        break
                    
                    batch_count += 1
                    paper_data = {
                        "id": paper.entry_id.split('/')[-1],
                        "title": paper.title,
                        "authors": ", ".join([author.name for author in paper.authors]),
                        "summary": paper.summary,
                        "published": paper.published.strftime("%Y-%m-%d") if paper.published else "",
                        "updated": paper.updated.strftime("%Y-%m-%d") if paper.updated else "",
                        "categories": ", ".join(paper.categories),
                        "pdf_url": paper.pdf_url,
                        "primary_category": paper.primary_category if hasattr(paper, 'primary_category') else ""
                    }
                    papers.append(paper_data)
                
                self.crawler_log(f"第 {batch_num} 批完成，获取 {batch_count} 篇论文（累计: {len(papers)} 篇）", "SUCCESS")
                
                # 如果获取的数量少于批次大小，说明已经获取完所有结果
                if batch_count < current_batch_size:
                    break
                
                offset += batch_count
                
                # 如果还没达到限制，等待API延迟
                if offset < max_total and batch_count == current_batch_size:
                    self.crawler_log(f"等待 {api_delay} 秒后继续...", "INFO")
                    time.sleep(api_delay)
                    
            except Exception as e:
                self.crawler_log(f"第 {batch_num} 批查询出错: {e}", "WARN")
                # 即使出错，也保存已获取的论文
                break
        
        return papers
    
    def _open_calendar(self, date_var, entry_widget):
        """打开日历选择器"""
        try:
            from tkcalendar import Calendar
            from datetime import datetime
            
            # 创建日历窗口
            cal_window = tk.Toplevel(self.root)
            cal_window.title("选择日期")
            cal_window.transient(self.root)
            cal_window.grab_set()
            
            # 默认使用今天的日期
            today = datetime.now()
            
            # 创建日历控件（默认显示今天）
            cal = Calendar(
                cal_window,
                selectmode='day',
                year=today.year,
                month=today.month,
                day=today.day,
                date_pattern='y-mm-dd'
            )
            cal.pack(pady=10, padx=10)
            
            # 如果输入框中有日期，则选中该日期（但日历仍显示今天）
            current_date_str = date_var.get()
            try:
                current_date = datetime.strptime(current_date_str, "%Y-%m-%d")
                # 设置选中的日期为输入框中的日期
                cal.selection_set(current_date)
            except:
                # 如果解析失败，默认选中今天
                cal.selection_set(today)
            
            # 标记今日（使用上面已定义的today变量）
            try:
                cal.calevent_create(
                    today,
                    '今日',
                    'today'
                )
                cal.tag_config('today', background='lightblue', foreground='black')
            except:
                # 如果calevent_create不可用，使用其他方法标记
                pass
            
            # 确定按钮
            def confirm_date():
                selected_date = cal.selection_get()
                date_var.set(selected_date.strftime("%Y-%m-%d"))
                cal_window.destroy()
            
            # 取消按钮
            def cancel_date():
                cal_window.destroy()
            
            button_frame = ttk.Frame(cal_window)
            button_frame.pack(pady=10)
            
            ttk.Button(button_frame, text="确定", command=confirm_date, width=10).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="取消", command=cancel_date, width=10).pack(side=tk.LEFT, padx=5)
            
            # 添加"今日"标签
            today_label = ttk.Label(cal_window, text=f"今日: {today.strftime('%Y-%m-%d')}", 
                                   font=(self.chinese_font, 9), foreground="blue")
            today_label.pack(pady=(0, 5))
            
            # 居中显示窗口
            cal_window.update_idletasks()
            width = cal_window.winfo_width()
            height = cal_window.winfo_height()
            x = (cal_window.winfo_screenwidth() // 2) - (width // 2)
            y = (cal_window.winfo_screenheight() // 2) - (height // 2)
            cal_window.geometry(f'{width}x{height}+{x}+{y}')
            
        except ImportError:
            messagebox.showerror("错误", "需要安装 tkcalendar 库：\npip install tkcalendar")
        except Exception as e:
            messagebox.showerror("错误", f"打开日历失败: {e}")
    
    
    def _generate_crawler_filename(self, categories, start_date, end_date):
        """根据选择的分类和时间自动生成文件名"""
        import os
        from datetime import datetime
        
        # 获取用户指定的基础路径（如果有）
        base_path = self.crawler_output_file_var.get()
        if base_path and os.path.dirname(base_path):
            base_dir = os.path.dirname(base_path)
        else:
            base_dir = ""
        
        # 生成分类部分（最多显示3个，超过用数字表示）
        if len(categories) == 1:
            cat_part = categories[0].replace('.', '_').replace('-', '_')
        elif len(categories) <= 3:
            cat_part = "_".join([cat.replace('.', '_').replace('-', '_') for cat in categories[:3]])
        else:
            cat_part = f"{categories[0].replace('.', '_').replace('-', '_')}_等{len(categories)}类"
        
        # 生成时间部分
        try:
            if start_date and end_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                time_part = f"{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}"
            elif start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                time_part = f"{start_dt.strftime('%Y%m%d')}_至今"
            elif end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                time_part = f"至{end_dt.strftime('%Y%m%d')}"
            else:
                time_part = "全部时间"
        except:
            time_part = "全部时间"
        
        # 组合文件名
        filename = f"arxiv_{cat_part}_{time_part}.csv"
        
        # 如果用户指定了目录，使用该目录
        if base_dir:
            filename = os.path.join(base_dir, filename)
        
        return filename
    
    def _save_crawler_results(self, papers, output_file):
        """保存爬虫结果"""
        try:
            import pandas as pd
            df = pd.DataFrame(papers)
            
            if output_file.endswith('.xlsx'):
                df.to_excel(output_file, index=False, engine='openpyxl')
            else:
                df.to_csv(output_file, index=False, encoding='utf-8-sig')
        except Exception as e:
            self.crawler_log(f"保存文件失败: {e}", "ERROR")
            raise
    
    def check_port_available(self, port):
        """检查本地端口是否可用"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result != 0
    
    def kill_process_on_port(self, port):
        """终止使用指定端口的进程（使用SSH命令）"""
        try:
            # 使用SSH命令在远程服务器上终止进程
            # 注意：这个方法只能终止远程服务器上的进程，不能终止本地进程
            # 如果需要终止本地进程，需要通过SSH在远程服务器上执行命令
            self.log(f"注意: 端口释放功能需要SSH连接，当前仅支持远程服务器端口管理", "INFO")
        except Exception as e:
            self.log(f"释放端口 {port} 失败: {e}", "WARN")
    
    def check_ssh_connection(self):
        """检查SSH连接是否已建立"""
        local_port = int(self.local_port_var.get())
        # 检查是否已经有可用的SSH隧道（直接测试端口是否可访问Ollama）
        try:
            test_url = f"http://localhost:{local_port}/api/tags"
            response = requests.get(test_url, timeout=2)
            if response.status_code == 200:
                return True
        except:
            pass
        # 检查是否有paramiko客户端
        if self.ssh_client:
            try:
                # 尝试执行一个简单命令来测试连接
                transport = self.ssh_client.get_transport()
                if transport and transport.is_active():
                    return True
            except:
                pass
        return False
    
    def update_ssh_status(self):
        """更新SSH连接状态显示"""
        if self.check_ssh_connection():
            self.ssh_status_label.config(text="已连接", foreground="green")
            self.connect_btn.config(state="disabled")
            self.disconnect_btn.config(state="normal")
            # 启用需要SSH连接的按钮（只更新Ollama按钮，且只在Ollama模式下）
            if hasattr(self, 'ollama_start_button') and self.ollama_start_button is not None:
                if self.api_mode_var.get() == "ollama":
                    self.ollama_start_button.config(state="normal")
            if hasattr(self, 'refresh_model_btn'):
                self.refresh_model_btn.config(state="normal")
        else:
            self.ssh_status_label.config(text="未连接", foreground="gray")
            self.connect_btn.config(state="normal")
            self.disconnect_btn.config(state="disabled")
            # 禁用需要SSH连接的按钮（只更新Ollama按钮，且只在Ollama模式下）
            if hasattr(self, 'ollama_start_button') and self.ollama_start_button is not None:
                if self.api_mode_var.get() == "ollama":
                    self.ollama_start_button.config(state="disabled")
            if hasattr(self, 'refresh_model_btn'):
                self.refresh_model_btn.config(state="disabled")
    
    def connect_ssh(self):
        """手动建立SSH连接"""
        # 检查IP白名单
        host = self.host_var.get().strip()
        if host not in self.allowed_ips:
            # 全局警告计数（不区分IP）
            self.ip_warning_count += 1
            
            if self.ip_warning_count == 1:
                # 第一次警告，只显示弹窗
                messagebox.showerror("非法IP", f"IP地址 {host} 不在允许列表中！\n\n这是第一次警告，再次尝试将锁定软件。")
                return False
            else:
                # 第二次及以后，立即锁定软件
                messagebox.showerror("非法IP", f"IP地址 {host} 不在允许列表中！\n\n软件已被锁定！")
                self.lock_application()
                return False
        
        # 如果已连接，先关闭当前连接并释放端口
        if self.check_ssh_connection():
            self.log("检测到已有SSH连接，先关闭当前连接...", "INFO")
            self.close_ssh_tunnel()
            # 使用update_ssh_status统一更新所有按钮状态
            self.update_ssh_status()
            # 等待一下，确保端口释放
            time.sleep(1)
        
        # 在新线程中建立连接，避免阻塞UI
        def connect_thread():
            try:
                self.connect_btn.config(state="disabled")
                self.ssh_status_label.config(text="连接中...", foreground="blue")
                if self.establish_ssh_tunnel():
                    self.log("✓ SSH连接已建立", "SUCCESS")
                    # 使用update_ssh_status统一更新所有按钮状态
                    self.update_ssh_status()
                else:
                    self.log("✗ SSH连接失败", "ERROR")
                    # 使用update_ssh_status统一更新所有按钮状态
                    self.update_ssh_status()
            except Exception as e:
                self.log(f"✗ SSH连接出错: {e}", "ERROR")
                # 使用update_ssh_status统一更新所有按钮状态
                self.update_ssh_status()
        
        thread = threading.Thread(target=connect_thread, daemon=True)
        thread.start()
        return True
    
    def disconnect_ssh(self):
        """手动断开SSH连接"""
        try:
            self.log("正在断开SSH连接...", "INFO")
            self.close_ssh_tunnel()
            self.log("✓ SSH连接已断开", "SUCCESS")
            # 使用update_ssh_status统一更新所有按钮状态
            self.update_ssh_status()
        except Exception as e:
            self.log(f"✗ 断开SSH连接时出错: {e}", "ERROR")
            # 即使出错也要更新状态
            self.update_ssh_status()
    
    def check_lock_status(self):
        """检查是否有锁定状态文件"""
        return os.path.exists(LOCK_FILE)
    
    def save_lock_status(self):
        """保存锁定状态到文件"""
        try:
            with open(LOCK_FILE, 'w', encoding='utf-8') as f:
                f.write("locked")
        except Exception as e:
            print(f"保存锁定状态失败: {e}")
    
    def clear_lock_status(self):
        """清除锁定状态文件"""
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception as e:
            print(f"清除锁定状态失败: {e}")
    
    def show_unlock_dialog(self):
        """显示解锁对话框，返回True表示解锁成功，False表示失败"""
        # 确保主窗口可见，以便 Toplevel 窗口能正确显示
        self.root.deiconify()
        self.root.update()
        
        unlock_window = tk.Toplevel(self.root)
        unlock_window.title("软件已锁定")
        unlock_window.geometry("400x200")
        unlock_window.transient(self.root)
        unlock_window.grab_set()
        unlock_window.resizable(False, False)
        # 确保解锁窗口在最前面
        unlock_window.lift()
        unlock_window.focus_force()
        
        # 居中显示
        unlock_window.update_idletasks()
        width = unlock_window.winfo_width()
        height = unlock_window.winfo_height()
        x = (unlock_window.winfo_screenwidth() // 2) - (width // 2)
        y = (unlock_window.winfo_screenheight() // 2) - (height // 2)
        unlock_window.geometry(f'{width}x{height}+{x}+{y}')
        
        # 提示信息
        info_label = tk.Label(
            unlock_window,
            text="软件已被锁定！\n请输入解锁码以继续使用。",
            font=(self.chinese_font, 12),
            fg="red",
            justify=tk.CENTER
        )
        info_label.pack(pady=20)
        
        # 解锁码输入框
        code_frame = ttk.Frame(unlock_window)
        code_frame.pack(pady=10)
        
        ttk.Label(code_frame, text="解锁码:", font=(self.chinese_font, 10)).pack(side=tk.LEFT, padx=5)
        code_var = tk.StringVar()
        code_entry = ttk.Entry(code_frame, textvariable=code_var, show="*", width=20, font=(self.chinese_font, 10))
        code_entry.pack(side=tk.LEFT, padx=5)
        code_entry.focus()
        
        # 结果标签
        result_label = tk.Label(unlock_window, text="", fg="red", font=(self.chinese_font, 9))
        result_label.pack(pady=5)
        
        # 解锁结果
        unlock_result = [False]  # 使用列表以便在闭包中修改
        
        def try_unlock():
            entered_code = code_var.get().strip()
            if entered_code == UNLOCK_CODE:
                unlock_result[0] = True
                unlock_window.destroy()
            else:
                # 解锁失败，显示错误信息
                result_label.config(text="解锁码错误！程序即将退出...")
                unlock_window.update()
                time.sleep(1)
                unlock_result[0] = False
                unlock_window.destroy()
                # 销毁主窗口并退出程序
                self.root.destroy()
                sys.exit(1)
        
        def on_enter(event):
            try_unlock()
        
        code_entry.bind("<Return>", on_enter)
        
        # 确定按钮
        button_frame = ttk.Frame(unlock_window)
        button_frame.pack(pady=10)
        
        def on_cancel():
            # 取消也视为失败，销毁程序
            unlock_result[0] = False
            unlock_window.destroy()
            self.root.destroy()
            sys.exit(1)
        
        ttk.Button(button_frame, text="确定", command=try_unlock, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        # 等待窗口关闭
        unlock_window.wait_window()
        
        return unlock_result[0]
    
    def lock_application(self):
        """锁定软件，禁用所有输入和按钮"""
        if self.is_locked:
            return  # 已经锁定，避免重复锁定
        
        self.is_locked = True
        self.log("✗ 软件已锁定：检测到非法IP地址", "ERROR")
        
        # 保存锁定状态到文件
        self.save_lock_status()
        
        # 递归禁用所有widget
        def disable_widget(widget):
            """递归禁用widget及其子widget"""
            try:
                # 禁用Entry、Combobox、Button等
                if isinstance(widget, (ttk.Entry, ttk.Combobox, ttk.Button, tk.Entry, tk.Button)):
                    widget.config(state="disabled")
                elif isinstance(widget, (scrolledtext.ScrolledText, tk.Text)):
                    widget.config(state="disabled")
                elif isinstance(widget, ttk.Treeview):
                    # Treeview不能直接禁用，但可以禁用其绑定的事件
                    pass
                
                # 递归处理子widget
                for child in widget.winfo_children():
                    disable_widget(child)
            except:
                pass  # 忽略无法禁用的widget
        
        # 禁用根窗口的所有子widget
        for child in self.root.winfo_children():
            disable_widget(child)
        
        # 显示锁定提示
        messagebox.showerror("软件已锁定", "检测到非法IP地址，软件已被锁定！\n\n下次启动时需要输入解锁码。")
    
    def establish_ssh_tunnel(self):
        """建立SSH隧道"""
        global USE_PARAMIKO
        
        username = self.username_var.get()
        host = self.host_var.get().strip()
        ssh_port = int(self.ssh_port_var.get())
        password = self.password_var.get()
        local_port = int(self.local_port_var.get())
        remote_port = int(self.remote_port_var.get())
        
        # 检查IP白名单
        if host not in self.allowed_ips:
            # 记录警告次数
            if host not in self.ip_warning_count:
                self.ip_warning_count[host] = 0
            self.ip_warning_count[host] += 1
            
            if self.ip_warning_count[host] == 1:
                # 第一次警告，只显示弹窗
                messagebox.showerror("非法IP", f"IP地址 {host} 不在允许列表中！\n\n这是第一次警告，再次尝试将锁定软件。")
                return False
            else:
                # 第二次警告，锁定软件
                messagebox.showerror("非法IP", f"IP地址 {host} 不在允许列表中！\n\n软件已被锁定！")
                self.lock_application()
                return False
        
        ssh_host = f"{username}@{host}"
        
        self.log(f"建立SSH隧道: {local_port} -> {remote_port}")
        
        # 检查是否已经有可用的SSH隧道（直接测试端口是否可访问Ollama）
        if self.check_ssh_connection():
            self.log(f"✓ 检测到现有SSH隧道，直接使用", "SUCCESS")
            return True
        
        # 优先使用paramiko（Windows上最可靠）
        if USE_PARAMIKO and password:
            try:
                self.log("使用paramiko建立SSH隧道...")
                import socket
                import paramiko
                
                # 创建SSH客户端
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # 连接SSH服务器
                client.connect(
                    hostname=host,
                    port=ssh_port,
                    username=username,
                    password=password,
                    timeout=10,
                    allow_agent=False,
                    look_for_keys=False
                )
                
                self.ssh_client = client
                transport = client.get_transport()
                
                # 创建本地端口转发服务器
                def forward_tunnel():
                    try:
                        # 创建本地监听socket
                        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        server_socket.bind(('127.0.0.1', local_port))
                        server_socket.listen(5)
                        
                        while True:
                            try:
                                # 接受本地连接
                                local_sock, addr = server_socket.accept()
                                
                                # 在新线程中处理每个连接
                                def handle_connection(local_socket):
                                    try:
                                        # 通过SSH建立到远程端口的通道
                                        remote_channel = transport.open_channel(
                                            'direct-tcpip',
                                            ('localhost', remote_port),
                                            (addr[0], addr[1])
                                        )
                                        
                                        # 双向转发数据
                                        def forward_data(source, dest):
                                            try:
                                                while True:
                                                    data = source.recv(4096)
                                                    if not data:
                                                        break
                                                    dest.send(data)
                                            except:
                                                pass
                                        
                                        # 在两个线程中分别转发两个方向的数据
                                        import threading
                                        t1 = threading.Thread(target=forward_data, args=(local_socket, remote_channel), daemon=True)
                                        t2 = threading.Thread(target=forward_data, args=(remote_channel, local_socket), daemon=True)
                                        t1.start()
                                        t2.start()
                                        t1.join()
                                        t2.join()
                                    except Exception as e:
                                        pass
                                    finally:
                                        try:
                                            local_socket.close()
                                            remote_channel.close()
                                        except:
                                            pass
                                
                                threading.Thread(target=handle_connection, args=(local_sock,), daemon=True).start()
                            except Exception as e:
                                if "listening" not in str(e).lower():
                                    break
                    except Exception as e:
                        self.log(f"SSH隧道线程错误: {e}", "ERROR")
                    finally:
                        try:
                            server_socket.close()
                        except:
                            pass
                
                # 启动隧道线程
                self.ssh_tunnel_thread = threading.Thread(target=forward_tunnel, daemon=True)
                self.ssh_tunnel_thread.start()
                
                # 等待一下让隧道建立
                time.sleep(1)
                
                # 验证隧道是否可用（通过测试Ollama API）
                try:
                    test_url = f"http://localhost:{local_port}/api/tags"
                    response = requests.get(test_url, timeout=3)
                    if response.status_code == 200:
                        self.log("✓ SSH隧道已建立（使用paramiko）", "SUCCESS")
                        return True
                    else:
                        self.log("✓ SSH隧道已建立（使用paramiko），但Ollama服务可能未启动", "SUCCESS")
                        return True  # 即使Ollama未启动，隧道本身已建立
                except:
                    # 即使无法访问Ollama，也认为隧道已建立（可能是Ollama未启动）
                    self.log("✓ SSH隧道已建立（使用paramiko）", "SUCCESS")
                    return True
                    
            except Exception as e:
                self.log(f"paramiko建立SSH隧道失败: {e}", "WARN")
                import traceback
                self.log(f"详细错误: {traceback.format_exc()[:500]}", "WARN")
                if self.ssh_client:
                    try:
                        self.ssh_client.close()
                    except:
                        pass
                    self.ssh_client = None
                # 继续尝试其他方法
        
        # 如果没有paramiko，无法建立SSH隧道
        if not USE_PARAMIKO:
            self.log("✗ 错误: 需要安装paramiko库才能建立SSH隧道", "ERROR")
            self.log("请运行: pip install paramiko", "ERROR")
            return False
        
        # 如果paramiko也失败，无法建立SSH隧道
        self.log("✗ SSH隧道建立失败: paramiko连接失败", "ERROR")
        return False
    
    def run_ssh_command(self, command, show_console=True):
        """执行SSH命令"""
        global USE_PARAMIKO
        
        username = self.username_var.get()
        host = self.host_var.get()
        ssh_port = int(self.ssh_port_var.get())
        password = self.password_var.get()
        ssh_host = f"{username}@{host}"
        
        # 在日志中显示实际执行的命令（控制台风格）
        if show_console:
            # 检查是否在模型管理页面（通过检查是否有model_mgmt_log方法）
            if hasattr(self, 'model_mgmt_output') and self.model_mgmt_output:
                self.model_mgmt_log(f"{username}@{host}:~$ {command}", "INFO")
            else:
                self.log(f"[SSH命令] {command}", "INFO")
        else:
            self.log(f"[SSH命令] {command}", "INFO")
        
        # 优先使用paramiko（Windows上最可靠）
        if USE_PARAMIKO and password:
            try:
                import paramiko
                
                # 优先复用已有的SSH客户端连接
                client = None
                reuse_connection = False
                
                if self.ssh_client:
                    try:
                        # 检查现有连接是否有效
                        transport = self.ssh_client.get_transport()
                        if transport and transport.is_active():
                            client = self.ssh_client
                            reuse_connection = True
                        else:
                            # 连接已失效，关闭并创建新连接
                            try:
                                self.ssh_client.close()
                            except:
                                pass
                            self.ssh_client = None
                    except:
                        # 检查失败，关闭旧连接
                        try:
                            self.ssh_client.close()
                        except:
                            pass
                        self.ssh_client = None
                
                # 如果没有可复用的连接，创建新连接
                if not client:
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(
                        hostname=host,
                        port=ssh_port,
                        username=username,
                        password=password,
                        timeout=30,
                        allow_agent=False,
                        look_for_keys=False
                    )
                    # 保存连接以便后续复用（但不关闭，保持连接）
                    self.ssh_client = client
                
                # 使用连接执行命令
                stdin, stdout, stderr = client.exec_command(command, timeout=3600)
                output = stdout.read().decode('utf-8', errors='ignore')
                error_output = stderr.read().decode('utf-8', errors='ignore')
                exit_status = stdout.channel.recv_exit_status()
                
                # 注意：不复用连接时，不关闭client，保持连接以便后续使用
                # 只有在连接失败或需要重新连接时才关闭
                
                full_output = output + error_output
                
                # 在模型管理页面显示命令输出（控制台风格）
                if show_console and hasattr(self, 'model_mgmt_output') and self.model_mgmt_output and full_output.strip():
                    self.model_mgmt_log(full_output, "INFO")
                
                return True, full_output, exit_status
            except Exception as e:
                # 如果连接出错，清除保存的连接
                if self.ssh_client:
                    try:
                        self.ssh_client.close()
                    except:
                        pass
                    self.ssh_client = None
                return False, str(e), 1
        
        # 如果没有paramiko，无法执行SSH命令
        return False, "需要安装paramiko库才能执行SSH命令。请运行: pip install paramiko", 1
    
    def check_model_running(self, model_name):
        """检查指定模型是否正在运行"""
        # 检查是否有该模型的运行进程
        ollama_cmd = get_ollama_cmd()
        if not ollama_cmd:
            return False
        
        cmd_name = os.path.basename(ollama_cmd)
        success, output, code = self.run_ssh_command(f"pgrep -f '{ollama_cmd} run {model_name}' || pgrep -f '{cmd_name} run {model_name}' || echo 'not_running'")
        if success:
            return "not_running" not in output
        return False
    
    def pull_model_with_progress(self, model_name):
        """下载模型并显示进度"""
        global USE_PARAMIKO, _ollama_path
        
        self.is_downloading = True
        self.log(f"开始下载模型 {model_name}...")
        self.log("这可能需要一些时间，请耐心等待...")
        
        # 自动检测ollama路径（在两个可能的位置）
        username = self.username_var.get()
        data_path = f"/data/{username}/ollama/bin/ollama"
        home_path = f"/home/{username}/ollama/bin/ollama"
        
        # 检测 /data/<username>/ollama/bin/ollama
        success1, output1, _ = self.run_ssh_command(f"test -x {data_path} && {data_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
        found_in_data = success1 and "NOT_FOUND" not in output1
        
        # 检测 /home/<username>/ollama/bin/ollama
        success2, output2, _ = self.run_ssh_command(f"test -x {home_path} && {home_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
        found_in_home = success2 and "NOT_FOUND" not in output2
        
        if found_in_data:
            ollama_cmd = data_path
            self.log(f"使用检测到的 ollama 路径: {ollama_cmd}", "INFO")
        elif found_in_home:
            ollama_cmd = home_path
            self.log(f"使用检测到的 ollama 路径: {ollama_cmd}", "INFO")
        else:
            self.log("✗ 错误: 未找到Ollama，无法下载模型", "ERROR")
            self.log("提示: 请先启动服务，系统会自动检测Ollama路径", "INFO")
            return False
        
        global _ollama_path
        _ollama_path = ollama_cmd
        
        # 优先使用paramiko（Windows上最可靠，可以实时显示进度）
        username = self.username_var.get()
        host = self.host_var.get()
        ssh_port = int(self.ssh_port_var.get())
        password = self.password_var.get()
        
        if USE_PARAMIKO and password:
            try:
                import paramiko
                
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    hostname=host,
                    port=ssh_port,
                    username=username,
                    password=password,
                    timeout=30,
                    allow_agent=False,
                    look_for_keys=False
                )
                
                # 执行ollama pull命令，实时读取输出
                self.log(f"使用命令: {ollama_cmd} pull {model_name}", "INFO")
                stdin, stdout, stderr = client.exec_command(f"{ollama_cmd} pull {model_name}", timeout=3600)
                
                # 实时读取输出并显示进度
                import select
                import sys
                import re
                
                def read_output():
                    buffer = ""
                    last_progress = ""
                    while True:
                        # 检查是否被中断
                        if not self.is_downloading:
                            self.log("下载已中断", "WARN")
                            try:
                                client.close()
                            except:
                                pass
                            return False
                        
                        # 检查是否有数据可读
                        if sys.platform == 'win32':
                            # Windows上使用不同的方法
                            if stdout.channel.recv_ready():
                                data = stdout.channel.recv(4096).decode('utf-8', errors='replace')
                                if data:
                                    buffer += data
                                    # 按行处理
                                    while '\n' in buffer or '\r' in buffer:
                                        line_end = buffer.find('\n')
                                        if line_end == -1:
                                            line_end = buffer.find('\r')
                                        if line_end == -1:
                                            break
                                        line = buffer[:line_end].strip()
                                        buffer = buffer[line_end+1:].lstrip('\r\n')
                                        
                                        if line:
                                            # 解析ollama pull的输出格式
                                            # 格式示例: "pulling manifest", "pulling <hash>... 50%", "downloading <size>", "extracting <size>"
                                            progress_match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
                                            if progress_match:
                                                percent = progress_match.group(1)
                                                # 提取操作类型
                                                if 'pulling' in line.lower():
                                                    if 'manifest' in line.lower():
                                                        self.log(f"📥 正在拉取清单... {percent}%", "INFO")
                                                    else:
                                                        self.log(f"📥 正在拉取层... {percent}%", "INFO")
                                                elif 'downloading' in line.lower():
                                                    self.log(f"⬇️ 正在下载... {percent}%", "INFO")
                                                elif 'extracting' in line.lower():
                                                    self.log(f"📦 正在解压... {percent}%", "INFO")
                                                elif 'verifying' in line.lower():
                                                    self.log(f"✓ 正在验证... {percent}%", "INFO")
                                                else:
                                                    self.log(f"⏳ {line}", "INFO")
                                            elif any(keyword in line.lower() for keyword in ['pulling', 'downloading', 'extracting', 'verifying', 'complete', 'success']):
                                                # 没有百分比但有关键词，显示完整信息
                                                if 'complete' in line.lower() or 'success' in line.lower():
                                                    self.log(f"✓ {line}", "SUCCESS")
                                                else:
                                                    self.log(f"⏳ {line}", "INFO")
                            
                            if stderr.channel.recv_stderr_ready():
                                data = stderr.channel.recv_stderr(4096).decode('utf-8', errors='replace')
                                if data:
                                    for line in data.split('\n'):
                                        line = line.strip()
                                        if line and not line.startswith('Error:'):
                                            self.log(f"ℹ️ {line}", "INFO")
                            
                            if stdout.channel.exit_status_ready():
                                # 处理剩余的buffer
                                if buffer.strip():
                                    for line in buffer.split('\n'):
                                        line = line.strip()
                                        if line:
                                            self.log(f"⏳ {line}", "INFO")
                                break
                            time.sleep(0.1)  # 更频繁地检查，提高实时性
                        else:
                            # Linux/Mac上使用select
                            r, w, x = select.select([stdout.channel, stderr.channel], [], [], 0.1)
                            buffer = ""
                            if stdout.channel in r:
                                data = stdout.channel.recv(4096).decode('utf-8', errors='replace')
                                if data:
                                    buffer += data
                                    # 按行处理
                                    while '\n' in buffer or '\r' in buffer:
                                        line_end = buffer.find('\n')
                                        if line_end == -1:
                                            line_end = buffer.find('\r')
                                        if line_end == -1:
                                            break
                                        line = buffer[:line_end].strip()
                                        buffer = buffer[line_end+1:].lstrip('\r\n')
                                        
                                        if line:
                                            # 解析ollama pull的输出格式
                                            progress_match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
                                            if progress_match:
                                                percent = progress_match.group(1)
                                                if 'pulling' in line.lower():
                                                    if 'manifest' in line.lower():
                                                        self.log(f"📥 正在拉取清单... {percent}%", "INFO")
                                                    else:
                                                        self.log(f"📥 正在拉取层... {percent}%", "INFO")
                                                elif 'downloading' in line.lower():
                                                    self.log(f"⬇️ 正在下载... {percent}%", "INFO")
                                                elif 'extracting' in line.lower():
                                                    self.log(f"📦 正在解压... {percent}%", "INFO")
                                                elif 'verifying' in line.lower():
                                                    self.log(f"✓ 正在验证... {percent}%", "INFO")
                                                else:
                                                    self.log(f"⏳ {line}", "INFO")
                                            elif any(keyword in line.lower() for keyword in ['pulling', 'downloading', 'extracting', 'verifying', 'complete', 'success']):
                                                if 'complete' in line.lower() or 'success' in line.lower():
                                                    self.log(f"✓ {line}", "SUCCESS")
                                                else:
                                                    self.log(f"⏳ {line}", "INFO")
                            
                            if stderr.channel in r:
                                data = stderr.channel.recv_stderr(4096).decode('utf-8', errors='replace')
                                if data:
                                    for line in data.split('\n'):
                                        line = line.strip()
                                        if line and not line.startswith('Error:'):
                                            self.log(f"ℹ️ {line}", "INFO")
                            
                            if stdout.channel.exit_status_ready():
                                # 处理剩余的buffer
                                if buffer.strip():
                                    for line in buffer.split('\n'):
                                        line = line.strip()
                                        if line:
                                            self.log(f"⏳ {line}", "INFO")
                                break
                
                # 在后台线程中读取输出
                output_thread = threading.Thread(target=read_output, daemon=True)
                output_thread.start()
                
                # 等待命令完成（检查中断）
                if not self.is_downloading:
                    self.log("下载已中断", "WARN")
                    try:
                        client.close()
                    except:
                        pass
                    return False
                
                exit_status = stdout.channel.recv_exit_status()
                
                # 读取剩余输出
                remaining_stdout = stdout.read().decode('utf-8', errors='replace')
                remaining_stderr = stderr.read().decode('utf-8', errors='replace')
                
                if remaining_stdout:
                    for line in remaining_stdout.split('\n'):
                        line = line.strip()
                        if line:
                            self.log(f"下载信息: {line}", "INFO")
                
                # 显示错误信息（如果有）
                if remaining_stderr:
                    for line in remaining_stderr.split('\n'):
                        line = line.strip()
                        if line:
                            self.log(f"下载错误: {line}", "ERROR")
                
                client.close()
                
                # 检查是否被中断
                if not self.is_downloading:
                    self.log("下载已中断", "WARN")
                    return False
                
                # 检查命令退出状态
                if exit_status != 0:
                    self.log(f"✗ 模型 {model_name} 下载失败，退出状态码: {exit_status}", "ERROR")
                    if remaining_stderr:
                        self.log(f"错误详情: {remaining_stderr[:500]}", "ERROR")
                    self.is_downloading = False
                    return False
                
                # 检查是否成功（使用更可靠的方法）
                time.sleep(1)
                success, output, code = self.run_ssh_command(f"{ollama_cmd} list")
                if success:
                    # 解析输出检查模型是否存在
                    lines = output.strip().split('\n')
                    model_exists = False
                    if len(lines) > 1:
                        for line in lines[1:]:
                            parts = line.split()
                            if parts:
                                listed_model = parts[0]
                                if listed_model == model_name or listed_model.startswith(model_name + ":"):
                                    model_exists = True
                                    break
                    
                    if model_exists:
                        self.log(f"✓ 模型 {model_name} 下载完成", "SUCCESS")
                        return True
                    else:
                        self.log(f"✗ 模型 {model_name} 下载失败或验证失败", "ERROR")
                        self.log(f"验证输出: {output[:300]}", "ERROR")
                        return False
                else:
                    # 检查是否是 ollama 命令找不到的错误
                    if "command not found" in output.lower() or "not found" in output.lower():
                        self.log(f"✗ 错误: 服务器上找不到 ollama 命令", "ERROR")
                        self.log(f"请确保服务器上已安装 Ollama，并且 ollama 命令在 PATH 中", "ERROR")
                    else:
                        self.log(f"✗ 无法验证模型是否下载成功: {output}", "ERROR")
                    return False
                    
            except Exception as e:
                self.log(f"✗ paramiko下载过程出错: {e}", "ERROR")
                import traceback
                self.log(f"详细错误: {traceback.format_exc()[:500]}", "WARN")
                # 继续尝试其他方法
        
            # 使用普通方式（无法实时显示进度）
            self.log("使用普通方式下载（无法显示实时进度）...")
            success, output, code = self.run_ssh_command(f"{ollama_cmd} pull {model_name}")
            if success and code == 0:
                # 显示输出中的关键信息
                if output:
                    for line in output.split('\n'):
                        if 'pulling' in line.lower() or '%' in line or 'downloading' in line.lower():
                            self.log(f"下载信息: {line.strip()}", "INFO")
                self.log(f"✓ 模型 {model_name} 下载完成", "SUCCESS")
                return True
            else:
                # 检查是否是 ollama 命令找不到的错误
                if "command not found" in output.lower() or "not found" in output.lower():
                    self.log(f"✗ 错误: 服务器上找不到 ollama 命令", "ERROR")
                    self.log(f"请确保服务器上已安装 Ollama，并且 ollama 命令在 PATH 中", "ERROR")
                    self.log(f"错误详情: {output}", "ERROR")
                    return False
                self.log(f"✗ 模型 {model_name} 下载失败: {output}", "ERROR")
                return False
    
    def start_ollama_services(self):
        """启动Ollama服务"""
        base_model_name = self.model_var.get()
        model_size = self.model_size_var.get()
        model_name = get_full_model_name(base_model_name, model_size)
        
        self.log("检查Ollama服务状态...")
        
        global _ollama_path
        
        # 优先使用用户自定义的Ollama路径
        ollama_cmd = None
        custom_dir = self.ollama_custom_dir_var.get().strip()
        
        if custom_dir:
            # 用户输入了自定义路径，检查该路径下是否有ollama
            custom_ollama_path = f"{custom_dir.rstrip('/')}/ollama/bin/ollama"
            self.log(f"检查用户指定的Ollama路径: {custom_ollama_path}", "INFO")
            success_custom, output_custom, _ = self.run_ssh_command(
                f"test -x {custom_ollama_path} && {custom_ollama_path} --version 2>&1 || echo 'NOT_FOUND'", 
                show_console=False
            )
            found_custom = success_custom and "NOT_FOUND" not in output_custom
            if found_custom:
                ollama_cmd = custom_ollama_path
                self.log(f"✓ 使用用户指定的 ollama 路径: {ollama_cmd}", "SUCCESS")
        
        # 如果用户没有指定路径或用户指定的路径不可用，使用默认检测逻辑
        if not ollama_cmd:
            # 先检测ollama是否已经安装（在两个可能的位置都检测）
            username = self.username_var.get()
            data_path = f"/data/{username}/ollama/bin/ollama"
            home_path = f"/home/{username}/ollama/bin/ollama"
            
            self.log(f"检测 Ollama 是否已安装...", "INFO")
            
            # 检测 /data/<username>/ollama/bin/ollama
            self.log(f"检查路径 1: {data_path}", "INFO")
            success1, output1, code1 = self.run_ssh_command(f"test -x {data_path} && {data_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
            found_in_data = success1 and "NOT_FOUND" not in output1
            
            # 检测 /home/<username>/ollama/bin/ollama
            self.log(f"检查路径 2: {home_path}", "INFO")
            success2, output2, code2 = self.run_ssh_command(f"test -x {home_path} && {home_path} --version 2>&1 || echo 'NOT_FOUND'", show_console=False)
            found_in_home = success2 and "NOT_FOUND" not in output2
            
            # 确定使用的路径（自动检测）
            if found_in_data:
                ollama_cmd = data_path
                self.log(f"✓ 在 {data_path} 找到 Ollama", "SUCCESS")
            elif found_in_home:
                ollama_cmd = home_path
                self.log(f"✓ 在 {home_path} 找到 Ollama", "SUCCESS")
            else:
                # 两个位置都没有，需要检测 /data/ 目录并安装
                self.log(f"✗ 在两个位置都未找到 Ollama", "ERROR")
                
                # 如果用户指定了自定义路径，使用用户指定的路径进行安装
                if custom_dir:
                    install_path = f"{custom_dir.rstrip('/')}/ollama/bin/ollama"
                    install_base_dir = f"{custom_dir.rstrip('/')}/ollama"
                    self.log(f"使用用户指定的路径进行安装: {install_base_dir}", "INFO")
                else:
                    # 检测服务器是否有 /data/ 目录
                    self.log(f"检测服务器目录结构...", "INFO")
                    success_check, output_check, _ = self.run_ssh_command("test -d /data && echo 'EXISTS' || echo 'NOT_EXISTS'", show_console=False)
                    output_check_clean = output_check.strip() if output_check else ""
                    
                    if success_check and output_check_clean == "EXISTS":
                        # 有 /data/ 目录，使用 /data/<username>/ollama/bin/ollama
                        install_path = data_path
                        install_base_dir = f"/data/{username}/ollama"
                        self.log(f"✓ 检测到 /data/ 目录，将安装到: {install_base_dir}", "INFO")
                    else:
                        # 没有 /data/ 目录，使用 /home/<username>/ollama/bin/ollama
                        install_path = home_path
                        install_base_dir = f"/home/{username}/ollama"
                        self.log(f"✓ 未检测到 /data/ 目录，将安装到: {install_base_dir}", "INFO")
                
                # 弹窗提示安装
                if messagebox.askyesno(
                    "Ollama 未安装",
                    f"未在服务器上找到 Ollama。\n\n"
                    f"是否要安装 Ollama 到 {install_base_dir}？\n\n"
                    f"注意：这将安装新的 Ollama，不会影响原有的安装。\n"
                    f"安装后，可执行文件将位于 {install_base_dir}/bin/ollama"
                ):
                    # 用户选择安装
                    if self.install_ollama(install_path):
                        self.log(f"✓ Ollama 已安装到: {install_path}", "SUCCESS")
                        ollama_cmd = install_path
                    else:
                        self.log(f"✗ Ollama 安装失败", "ERROR")
                        return False
                else:
                    self.log("用户取消了 Ollama 安装", "INFO")
                    return False
        
        # 设置最终使用的路径
        if ollama_cmd:
            self.ollama_path_var.set(ollama_cmd)
            expanded_path = ollama_cmd
            
            _ollama_path = expanded_path
            
            self.log(f"使用检测到的 ollama 路径: {expanded_path}", "INFO")
        else:
            self.log("✗ 无法确定 Ollama 路径", "ERROR")
            return False
        
        # 首先通过本地端口（SSH隧道）测试服务是否可访问（这是最可靠的判断方式）
        self.log("检查 Ollama 服务是否可访问...")
        local_port = int(self.local_port_var.get())
        service_accessible = False
        try:
            test_url = f"http://localhost:{local_port}/api/tags"
            response = requests.get(test_url, timeout=3)
            service_accessible = response.status_code == 200
        except:
            service_accessible = False
        
        if service_accessible:
            self.log("✓ Ollama 服务可正常访问", "SUCCESS")
        else:
            # 服务不可访问，直接启动（使用最简单的启动方式）
            self.log("服务不可访问，启动 ollama serve...", "INFO")
            # 使用指定的ollama路径（已在函数开头设置）
            
            # 使用最简单的启动方式：<ollama_path> serve &
            # 如果指定了GPU，使用CUDA_VISIBLE_DEVICES环境变量
            gpu_devices = self.gpu_var.get().strip()
            if gpu_devices:
                self.log(f"使用GPU设备: {gpu_devices}", "INFO")
                # 使用CUDA_VISIBLE_DEVICES环境变量指定GPU
                serve_cmd = f"CUDA_VISIBLE_DEVICES={gpu_devices} {ollama_cmd} serve > /dev/null 2>&1 &"
            else:
                serve_cmd = f"{ollama_cmd} serve > /dev/null 2>&1 &"
            
            self.log(f"执行: {serve_cmd}", "INFO")
            success, output, code = self.run_ssh_command(serve_cmd)
            
            # 等待服务启动并验证（通过本地端口验证，因为需要通过SSH隧道访问）
            self.log("等待 ollama serve 启动...", "INFO")
            max_retries = 10
            for i in range(max_retries):
                time.sleep(2)  # 每次等待2秒
                # 通过本地端口（SSH隧道）验证服务是否可访问
                try:
                    test_url = f"http://localhost:{local_port}/api/tags"
                    response = requests.get(test_url, timeout=2)
                    if response.status_code == 200:
                        self.log("✓ ollama serve 已启动并验证成功", "SUCCESS")
                        break
                except:
                    pass
                if i < max_retries - 1:
                    self.log(f"等待服务就绪... ({i+1}/{max_retries})", "INFO")
            else:
                self.log("⚠ ollama serve 已启动，但验证可能失败，继续尝试...", "WARN")
            
            # 检查启动命令是否失败
            if not success:
                self.log(f"⚠ 启动可能失败: {output}", "WARN")
                # 检查是否是命令找不到的错误
                if "command not found" in output.lower() or "not found" in output.lower():
                    self.log(f"✗ 错误: 服务器上找不到 ollama 命令", "ERROR")
                    self.log(f"请确保服务器上已安装 Ollama，并且 ollama 命令在 PATH 中", "ERROR")
                    return False
        
        # 检查模型是否存在
        self.log(f"检查模型 {model_name} 是否存在...")
        # 使用指定的ollama路径获取模型列表
        success, output, code = self.run_ssh_command(f"{ollama_cmd} list")
        
        if not success:
            # 检查是否是 ollama 命令找不到的错误
            if "command not found" in output.lower() or "not found" in output.lower():
                self.log(f"✗ 错误: 服务器上找不到 ollama 命令", "ERROR")
                self.log(f"请确保服务器上已安装 Ollama，并且 ollama 命令在 PATH 中", "ERROR")
                self.log(f"错误详情: {output}", "ERROR")
                return False
            else:
                self.log(f"⚠ 无法检查模型列表: {output}", "WARN")
                # 如果检查失败但不是命令找不到，尝试下载模型
                self.log(f"尝试下载模型 {model_name}...", "INFO")
                if not self.pull_model_with_progress(model_name):
                    self.log("✗ 模型下载失败，无法继续", "ERROR")
                    return False
        else:
            # 解析ollama list的输出，检查模型是否存在
            # ollama list 输出格式：
            # NAME              ID      SIZE    MODIFIED
            # model_name        abc123  4.5GB   2 hours ago
            model_exists = False
            lines = output.strip().split('\n')
            if len(lines) > 1:  # 有表头，至少需要2行
                for line in lines[1:]:  # 跳过表头
                    parts = line.split()
                    if parts:
                        # 第一列是模型名称（可能包含标签，如 model:latest）
                        listed_model = parts[0]
                        # 检查精确匹配或前缀匹配（处理标签情况）
                        if listed_model == model_name or listed_model.startswith(model_name + ":"):
                            model_exists = True
                            break
            
            if model_exists:
                self.log(f"✓ 模型 {model_name} 已存在", "SUCCESS")
            else:
                self.log(f"模型 {model_name} 不存在，开始下载...", "INFO")
                # 在下载前再次验证Ollama服务是否可访问（通过本地端口）
                self.log("下载前验证Ollama服务...", "INFO")
                local_port = int(self.local_port_var.get())
                try:
                    test_url = f"http://localhost:{local_port}/api/tags"
                    response = requests.get(test_url, timeout=3)
                    service_accessible = response.status_code == 200
                except:
                    service_accessible = False
                
                if not service_accessible:
                    self.log("⚠ Ollama服务可能未就绪，等待5秒后重试...", "WARN")
                    time.sleep(5)
                    # 再次验证
                    try:
                        test_url2 = f"http://localhost:{local_port}/api/tags"
                        response2 = requests.get(test_url2, timeout=3)
                        service_accessible2 = response2.status_code == 200
                    except:
                        service_accessible2 = False
                    
                    if not service_accessible2:
                        self.log("✗ Ollama服务无法访问，无法下载模型", "ERROR")
                        return False
                    else:
                        self.log("✓ Ollama服务已就绪", "SUCCESS")
                else:
                    self.log("✓ Ollama服务可访问", "SUCCESS")
                
                if not self.pull_model_with_progress(model_name):
                    self.log("✗ 模型下载失败，无法继续", "ERROR")
                    return False
        
        # 检查模型是否正在运行
        self.log(f"检查模型 {model_name} 是否正在运行...")
        is_running = self.check_model_running(model_name)
        
        if is_running:
            self.log(f"✓ 模型 {model_name} 已在运行", "SUCCESS")
        else:
            # 停止其他正在运行的模型
            self.log("检查是否有其他模型正在运行...")
            ollama_cmd = get_ollama_cmd()
            if not ollama_cmd:
                return
            cmd_name = os.path.basename(ollama_cmd)
            success, output, code = self.run_ssh_command(f"pgrep -f '{ollama_cmd} run' || pgrep -f '{cmd_name} run' | head -1")
            if success and output.strip():
                self.log("发现其他模型正在运行，先停止...")
                self.stop_ollama_model()
            
            # 预加载模型
            self.log(f"预加载模型 {model_name}...")
            success, output, code = self.run_ssh_command(f"nohup {ollama_cmd} run {model_name} 'test' > /dev/null 2>&1 &")
            if success:
                time.sleep(3)
                # 验证模型是否成功启动
                if self.check_model_running(model_name):
                    self.log(f"✓ 模型 {model_name} 预加载完成", "SUCCESS")
                else:
                    self.log(f"⚠ 模型 {model_name} 预加载可能失败", "WARN")
            else:
                self.log(f"⚠ 模型预加载可能失败: {output}", "WARN")
        
        return True
    
    def test_ollama_connection(self):
        """测试Ollama连接"""
        local_port = int(self.local_port_var.get())
        base_model_name = self.model_var.get()
        model_size = self.model_size_var.get()
        model_name = get_full_model_name(base_model_name, model_size)
        base_url = f"http://localhost:{local_port}"
        
        self.log("测试Ollama连接...")
        
        for i in range(5):
            try:
                test_url = f"{base_url}/api/tags"
                response = requests.get(test_url, timeout=5)
                
                if response.status_code == 200:
                    self.log("✓ Ollama服务器连接成功", "SUCCESS")
                    
                    # 测试模型
                    self.log(f"测试模型 {model_name}...")
                    generate_url = f"{base_url}/api/generate"
                    test_payload = {
                        "model": model_name,
                        "prompt": "Hello",
                        "stream": False
                    }
                    
                    test_response = requests.post(generate_url, json=test_payload, timeout=30)
                    if test_response.status_code == 200:
                        self.log(f"✓ 模型 {model_name} 响应正常", "SUCCESS")
                        return True
                    else:
                        self.log(f"⚠ 模型测试失败 (状态码: {test_response.status_code})", "WARN")
                        
            except requests.exceptions.ConnectionError:
                if i < 4:
                    self.log(f"连接失败，重试 {i+1}/5...", "WARN")
                    time.sleep(2)
                else:
                    self.log("✗ 无法连接到Ollama服务器", "ERROR")
                    return False
            except Exception as e:
                self.log(f"✗ 测试失败: {e}", "ERROR")
                return False
        
        return False
    
    def stop_ollama_model(self):
        """停止当前运行的Ollama模型"""
        self.log("停止当前运行的Ollama模型...")
        
        # 方法1: 使用 ollama ps 获取当前运行的模型
        ollama_cmd = get_ollama_cmd()
        if not ollama_cmd:
            return
        success, output, code = self.run_ssh_command(f"{ollama_cmd} ps")
        if success and output.strip():
            # 解析 ollama ps 的输出，获取模型名称
            # ollama ps 输出格式通常是：
            # NAME              ID      SIZE    MODIFIED
            # model_name        abc123  4.5GB   2 hours ago
            lines = output.strip().split('\n')
            if len(lines) > 1:  # 有表头，至少需要2行
                models_to_stop = []
                for line in lines[1:]:  # 跳过表头
                    parts = line.split()
                    if parts:
                        model_name = parts[0]
                        if model_name and model_name not in models_to_stop:
                            models_to_stop.append(model_name)
                
                # 停止所有运行的模型
                stopped_any = False
                for model_name in models_to_stop:
                    self.log(f"正在停止模型: {model_name}...")
                    success, output, code = self.run_ssh_command(f"{ollama_cmd} stop {model_name}")
                    if success:
                        self.log(f"✓ 已停止模型: {model_name}", "SUCCESS")
                        stopped_any = True
                    else:
                        self.log(f"⚠ 停止模型 {model_name} 失败: {output}", "WARN")
                
                if stopped_any:
                    time.sleep(1)
                    return True
        
        # 方法2: 如果 ollama ps 失败或没有输出，尝试使用配置的模型名称
        base_model_name = self.model_var.get()
        model_size = self.model_size_var.get()
        model_name = get_full_model_name(base_model_name, model_size)
        if model_name:
            self.log(f"尝试停止配置的模型: {model_name}...")
            ollama_cmd = get_ollama_cmd()
            if not ollama_cmd:
                return
            success, output, code = self.run_ssh_command(f"{ollama_cmd} stop {model_name}")
            if success:
                self.log(f"✓ 已停止模型: {model_name}", "SUCCESS")
                time.sleep(1)
                return True
            else:
                # 如果停止失败，可能是模型没有运行，这是正常的
                self.log(f"模型 {model_name} 可能未运行或已停止", "INFO")
                return True
        
        # 方法3: 如果以上都失败，使用旧方法（kill进程）作为后备
        self.log("使用备用方法停止模型...")
        ollama_cmd = get_ollama_cmd()
        if not ollama_cmd:
            return
        cmd_name = os.path.basename(ollama_cmd)
        success, output, code = self.run_ssh_command(f"pgrep -f '{ollama_cmd} run' || pgrep -f '{cmd_name} run' | head -1")
        if success and output.strip():
            pid = output.strip()
            self.log(f"找到运行中的模型进程 PID: {pid}")
            success, output, code = self.run_ssh_command(f"kill {pid} 2>/dev/null && echo 'stopped' || echo 'failed'")
            if success and "stopped" in output:
                self.log("✓ 已停止运行中的模型（使用备用方法）", "SUCCESS")
                time.sleep(1)
                return True
            else:
                self.log("⚠ 停止模型失败", "WARN")
                return False
        else:
            self.log("没有运行中的模型", "INFO")
            return True
    
    def install_ollama(self, install_path):
        """安装Ollama到指定路径"""
        self.is_downloading = True
        try:
            self.log(f"开始安装 Ollama 到: {install_path}", "INFO")
            
            # 解析安装路径，确定安装目录（不包含 /bin/ollama）
            if install_path.endswith('/bin/ollama'):
                install_base_dir = install_path[:-10]  # 去掉 '/bin/ollama'
            elif install_path.endswith('/ollama'):
                # 如果路径以 /ollama 结尾，直接使用
                install_base_dir = install_path
            else:
                # 如果路径格式不对，根据是否有 /data/ 目录确定
                username = self.username_var.get()
                success_check, output_check, _ = self.run_ssh_command("test -d /data && echo 'EXISTS' || echo 'NOT_EXISTS'", show_console=False)
                output_check_clean = output_check.strip() if output_check else ""
                if success_check and output_check_clean == "EXISTS":
                    install_base_dir = f"/data/{username}/ollama"
                else:
                    install_base_dir = f"/home/{username}/ollama"
            
            username = self.username_var.get()
            
            # 创建安装目录
            self.log(f"创建安装目录: {install_base_dir}", "INFO")
            success, output, code = self.run_ssh_command(
                f"mkdir -p {install_base_dir}",
                show_console=False
            )
            if not success:
                self.log(f"✗ 创建目录失败: {output}", "ERROR")
                return False
            
            # 从本地上传并安装 Ollama
            self.log("准备从本地上传并安装 Ollama...", "INFO")
            
            # 获取ollama压缩包路径（优先从资源文件，其次从本地文件）
            ollama_tgz_path = None
            
            # 方法1: 尝试从exe资源中读取（如果打包了）
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller打包后的临时目录
                resource_path = os.path.join(sys._MEIPASS, "ollama-linux-amd64.tgz")
                if os.path.exists(resource_path):
                    ollama_tgz_path = resource_path
                    self.log(f"从exe资源中找到压缩包: {ollama_tgz_path}", "INFO")
            
            # 方法2: 尝试从脚本目录读取
            if not ollama_tgz_path:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                local_path = os.path.join(script_dir, "ollama-linux-amd64.tgz")
                if os.path.exists(local_path):
                    ollama_tgz_path = local_path
                    self.log(f"从本地文件找到压缩包: {ollama_tgz_path}", "INFO")
            
            # 方法3: 如果都找不到，提示用户选择文件
            if not ollama_tgz_path:
                self.log("未找到ollama压缩包，请选择文件...", "INFO")
                file_path = filedialog.askopenfilename(
                    title="选择 Ollama 压缩包",
                    filetypes=[("压缩包", "*.tgz *.tar.gz"), ("所有文件", "*.*")]
                )
                if not file_path:
                    self.log("✗ 用户取消了文件选择", "ERROR")
                    self.is_downloading = False
                    return False
                ollama_tgz_path = file_path
            
            # 使用paramiko SFTP上传文件
            self.log(f"正在上传文件: {os.path.basename(ollama_tgz_path)}...", "INFO")
            try:
                import paramiko
                
                # 获取SSH连接（复用或新建）
                client = None
                temp_client = False
                
                if self.ssh_client:
                    # 复用现有连接
                    try:
                        # 测试连接是否有效
                        transport = self.ssh_client.get_transport()
                        if transport and transport.is_active():
                            client = self.ssh_client
                            self.log("复用现有SSH连接", "INFO")
                        else:
                            self.ssh_client = None
                    except:
                        self.ssh_client = None
                
                if not client:
                    # 需要新建SSH连接
                    username = self.username_var.get()
                    host = self.host_var.get()
                    ssh_port = int(self.ssh_port_var.get())
                    password = self.password_var.get()
                    
                    self.log("建立新的SSH连接用于文件上传...", "INFO")
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(
                        hostname=host,
                        port=ssh_port,
                        username=username,
                        password=password,
                        timeout=30,
                        allow_agent=False,
                        look_for_keys=False
                    )
                    temp_client = True
                
                # 创建SFTP客户端
                sftp = client.open_sftp()
                
                # 上传文件到临时位置
                remote_temp_path = f"/tmp/ollama-linux-amd64.tgz"
                
                # 检查远程文件是否已存在（可能是其他用户上传的）
                need_upload = True
                try:
                    sftp.stat(remote_temp_path)
                    # 文件存在，跳过上传
                    need_upload = False
                    self.log(f"检测到服务器临时位置已有文件: {remote_temp_path}，跳过上传", "INFO")
                except (IOError, OSError):
                    # 文件不存在（IOError/OSError），需要上传
                    need_upload = True
                except Exception as e:
                    # 其他错误，尝试上传
                    need_upload = True
                    self.log(f"检查远程文件时出错，将尝试上传: {e}", "WARN")
                
                if need_upload:
                    self.log(f"上传到服务器临时位置: {remote_temp_path}", "INFO")
                    
                    # 显示上传进度
                    file_size = os.path.getsize(ollama_tgz_path)
                    self.log(f"文件大小: {file_size / 1024 / 1024:.2f} MB", "INFO")
                    
                    # 创建上传进度条窗口
                    progress_window = tk.Toplevel(self.root)
                    progress_window.title("上传进度")
                    progress_window.geometry("400x120")
                    progress_window.resizable(False, False)
                    # 居中显示
                    progress_window.update_idletasks()
                    x = (progress_window.winfo_screenwidth() // 2) - (progress_window.winfo_width() // 2)
                    y = (progress_window.winfo_screenheight() // 2) - (progress_window.winfo_height() // 2)
                    progress_window.geometry(f"+{x}+{y}")
                    
                    # 进度条
                    progress_var = tk.DoubleVar()
                    progress_bar = ttk.Progressbar(
                        progress_window,
                        variable=progress_var,
                        maximum=100,
                        length=350,
                        mode='determinate'
                    )
                    progress_bar.pack(pady=20, padx=20)
                    
                    # 进度文本
                    progress_label = tk.Label(
                        progress_window,
                        text="0.0% (0.00 MB / 0.00 MB)",
                        font=(self.chinese_font, 10)
                    )
                    progress_label.pack(pady=5)
                    
                    # 用于中断上传的异常类
                    class UploadInterrupted(Exception):
                        pass
                    
                    upload_interrupted = False  # 用于标记是否中断
                    last_percent = -1  # 记录上次显示的百分比，避免频繁更新
                    
                    def progress_callback(transferred, total):
                        nonlocal upload_interrupted, last_percent
                        
                        # 检查是否被中断
                        if not self.is_downloading:
                            upload_interrupted = True
                            # 尝试关闭SFTP连接以中断上传
                            try:
                                sftp.close()
                            except:
                                pass
                            raise UploadInterrupted("上传已中断")
                        
                        percent = (transferred / total) * 100
                        # 实时更新进度条（每1%更新一次，避免过于频繁）
                        current_percent = int(percent)
                        if current_percent != last_percent:
                            progress_var.set(percent)
                            progress_label.config(
                                text=f"{percent:.1f}% ({transferred / 1024 / 1024:.2f} MB / {total / 1024 / 1024:.2f} MB)"
                            )
                            progress_window.update_idletasks()
                            last_percent = current_percent
                    
                    # 上传文件（在try-except中捕获中断异常）
                    try:
                        sftp.put(ollama_tgz_path, remote_temp_path, callback=progress_callback)
                    except (UploadInterrupted, Exception) as e:
                        # 关闭进度条窗口
                        try:
                            progress_window.destroy()
                        except:
                            pass
                        
                        if upload_interrupted or not self.is_downloading:
                            self.log("上传已中断", "WARN")
                            try:
                                sftp.close()
                            except:
                                pass
                            if temp_client:
                                try:
                                    client.close()
                                except:
                                    pass
                            self.is_downloading = False
                            return False
                        else:
                            # 其他异常，重新抛出
                            raise
                    
                    # 关闭进度条窗口
                    try:
                        progress_window.destroy()
                    except:
                        pass
                    
                    self.log("✓ 文件上传完成", "SUCCESS")
                
                sftp.close()
                
                if temp_client:
                    client.close()
                
                # 解压并安装
                self.log("正在解压并安装...", "INFO")
                # 如果文件是我们上传的，解压后删除；如果是已存在的文件，保留给其他用户使用
                if need_upload:
                    install_cmd = f"tar zx -f {remote_temp_path} -C {install_base_dir} && rm -f {remote_temp_path}"
                else:
                    install_cmd = f"tar zx -f {remote_temp_path} -C {install_base_dir}"
                success, output, code = self.run_ssh_command(install_cmd, show_console=True)
                if not success:
                    self.log(f"✗ 解压安装失败: {output}", "ERROR")
                    self.is_downloading = False
                    return False
                
            except Exception as e:
                self.log(f"✗ 上传文件失败: {e}", "ERROR")
                import traceback
                self.log(traceback.format_exc()[:500], "ERROR")
                self.is_downloading = False
                return False
            
            # 验证安装（检查 bin/ollama 是否存在）
            verify_path = f"{install_base_dir}/bin/ollama"
            verify_cmd = f"test -x {verify_path} && {verify_path} --version 2>&1 || echo 'NOT_FOUND'"
            success, output, code = self.run_ssh_command(verify_cmd, show_console=True)
            
            if success and "NOT_FOUND" not in output and code == 0:
                self.log(f"✓ Ollama 安装成功", "SUCCESS")
                self.log(f"✓ 可执行文件位于: {verify_path}", "SUCCESS")
                return True
            else:
                self.log(f"✗ Ollama 安装验证失败: {output}", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"✗ 安装 Ollama 时出错: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc()[:500], "ERROR")
            return False
    
    def close_ssh_tunnel(self):
        """关闭SSH隧道"""
        self.log("正在关闭SSH隧道...")
        
        # 关闭SSH隧道（paramiko）
        if self.ssh_client:
            try:
                self.ssh_client.close()
                self.log("✓ SSH隧道（paramiko）已关闭", "SUCCESS")
            except:
                pass
            self.ssh_client = None
        
        
        # 释放本地端口
        try:
            local_port = int(self.local_port_var.get())
            self.log(f"正在释放本地端口 {local_port}...")
            self.kill_process_on_port(local_port)
        except Exception as e:
            self.log(f"释放端口时出错: {e}", "WARN")
    
    def cleanup(self):
        """清理资源（包括关闭SSH）"""
        try:
            self.log("清理资源...")
            
            # 停止Ollama模型
            try:
                self.stop_ollama_model()
            except Exception as e:
                self.log(f"停止Ollama模型时出错: {e}", "WARN")
            
            # 关闭SSH连接
            try:
                self.close_ssh_tunnel()
            except Exception as e:
                self.log(f"关闭SSH隧道时出错: {e}", "WARN")
        except Exception as e:
            self.log(f"清理资源时出错: {e}", "WARN")
    
    def cleanup_without_ssh(self):
        """清理资源（不关闭SSH连接）"""
        try:
            self.log("清理资源（保持SSH连接）...")
            
            # 停止Ollama模型
            try:
                self.stop_ollama_model()
            except Exception as e:
                self.log(f"停止Ollama模型时出错: {e}", "WARN")
            
            # 注意：不关闭SSH连接，保持SSH隧道打开
        except Exception as e:
            self.log(f"清理资源时出错: {e}", "WARN")
    
    def analyze_row(self, row_data, prompt_template, idx, total, api_delay):
        """分析表格中的一行数据"""
        try:
            # 检查是否已停止
            if not self.is_running:
                return None
            
            # 替换prompt中的列名占位符
            prompt = prompt_template
            for col_name, value in row_data.items():
                placeholder = f"{{{col_name}}}"
                prompt = prompt.replace(placeholder, str(value) if value else "")
            
            # API调用前的小延迟（可中断）
            if api_delay > 0:
                # 分段sleep，以便能够快速响应停止信号
                sleep_interval = 0.1
                slept = 0
                while slept < api_delay and self.is_running:
                    time.sleep(min(sleep_interval, api_delay - slept))
                    slept += sleep_interval
            
            # 再次检查是否已停止
            if not self.is_running:
                return None
            
            # 根据模式选择调用不同的API
            api_mode = _global_client_config.get('api_mode', 'ollama')
            
            if api_mode == 'online':
                # 在线API调用
                api_url = _global_client_config.get('api_url')
                api_key = _global_client_config.get('api_key')
                model_name = _global_client_config.get('model_name')
                provider = _global_client_config.get('provider', 'siliconflow')
                temperature = float(_global_client_config.get('temperature', 0.7))
                max_tokens = int(_global_client_config.get('max_tokens', 4096))
                top_p = float(_global_client_config.get('top_p', 0.7))
                enable_thinking = _global_client_config.get('enable_thinking', 'False').lower() == 'true'
                thinking_budget = int(_global_client_config.get('thinking_budget', 4096))
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }
                
                # 根据提供商构建不同的请求体
                if provider == "siliconflow":
                    # 硅基流动API格式
                    payload = {
                        "model": model_name,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False,
                        "max_tokens": max_tokens,
                        "enable_thinking": enable_thinking,
                        "thinking_budget": thinking_budget,
                        "min_p": 0.05,
                        "stop": None,
                        "temperature": temperature,
                        "top_p": top_p,
                        "top_k": 50,
                        "frequency_penalty": 0.5,
                        "n": 1,
                        "response_format": {"type": "json_object"}
                    }
                else:
                    # 通用格式（custom或siliconflow）
                    payload = {
                        "model": model_name,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "top_p": top_p
                    }
                    if enable_thinking and thinking_budget:
                        payload["thinking_budget"] = thinking_budget
                
                # 再次检查是否已停止（在发送请求前）
                if not self.is_running:
                    return None
                
                response = requests.post(api_url, json=payload, headers=headers, timeout=120)
                response.raise_for_status()
                
                # 请求完成后再次检查是否已停止
                if not self.is_running:
                    return None
                
                result_data = response.json()
                # 记录请求时间和token数
                current_time = time.time()
                self.request_times.append(current_time)
                
                # 提取token使用量（只使用total_tokens字段）
                tokens_used = 0
                if "usage" in result_data:
                    usage = result_data["usage"]
                    if "total_tokens" in usage:
                        tokens_used = usage["total_tokens"]
                
                if tokens_used > 0:
                    self.total_tokens_count += tokens_used
                    # 记录每分钟的token数（用于计算TPM）
                    self.token_counts.append((current_time, tokens_used))
                
                # OpenAI格式的响应
                if "choices" in result_data and len(result_data["choices"]) > 0:
                    result_text = result_data["choices"][0]["message"]["content"].strip()
                else:
                    result_text = ""
            else:
                # Ollama API调用（原有逻辑）
                local_port = _global_client_config.get('local_port', int(self.local_port_var.get()))
                model_name = _global_client_config.get('model_name', self.model_var.get())
                api_url = f"http://localhost:{local_port}/api/generate"
                payload = {
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False
                }
                
                # 再次检查是否已停止（在发送请求前）
                if not self.is_running:
                    return None
                
                response = requests.post(api_url, json=payload, timeout=120)
                response.raise_for_status()
                
                # 请求完成后再次检查是否已停止
                if not self.is_running:
                    return None
                
                result_data = response.json()
                result_text = result_data.get("response", "").strip()
                
                # 记录请求时间（Ollama模式）
                current_time = time.time()
                self.request_times.append(current_time)
                
                # 提取token使用量（优先使用total_tokens，否则使用prompt_eval_count + eval_count）
                tokens_used = 0
                if "usage" in result_data and "total_tokens" in result_data["usage"]:
                    tokens_used = result_data["usage"]["total_tokens"]
                elif "prompt_eval_count" in result_data and "eval_count" in result_data:
                    tokens_used = result_data.get("prompt_eval_count", 0) + result_data.get("eval_count", 0)
                
                if tokens_used > 0:
                    self.total_tokens_count += tokens_used
                    self.token_counts.append((current_time, tokens_used))
            
            # 如果返回空字符串，直接跳过这一行
            if not result_text or result_text == "":
                self.log(f"[{idx}/{total}] 返回空字符串，跳过该行", "INFO")
                return None  # 返回None表示跳过
            
            # 清理响应文本，提取JSON部分
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            # 再次检查是否为空（清理后可能为空）
            if not result_text or result_text == "":
                self.log(f"[{idx}/{total}] 清理后为空字符串，跳过该行", "INFO")
                return None  # 返回None表示跳过
            
            # 尝试解析JSON，处理转义字符问题
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError as e:
                # 如果解析失败，尝试修复常见的转义问题
                try:
                    import re
                    # 提取JSON对象（找到第一个{到最后一个}）
                    start_idx = result_text.find('{')
                    end_idx = result_text.rfind('}')
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        json_str = result_text[start_idx:end_idx+1]
                        
                        # 处理双重花括号的情况（如 {{ "title": "..." }}）
                        json_str_stripped = json_str.strip()
                        if json_str_stripped.startswith('{{') and json_str_stripped.endswith('}}'):
                            # 找到第二个 {（内层JSON的开始位置）
                            first_brace = json_str_stripped.find('{')
                            second_brace = json_str_stripped.find('{', first_brace + 1)
                            
                            if second_brace != -1:
                                # 从第二个 { 开始，使用括号匹配找到匹配的 }
                                brace_count = 0
                                inner_end = -1
                                in_string = False
                                escape_next = False
                                
                                # 从第二个 { 开始，找到匹配的 }（考虑字符串内的花括号）
                                for i in range(second_brace, len(json_str_stripped)):
                                    char = json_str_stripped[i]
                                    
                                    if escape_next:
                                        escape_next = False
                                        continue
                                    
                                    if char == '\\' and in_string:
                                        escape_next = True
                                        continue
                                    
                                    if char == '"' and not escape_next:
                                        in_string = not in_string
                                        continue
                                    
                                    if not in_string:
                                        if char == '{':
                                            brace_count += 1
                                        elif char == '}':
                                            brace_count -= 1
                                            if brace_count == 0:
                                                inner_end = i
                                                break
                                
                                # 如果找到了匹配的 }，提取内层JSON
                                if inner_end != -1:
                                    json_str = json_str_stripped[second_brace:inner_end+1]
                                else:
                                    # 如果找不到匹配的 }，尝试找到倒数第二个 }
                                    last_brace = json_str_stripped.rfind('}')
                                    second_last_brace = json_str_stripped.rfind('}', 0, last_brace)
                                    if second_last_brace != -1 and second_last_brace > second_brace:
                                        json_str = json_str_stripped[second_brace:second_last_brace+1]
                                    else:
                                        # 最后的方法：去掉最外层的一对花括号
                                        json_str = json_str_stripped[1:-1].strip()
                            else:
                                # 如果找不到第二个 {，直接去掉最外层的一对花括号
                                json_str = json_str_stripped[1:-1].strip()
                    else:
                        json_str = result_text
                    
                    # 修复未转义的反斜杠
                    # 使用状态机正确处理字符串内外的反斜杠
                    def fix_backslashes(text):
                        result = []
                        i = 0
                        in_string = False
                        escape_next = False
                        
                        while i < len(text):
                            char = text[i]
                            
                            if escape_next:
                                # 前一个字符是反斜杠，当前字符需要检查
                                if char in 'nrt"\\/':
                                    # 有效转义序列
                                    result.append('\\' + char)
                                elif char == 'u' and i + 4 < len(text):
                                    # Unicode转义 \uXXXX
                                    unicode_part = text[i:i+5]
                                    if all(c in '0123456789abcdefABCDEF' for c in unicode_part[1:]):
                                        result.append('\\' + unicode_part)
                                        i += 4
                                    else:
                                        # 无效Unicode，转义反斜杠
                                        result.append('\\\\')
                                        result.append(char)
                                else:
                                    # 无效转义，转义反斜杠
                                    result.append('\\\\')
                                    result.append(char)
                                escape_next = False
                                i += 1
                            elif char == '\\':
                                if in_string:
                                    escape_next = True
                                    i += 1
                                else:
                                    result.append(char)
                                    i += 1
                            elif char == '"':
                                # 只有在非转义状态下才切换字符串状态
                                in_string = not in_string
                                result.append(char)
                                i += 1
                            else:
                                result.append(char)
                                i += 1
                        
                        # 处理末尾未完成的反斜杠
                        if escape_next:
                            result.append('\\\\')
                        
                        return ''.join(result)
                    
                    fixed_json = fix_backslashes(json_str)
                    # 再次检查是否还有双重花括号
                    fixed_json_stripped = fixed_json.strip()
                    if fixed_json_stripped.startswith('{{') and fixed_json_stripped.endswith('}}'):
                        # 如果还有双重花括号，再次处理
                        # 找到第二个 { 和倒数第二个 }
                        second_brace = fixed_json_stripped.find('{', fixed_json_stripped.find('{') + 1)
                        last_brace = fixed_json_stripped.rfind('}')
                        second_last_brace = fixed_json_stripped.rfind('}', 0, last_brace)
                        if second_brace != -1 and second_last_brace != -1 and second_last_brace > second_brace:
                            fixed_json = fixed_json_stripped[second_brace:second_last_brace+1]
                        else:
                            # 如果找不到，直接去掉最外层的一对花括号
                            fixed_json = fixed_json_stripped[1:-1].strip()
                    
                    result = json.loads(fixed_json)
                    self.log(f"[{idx}/{total}] JSON解析已修复转义问题", "INFO")
                except Exception as e2:
                    # 如果修复也失败，记录详细错误信息并返回错误结果
                    self.log(f"[{idx}/{total}] JSON解析错误: {e}", "ERROR")
                    self.log(f"[{idx}/{total}] 尝试修复后仍失败: {e2}", "ERROR")
                    self.log(f"[{idx}/{total}] 原始响应前300字符: {result_text[:300]}", "ERROR")
                    # 返回错误信息，但不中断处理
                    return {
                        "row_index": idx,
                        "original_data": row_data,
                        "analysis_result": {"error": f"JSON解析失败: {str(e)}", "raw_response": result_text[:500]}
                    }
            
            # 返回完整的JSON结果和原始行数据（不再判断是否相关，直接返回所有结果）
            return {
                "row_index": idx,
                "original_data": row_data,
                "analysis_result": result
            }
            
        except json.JSONDecodeError as e:
            self.log(f"[{idx}/{total}] JSON解析错误: {e}", "ERROR")
            return {
                "row_index": idx,
                "original_data": row_data,
                "analysis_result": {"error": str(e)}
            }
        except Exception as e:
            self.log(f"[{idx}/{total}] 分析出错: {e}", "ERROR")
            return {
                "row_index": idx,
                "original_data": row_data,
                "analysis_result": {"error": str(e)}
            }
    
    def on_monitor_enabled_changed(self):
        """监控开关改变时的回调"""
        enabled = self.monitor_enabled_var.get()
        if enabled:
            self.monitor_content_frame.grid()
        else:
            self.monitor_content_frame.grid_remove()
    
    def update_monitor(self):
        """更新监控显示"""
        # 如果监控未启用，不更新
        if not self.monitor_enabled_var.get():
            # 如果正在运行，继续检查（但不更新显示）
            if self.is_running:
                self.root.after(self.monitor_update_interval, self.update_monitor)
            return
        
        try:
            current_time = time.time()
            
            # 计算实际运行时间
            if self.monitor_start_time is None:
                self.monitor_start_time = current_time
            
            elapsed_time = current_time - self.monitor_start_time
            
            # 如果运行时间不足1分钟，使用实际运行时间计算；否则使用过去1分钟的数据
            if elapsed_time < 60 and elapsed_time > 0:
                # 使用实际运行时间计算RPM和TPM
                all_requests = len(self.request_times)
                all_tokens = sum(tokens for t, tokens in self.token_counts)
                # 按比例换算到每分钟
                rpm = int(all_requests / elapsed_time * 60) if elapsed_time > 0 else 0
                tpm = int(all_tokens / elapsed_time * 60) if elapsed_time > 0 else 0
            else:
                # 运行时间超过1分钟，使用过去1分钟内的数据
                one_minute_ago = current_time - 60
                recent_requests = [t for t in self.request_times if t > one_minute_ago]
                rpm = len(recent_requests)
                
                recent_tokens = sum(tokens for t, tokens in self.token_counts if t > one_minute_ago)
                tpm = recent_tokens
            
            # 计算平均每个prompt的token数
            avg_tokens = 0
            if len(self.request_times) > 0:
                avg_tokens = int(self.total_tokens_count / len(self.request_times))
            
            # 更新显示
            self.rpm_var.set(str(rpm))
            self.tpm_var.set(str(tpm))
            self.total_tokens_var.set(str(self.total_tokens_count))
            self.avg_tokens_per_prompt_var.set(str(avg_tokens))
            
            # 检查是否超过上限，如果超过则改变颜色
            try:
                rpm_limit = int(self.rpm_limit_var.get() or "1000")
                if rpm > rpm_limit:
                    self.rpm_label.config(foreground="red")
                else:
                    self.rpm_label.config(foreground="blue")
            except:
                pass
            
            try:
                tpm_limit = int(self.tpm_limit_var.get() or "100000")
                if tpm > tpm_limit:
                    self.tpm_label.config(foreground="red")
                else:
                    self.tpm_label.config(foreground="blue")
            except:
                pass
            
            try:
                total_limit = int(self.total_tokens_limit_var.get() or "1000000")
                if self.total_tokens_count > total_limit:
                    self.total_tokens_label.config(foreground="red")
                else:
                    self.total_tokens_label.config(foreground="blue")
            except:
                pass
            
            # 清理过期的数据（保留最近2分钟的数据）
            two_minutes_ago = current_time - 120
            self.request_times = [t for t in self.request_times if t > two_minutes_ago]
            self.token_counts = [(t, tokens) for t, tokens in self.token_counts if t > two_minutes_ago]
            
        except Exception as e:
            pass  # 静默失败，避免影响主流程
        
        # 如果正在运行，继续更新
        if self.is_running:
            self.root.after(self.monitor_update_interval, self.update_monitor)
    
    def reset_monitor(self):
        """重置监控数据"""
        self.request_times = []
        self.token_counts = []
        self.total_tokens_count = 0
        self.monitor_start_time = time.time()  # 记录开始时间
        self.rpm_var.set("0")
        self.tpm_var.set("0")
        self.total_tokens_var.set("0")
        self.avg_tokens_per_prompt_var.set("0")
        self.rpm_label.config(foreground="blue")
        self.tpm_label.config(foreground="blue")
        self.total_tokens_label.config(foreground="blue")
    
    def process_table(self):
        """处理表格并生成调研报告（并发处理）"""
        # 重置监控数据
        self.reset_monitor()
        # 启动监控更新
        self.root.after(self.monitor_update_interval, self.update_monitor)
        
        table_path = self.table_var.get()
        api_delay = float(self.api_delay_var.get() or "0.5")
        max_workers = int(self.max_workers_var.get() or "8")
        
        # 根据模式获取不同的配置
        api_mode = self.api_mode_var.get()
        if api_mode == "ollama":
            local_port = int(self.local_port_var.get())
            base_model_name = self.model_var.get()
            model_size = self.model_size_var.get()
            model_name = get_full_model_name(base_model_name, model_size)
        else:
            # 在线API模式，这些变量不需要
            local_port = None
            model_name = None
        
        if not os.path.exists(table_path):
            self.log(f"✗ 找不到表格文件: {table_path}", "ERROR")
            return False
        
        # 读取prompt模板
        prompt_template = self.prompt_text.get(1.0, tk.END).strip()
        if not prompt_template:
            self.log("✗ Prompt不能为空", "ERROR")
            return False
        
        self.log(f"读取表格: {table_path}")
        self.log("-" * 60)
        
        try:
            # 固定跳过第一行（表头）
            skip_rows = 1
            
            # 读取表格
            if table_path.endswith('.csv'):
                # CSV文件：DictReader会自动将第一行作为列名，从第二行开始读取数据
                with open(table_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            else:
                # Excel文件：第一行是列名，skiprows=1跳过第一行
                import pandas as pd
                df = pd.read_excel(table_path, skiprows=1)
                rows = df.to_dict('records')
            
            total_rows = len(rows)
            self.log(f"共 {total_rows} 行数据待处理，使用 {max_workers} 个并发线程，API延迟: {api_delay}秒")
            
            # 设置全局配置，供analyze_row使用
            global _global_client_config
            api_mode = self.api_mode_var.get()
            
            if api_mode == "online":
                _global_client_config = {
                    'api_mode': 'online',
                    'api_url': self.online_api_url_var.get().strip(),
                    'api_key': self.online_api_key_var.get().strip(),
                    'model_name': self.online_model_var.get().strip(),
                    'provider': self.online_api_provider_var.get(),
                    'temperature': float(self.online_api_temperature_var.get() or "0.7"),
                    'max_tokens': int(self.online_api_max_tokens_var.get() or "4096"),
                    'top_p': float(self.online_api_top_p_var.get() or "0.7"),
                    'enable_thinking': self.online_api_enable_thinking_var.get(),
                    'thinking_budget': int(self.online_api_thinking_budget_var.get() or "4096")
                }
            else:
                # Ollama模式需要local_port和model_name
                local_port = int(self.local_port_var.get())
                base_model_name = self.model_var.get()
                model_size = self.model_size_var.get()
                model_name = get_full_model_name(base_model_name, model_size)
                _global_client_config = {
                    'api_mode': 'ollama',
                    'local_port': local_port,
                    'model_name': model_name  # 已经包含大小信息（如果指定了）
                }
            
            all_results = []
            completed = 0  # 使用锁保护的计数器
            start_time = time.time()
            
            # 使用线程池并发处理
            executor = ThreadPoolExecutor(max_workers=max_workers)
            try:
                # 提交所有任务
                future_to_row = {
                    executor.submit(self.analyze_row, row, prompt_template, idx, total_rows, api_delay): (idx, row)
                    for idx, row in enumerate(rows, 1)
                }
                
                # 收集结果
                for future in as_completed(future_to_row):
                    if not self.is_running:
                        self.log("用户中断处理，正在停止所有线程...", "INFO")
                        # 取消未完成的任务
                        cancelled_count = 0
                        for f in future_to_row:
                            if not f.done():
                                f.cancel()
                                cancelled_count += 1
                        self.log(f"已取消 {cancelled_count} 个未完成的任务", "INFO")
                        break
                    
                    idx, row = future_to_row[future]
                    title = str(row.get("name", "") or row.get("title", "") or f"第{idx}行")[:80]
                    
                    try:
                        result = future.result()
                        
                        # 如果返回None，表示跳过该行（返回空字符串的情况）
                        if result is None:
                            with results_lock:
                                self.log(f"[{idx}/{total_rows}] ⏭ 跳过: {title}...（返回空字符串）", "INFO")
                            continue
                        
                        # 保存所有结果（使用锁保证线程安全）
                        if result:
                            with results_lock:
                                all_results.append(result)
                                self.log(f"[{idx}/{total_rows}] ✓ 已处理: {title}...", "SUCCESS")
                    except Exception as e:
                        # 如果是停止导致的异常，不记录为错误
                        if not self.is_running:
                            continue
                        with results_lock:
                            self.log(f"[{idx}/{total_rows}] 任务执行异常: {e}", "ERROR")
                            # 即使出错也记录，但不添加到结果中
                            all_results.append({
                                "row_index": idx,
                                "original_data": row,
                                "analysis_result": {"error": str(e)}
                            })
                    
                    # 更新完成计数（使用锁保证线程安全）
                    with results_lock:
                        completed += 1
                        current_completed = completed
                    
                    # 显示进度（仅在运行中时显示）
                    if self.is_running and (current_completed % 10 == 0 or current_completed == total_rows):
                        elapsed = time.time() - start_time
                        rate = current_completed / elapsed if elapsed > 0 else 0
                        remaining = (total_rows - current_completed) / rate if rate > 0 else 0
                        progress = current_completed / total_rows * 100
                        with results_lock:
                            self.log(f"\n进度: {current_completed}/{total_rows} ({progress:.1f}%) | "
                                   f"已用时: {elapsed:.1f}s | 速度: {rate:.2f}行/s | 预计剩余: {remaining:.1f}s\n")
                    
                    # 如果所有任务都已完成，提前退出循环（避免继续等待）
                    if current_completed >= total_rows:
                        break
                
                # 如果已停止，立即关闭线程池
                if not self.is_running:
                    self.log("正在关闭线程池...", "INFO")
                    # 尝试使用 cancel_futures 参数（Python 3.9+）
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        # Python 3.8 及以下版本不支持 cancel_futures 参数
                        executor.shutdown(wait=False)
                    self.log("线程池已关闭", "INFO")
                    return False
            finally:
                # 确保线程池被关闭
                try:
                    if not executor._shutdown:
                        executor.shutdown(wait=True)
                except:
                    pass
            
            elapsed_time = time.time() - start_time
            if self.is_running:
                self.log(f"\n处理完成！总用时: {elapsed_time:.1f}秒，平均速度: {total_rows/elapsed_time:.2f}行/秒\n")
            
            # 生成报告 - 保存所有结果
            if all_results:
                output_file = self.output_file_var.get() or "调研报告.csv"
                
                # 获取输出列名
                output_columns_str = self.output_columns_var.get().strip()
                output_columns = [col.strip() for col in output_columns_str.split(',') if col.strip()] if output_columns_str else []
                
                # 构建输出数据
                output_data = []
                for result in all_results:
                    row_data = result.get("original_data", {})
                    analysis = result.get("analysis_result", {})
                    
                    # 构建输出行
                    output_row = {}
                    
                    # 如果指定了输出列名，只保存这些列
                    if output_columns:
                        for col in output_columns:
                            # 先从分析结果中获取
                            if isinstance(analysis, dict) and col in analysis:
                                output_row[col] = analysis[col]
                            # 如果分析结果中没有，尝试从原始数据中获取
                            elif col in row_data:
                                output_row[col] = row_data[col]
                            else:
                                output_row[col] = ""
                    else:
                        # 如果没有指定输出列名，保存所有分析结果
                        if isinstance(analysis, dict):
                            for key, value in analysis.items():
                                if key != "is_relevant":
                                    output_row[key] = value
                        else:
                            output_row["分析结果"] = str(analysis)
                    
                    output_data.append(output_row)
                
                # 保存到文件
                import pandas as pd
                df = pd.DataFrame(output_data)
                
                if output_file.endswith('.xlsx'):
                    df.to_excel(output_file, index=False, engine='openpyxl')
                else:
                    df.to_csv(output_file, index=False, encoding='utf-8-sig')
                
                self.log(f"✓ 调研报告已保存到: {output_file}", "SUCCESS")
                self.log(f"共处理 {len(all_results)} 条记录", "SUCCESS")
                if output_columns:
                    self.log(f"输出列: {', '.join(output_columns)}", "INFO")
                
                # 保存完成后，立即停止所有未完成的任务并退出
                self.is_running = False
                # 关闭线程池，不再等待剩余任务
                try:
                    if not executor._shutdown:
                        executor.shutdown(wait=False, cancel_futures=True)
                except:
                    try:
                        executor.shutdown(wait=False)
                    except:
                        pass
                
                return True
            else:
                self.log("未处理任何记录", "INFO")
                # 即使没有结果，也停止运行状态
                self.is_running = False
                return True
                
        except Exception as e:
            self.log(f"✗ 处理表格时出错: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return False
    
    def on_batch_processing_changed(self):
        """批处理开关改变时的回调"""
        enabled = self.batch_processing_var.get()
        
        # 控制模型选择、API参数和并发设置的启用/禁用状态
        widgets_to_disable = [
            self.online_model_combo,
            self.online_model_refresh_btn,
            self.online_api_temperature_entry,
            self.online_api_max_tokens_entry,
            self.online_api_top_p_entry,
            self.online_api_thinking_combo,
            self.online_api_thinking_budget_entry,
            self.workers_entry,
            self.delay_entry
        ]
        
        state = "disabled" if enabled else "normal"
        
        for widget in widgets_to_disable:
            if hasattr(widget, 'config'):
                try:
                    widget.config(state=state)
                except:
                    pass
        
        # 控制批处理配置区域的启用/禁用状态
        batch_widgets = [
            self.batch_model_combo,
            self.batch_dir_entry,
            self.batch_dir_browse_btn,
            self.batch_temperature_entry,
            self.batch_max_tokens_entry,
            self.batch_top_p_entry,
            self.batch_thinking_combo,
            self.batch_thinking_budget_entry
        ]
        
        batch_state = "normal" if enabled else "disabled"
        
        for widget in batch_widgets:
            if hasattr(widget, 'config'):
                try:
                    widget.config(state=batch_state)
                except:
                    pass
        
        # 如果启用批处理，从常规API参数复制到批处理参数
        if enabled:
            self.batch_temperature_var.set(self.online_api_temperature_var.get())
            self.batch_max_tokens_var.set(self.online_api_max_tokens_var.get())
            self.batch_top_p_var.set(self.online_api_top_p_var.get())
            self.batch_enable_thinking_var.set(self.online_api_enable_thinking_var.get())
            self.batch_thinking_budget_var.set(self.online_api_thinking_budget_var.get())
    
    def browse_batch_output_dir(self):
        """浏览批处理结果保存目录"""
        directory = filedialog.askdirectory(title="选择批处理结果保存目录")
        if directory:
            self.batch_output_dir_var.set(directory)
    
    def generate_batch_jsonl(self, table_file, output_file):
        """生成批处理jsonl文件"""
        try:
            # 读取表格文件
            with open(table_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            if not rows:
                self.log("✗ 表格文件为空", "ERROR")
                return False
            
            # 获取列名
            columns = list(rows[0].keys())
            
            # 获取Prompt模板
            prompt_template = self.prompt_text.get(1.0, tk.END).strip()
            
            # 获取API配置（使用批处理参数）
            model = self.batch_model_var.get().strip()
            temperature = float(self.batch_temperature_var.get() or "0.7")
            max_tokens = int(self.batch_max_tokens_var.get() or "4096")
            enable_thinking = self.batch_enable_thinking_var.get() == "True"
            thinking_budget = int(self.batch_thinking_budget_var.get() or "4096") if enable_thinking else None
            
            # 生成jsonl文件
            with open(output_file, 'w', encoding='utf-8') as f:
                for idx, row in enumerate(rows, 1):
                    # 替换Prompt中的占位符
                    prompt = prompt_template
                    for col in columns:
                        placeholder = f"{{{col}}}"
                        value = str(row.get(col, ""))
                        prompt = prompt.replace(placeholder, value)
                    
                    # 构建请求体
                    body = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You are a highly advanced and versatile AI assistant"},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": True,
                        "max_tokens": max_tokens
                    }
                    
                    if enable_thinking and thinking_budget:
                        body["thinking_budget"] = thinking_budget
                    
                    # 构建jsonl行
                    jsonl_entry = {
                        "custom_id": f"request-{idx}",
                        "method": "POST",
                        "url": "/v1/chat/completions",
                        "body": body
                    }
                    
                    f.write(json.dumps(jsonl_entry, ensure_ascii=False) + "\n")
            
            self.log(f"✓ 已生成批处理文件: {output_file}，共 {len(rows)} 条记录", "SUCCESS")
            return True
            
        except Exception as e:
            self.log(f"✗ 生成批处理文件失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return False
    
    def upload_batch_file(self, jsonl_file):
        """上传批处理文件到API"""
        try:
            if not HAS_OPENAI:
                self.log("✗ 未安装openai库，请运行: pip install openai", "ERROR")
                return None
            
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            
            # 提取base_url（去掉/v1/chat/completions）
            if "/v1/chat/completions" in api_url:
                base_url = api_url.replace("/v1/chat/completions", "")
            else:
                base_url = api_url.rsplit("/", 1)[0] if "/" in api_url else api_url
            
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            self.log("正在上传批处理文件...", "INFO")
            with open(jsonl_file, "rb") as f:
                batch_input_file = client.files.create(
                    file=f,
                    purpose="batch"
                )
            
            file_id = batch_input_file.id
            self.log(f"✓ 文件上传成功，文件ID: {file_id}", "SUCCESS")
            return file_id
            
        except Exception as e:
            self.log(f"✗ 上传批处理文件失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return None
    
    def create_batch_task(self, file_id):
        """创建批处理任务"""
        try:
            if not HAS_OPENAI:
                self.log("✗ 未安装openai库", "ERROR")
                return None
            
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            model = self.batch_model_var.get().strip()
            
            # 提取base_url
            if "/v1/chat/completions" in api_url:
                base_url = api_url.replace("/v1/chat/completions", "")
            else:
                base_url = api_url.rsplit("/", 1)[0] if "/" in api_url else api_url
            
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            self.log("正在创建批处理任务...", "INFO")
            batch = client.batches.create(
                input_file_id=file_id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
                metadata={"description": "论文调研批处理任务"},
                extra_body={"replace": {"model": model}}
            )
            
            batch_id = batch.id
            self.batch_task_id_var.set(batch_id)
            self.batch_status_var.set("已创建")
            self.batch_check_status_btn.config(state="normal")
            self.batch_cancel_btn.config(state="normal")
            
            self.log(f"✓ 批处理任务创建成功，任务ID: {batch_id}", "SUCCESS")
            return batch_id
            
        except Exception as e:
            self.log(f"✗ 创建批处理任务失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return None
    
    def check_batch_status(self):
        """检查批处理任务状态"""
        try:
            batch_id = self.batch_task_id_var.get().strip()
            if not batch_id:
                self.log("✗ 没有活动的批处理任务", "ERROR")
                return
            
            if not HAS_OPENAI:
                self.log("✗ 未安装openai库", "ERROR")
                return
            
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            
            # 提取base_url
            if "/v1/chat/completions" in api_url:
                base_url = api_url.replace("/v1/chat/completions", "")
            else:
                base_url = api_url.rsplit("/", 1)[0] if "/" in api_url else api_url
            
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            self.log(f"正在检查任务状态: {batch_id}...", "INFO")
            batch = client.batches.retrieve(batch_id)
            
            status = batch.status
            self.batch_status_var.set(status)
            
            # 更新状态显示
            status_text = f"状态: {status}"
            if hasattr(batch, 'request_counts'):
                counts = batch.request_counts
                status_text += f" | 总数: {counts.total}, 完成: {counts.completed}, 失败: {counts.failed}"
            
            self.log(f"✓ {status_text}", "SUCCESS")
            
            # 如果任务完成，启用下载按钮
            if status in ["completed", "finalizing"]:
                self.batch_download_btn.config(state="normal")
                if hasattr(batch, 'output_file_id') and batch.output_file_id:
                    self.log(f"✓ 任务完成，输出文件ID: {batch.output_file_id}", "SUCCESS")
            
        except Exception as e:
            self.log(f"✗ 检查任务状态失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
    
    def cancel_batch_task(self):
        """取消批处理任务"""
        try:
            batch_id = self.batch_task_id_var.get().strip()
            if not batch_id:
                self.log("✗ 没有活动的批处理任务", "ERROR")
                return
            
            if not HAS_OPENAI:
                self.log("✗ 未安装openai库", "ERROR")
                return
            
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            
            # 提取base_url
            if "/v1/chat/completions" in api_url:
                base_url = api_url.replace("/v1/chat/completions", "")
            else:
                base_url = api_url.rsplit("/", 1)[0] if "/" in api_url else api_url
            
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            if messagebox.askyesno("确认", f"确定要取消批处理任务 {batch_id} 吗？"):
                self.log(f"正在取消任务: {batch_id}...", "INFO")
                client.batches.cancel(batch_id)
                self.batch_status_var.set("已取消")
                self.log("✓ 任务已取消", "SUCCESS")
                
        except Exception as e:
            self.log(f"✗ 取消任务失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
    
    def download_batch_results(self):
        """下载批处理结果文件"""
        try:
            batch_id = self.batch_task_id_var.get().strip()
            if not batch_id:
                self.log("✗ 没有活动的批处理任务", "ERROR")
                return
            
            if not HAS_OPENAI:
                self.log("✗ 未安装openai库", "ERROR")
                return
            
            output_dir = self.batch_output_dir_var.get().strip()
            if not output_dir:
                output_dir = APP_DIR
            else:
                os.makedirs(output_dir, exist_ok=True)
            
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            
            # 提取base_url
            if "/v1/chat/completions" in api_url:
                base_url = api_url.replace("/v1/chat/completions", "")
            else:
                base_url = api_url.rsplit("/", 1)[0] if "/" in api_url else api_url
            
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            # 获取任务信息
            batch = client.batches.retrieve(batch_id)
            
            # 下载输出文件
            if hasattr(batch, 'output_file_id') and batch.output_file_id:
                self.log(f"正在下载输出文件: {batch.output_file_id}...", "INFO")
                output_file_content = client.files.content(batch.output_file_id)
                output_file_path = os.path.join(output_dir, f"batch_{batch_id}_output.jsonl")
                with open(output_file_path, 'wb') as f:
                    f.write(output_file_content.read())
                self.log(f"✓ 输出文件已保存: {output_file_path}", "SUCCESS")
            
            # 下载错误文件
            if hasattr(batch, 'error_file_id') and batch.error_file_id:
                self.log(f"正在下载错误文件: {batch.error_file_id}...", "INFO")
                error_file_content = client.files.content(batch.error_file_id)
                error_file_path = os.path.join(output_dir, f"batch_{batch_id}_errors.jsonl")
                with open(error_file_path, 'wb') as f:
                    f.write(error_file_content.read())
                self.log(f"✓ 错误文件已保存: {error_file_path}", "SUCCESS")
            
        except Exception as e:
            self.log(f"✗ 下载结果文件失败: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
    
    def start_research(self):
        """开始运行调研"""
        if self.is_running:
            return
        
        # 检查是否启用批处理模式
        if self.batch_processing_var.get() and self.api_mode_var.get() == "online":
            # 批处理模式
            self.is_running = True
            start_btn = self.get_current_start_button()
            stop_btn = self.get_current_stop_button()
            if start_btn:
                start_btn.config(state=tk.DISABLED)
            if stop_btn:
                stop_btn.config(state=tk.NORMAL)
            
            # 在新线程中运行批处理
            thread = threading.Thread(target=self._run_batch_processing_thread, daemon=True)
            thread.start()
        else:
            # 常规模式
            self.is_running = True
            start_btn = self.get_current_start_button()
            stop_btn = self.get_current_stop_button()
            if start_btn:
                start_btn.config(state=tk.DISABLED)
            if stop_btn:
                stop_btn.config(state=tk.NORMAL)
            
            # 在新线程中运行
            thread = threading.Thread(target=self._run_research_thread, daemon=True)
            thread.start()
    
    def _run_batch_processing_thread(self):
        """在后台线程中运行批处理流程"""
        try:
            # 步骤1: 验证配置
            self.progress_var.set("步骤 1/4: 验证配置")
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            model_name = self.batch_model_var.get().strip()
            table_file = self.table_var.get().strip()
            
            if not api_key:
                self.log("✗ API Key未设置", "ERROR")
                self.finish_research(False)
                return
            if not api_url:
                self.log("✗ API地址未设置", "ERROR")
                self.finish_research(False)
                return
            if not model_name:
                self.log("✗ 模型名称未设置", "ERROR")
                self.finish_research(False)
                return
            if not table_file or not os.path.exists(table_file):
                self.log("✗ 表格文件不存在", "ERROR")
                self.finish_research(False)
                return
            
            self.log("✓ 配置验证通过", "SUCCESS")
            
            # 步骤2: 生成jsonl文件
            self.progress_var.set("步骤 2/4: 生成批处理文件")
            jsonl_file = os.path.join(APP_DIR, "batch_file_for_batch_inference.jsonl")
            if not self.generate_batch_jsonl(table_file, jsonl_file):
                self.finish_research(False)
                return
            
            # 步骤3: 上传文件
            self.progress_var.set("步骤 3/4: 上传批处理文件")
            file_id = self.upload_batch_file(jsonl_file)
            if not file_id:
                self.finish_research(False)
                return
            
            # 步骤4: 创建批处理任务
            self.progress_var.set("步骤 4/4: 创建批处理任务")
            batch_id = self.create_batch_task(file_id)
            if not batch_id:
                self.finish_research(False)
                return
            
            self.log("✓ 批处理任务已创建，可以使用'检查状态'按钮查看进度", "SUCCESS")
            self.progress_var.set("完成")
            self.finish_research(True)
            
        except Exception as e:
            self.log(f"✗ 批处理过程中发生错误: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            self.finish_research(False)
    
    def _run_research_thread(self):
        """在后台线程中运行调研流程"""
        try:
            api_mode = self.api_mode_var.get()
            
            if api_mode == "ollama":
                # Ollama模式：需要SSH连接和Ollama服务
                # 步骤1: 检查SSH连接
                self.progress_var.set("步骤 1/4: 检查SSH连接")
                if not self.check_ssh_connection():
                    self.log("✗ SSH连接未建立，请先点击'连接'按钮", "ERROR")
                    self.finish_research(False)
                    return
                self.log("✓ SSH连接已就绪", "SUCCESS")
                
                # 步骤2: 启动Ollama服务
                self.progress_var.set("步骤 2/4: 启动Ollama服务")
                if not self.start_ollama_services():
                    self.log("⚠ 警告: Ollama服务启动可能失败，继续尝试...", "WARN")
                
                # 步骤3: 测试连接
                self.progress_var.set("步骤 3/4: 测试连接")
                if not self.test_ollama_connection():
                    self.log("✗ Ollama连接测试失败，退出", "ERROR")
                    self.cleanup_without_ssh()
                    self.finish_research(False)
                    return
                
                # 步骤4: 处理表格
                self.progress_var.set("步骤 4/4: 处理表格数据")
                success = self.process_table()
                
                # 清理（但不关闭SSH连接）
                self.cleanup_without_ssh()
            else:
                # 在线API模式：直接处理表格
                # 步骤1: 验证API配置
                self.progress_var.set("步骤 1/2: 验证API配置")
                api_key = self.online_api_key_var.get().strip()
                api_url = self.online_api_url_var.get().strip()
                model_name = self.online_model_var.get().strip()
                
                if not api_key:
                    self.log("✗ API Key未设置", "ERROR")
                    self.finish_research(False)
                    return
                if not api_url:
                    self.log("✗ API地址未设置", "ERROR")
                    self.finish_research(False)
                    return
                if not model_name:
                    self.log("✗ 模型名称未设置", "ERROR")
                    self.finish_research(False)
                    return
                
                self.log("✓ API配置验证通过", "SUCCESS")
                
                # 步骤2: 处理表格
                self.progress_var.set("步骤 2/2: 处理表格数据")
                success = self.process_table()
            
            if success:
                self.log("✓ 所有步骤完成！", "SUCCESS")
                self.progress_var.set("完成")
            else:
                self.log("✗ 执行过程中出现错误", "ERROR")
                self.progress_var.set("失败")
            
            self.finish_research(success)
            
        except Exception as e:
            self.log(f"✗ 发生未预期的错误: {e}", "ERROR")
            api_mode = self.api_mode_var.get()
            if api_mode == "ollama":
                self.cleanup_without_ssh()
            self.finish_research(False)
    
    def stop_research(self):
        """停止运行（不关闭SSH连接）"""
        try:
            self.log("用户中断运行...", "INFO")
            self.is_running = False
            self.is_downloading = False  # 同时中断下载/上传
            
            # 停止Ollama模型（但不关闭SSH）- 只在Ollama模式下执行
            api_mode = self.api_mode_var.get()
            if api_mode == "ollama":
                try:
                    self.log("正在停止Ollama模型...", "INFO")
                    self.stop_ollama_model()
                except Exception as e:
                    self.log(f"停止Ollama模型时出错: {e}", "WARN")
                
                # 注意：不关闭SSH连接，保持SSH隧道打开以便后续使用
                
                # 清理资源（但不关闭SSH）
                try:
                    self.cleanup_without_ssh()
                except Exception as e:
                    self.log(f"清理资源时出错: {e}", "WARN")
            
            # 完成运行（恢复按钮状态）
            self.finish_research(False)
        except Exception as e:
            # 捕获所有异常，确保UI不会关闭
            self.log(f"停止运行时出错: {e}", "ERROR")
            import traceback
            self.log(f"详细错误: {traceback.format_exc()}", "ERROR")
            # 确保即使出错也恢复按钮状态
            try:
                self.finish_research(False)
            except:
                pass
    
    def finish_research(self, success):
        """完成运行"""
        self.is_running = False
        stop_btn = self.get_current_stop_button()
        if stop_btn:
            stop_btn.config(state=tk.DISABLED)
        # 根据模式和SSH连接状态更新开始按钮状态
        api_mode = self.api_mode_var.get()
        if api_mode == "online":
            # 在线API模式：只要有API配置就可以运行
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            model_name = self.online_model_var.get().strip()
            start_btn = self.get_current_start_button()
            if start_btn:
                if api_key and api_url and model_name:
                    start_btn.config(state=tk.NORMAL)
                else:
                    start_btn.config(state=tk.DISABLED)
        else:
            # Ollama模式：需要SSH连接
            start_btn = self.get_current_start_button()
            if start_btn:
                if self.check_ssh_connection():
                    start_btn.config(state=tk.NORMAL)
                else:
                    start_btn.config(state=tk.DISABLED)
    
    def _load_config_values(self):
        """在初始化时从config文件读取值（不更新UI，只返回字典）"""
        config_values = {}
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                    # 读取API模式
                    if "api_mode" in config:
                        config_values["api_mode"] = config["api_mode"]
                    
                    # 读取在线API配置
                    if "online_api" in config:
                        online_api = config["online_api"]
                        if "api_key" in online_api:
                            config_values["online_api_key"] = online_api["api_key"]
                        if "api_url" in online_api:
                            config_values["online_api_url"] = online_api["api_url"]
                        if "model" in online_api:
                            config_values["online_model"] = online_api["model"]
                        if "provider" in online_api:
                            config_values["online_api_provider"] = online_api["provider"]
                        if "temperature" in online_api:
                            config_values["online_api_temperature"] = online_api["temperature"]
                        if "max_tokens" in online_api:
                            config_values["online_api_max_tokens"] = online_api["max_tokens"]
                        if "top_p" in online_api:
                            config_values["online_api_top_p"] = online_api["top_p"]
                        if "enable_thinking" in online_api:
                            config_values["online_api_enable_thinking"] = online_api["enable_thinking"]
                        if "thinking_budget" in online_api:
                            config_values["online_api_thinking_budget"] = online_api["thinking_budget"]
        except Exception as e:
            pass  # 如果读取失败，使用默认值
        
        return config_values
    
    def save_config(self):
        """保存当前配置到文件"""
        try:
            config = {
                "ssh": {
                    "username": self.username_var.get(),
                    "host": self.host_var.get(),
                    "ssh_port": self.ssh_port_var.get(),
                    "password": self.password_var.get()
                },
                "ollama": {
                    "local_port": self.local_port_var.get(),
                    "remote_port": self.remote_port_var.get(),
                    "model": self.model_var.get(),
                    "model_size": self.model_size_var.get(),
                    "ollama_path": self.ollama_path_var.get(),
                    "ollama_custom_dir": self.ollama_custom_dir_var.get(),
                    "gpu": self.gpu_var.get()
                },
                "api_mode": self.api_mode_var.get(),
                "online_api": {
                    "api_key": self.online_api_key_var.get(),
                    "api_url": self.online_api_url_var.get(),
                    "model": self.online_model_var.get(),
                    "provider": self.online_api_provider_var.get(),
                    "temperature": self.online_api_temperature_var.get(),
                    "max_tokens": self.online_api_max_tokens_var.get(),
                    "top_p": self.online_api_top_p_var.get(),
                    "enable_thinking": self.online_api_enable_thinking_var.get(),
                    "thinking_budget": self.online_api_thinking_budget_var.get()
                },
                "table": {
                    "table_file": self.table_var.get(),
                    "output_file": self.output_file_var.get(),
                    "output_columns": self.output_columns_var.get(),
                    "max_workers": self.max_workers_var.get(),
                    "api_delay": self.api_delay_var.get()
                },
                "batch_processing": {
                    "enabled": self.batch_processing_var.get(),
                    "model": self.batch_model_var.get(),
                    "output_dir": self.batch_output_dir_var.get(),
                    "task_id": self.batch_task_id_var.get(),
                    "temperature": self.batch_temperature_var.get(),
                    "max_tokens": self.batch_max_tokens_var.get(),
                    "top_p": self.batch_top_p_var.get(),
                    "enable_thinking": self.batch_enable_thinking_var.get(),
                    "thinking_budget": self.batch_thinking_budget_var.get()
                },
                "prompt": self.prompt_text.get(1.0, tk.END).strip(),
                "crawler": {
                    "source": self.crawler_source_var.get(),
                    "selected_categories": list(self.category_selected_items),  # 转换为list保存
                    "start_date": self.crawler_start_date_var.get(),
                    "end_date": self.crawler_end_date_var.get(),
                    "output_file": self.crawler_output_file_var.get()
                },
                "monitor": {
                    "enabled": self.monitor_enabled_var.get(),
                    "rpm_limit": self.rpm_limit_var.get(),
                    "tpm_limit": self.tpm_limit_var.get(),
                    "total_tokens_limit": self.total_tokens_limit_var.get()
                }
            }
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.log("✓ 配置已保存", "SUCCESS")
        except Exception as e:
            self.log(f"保存配置失败: {e}", "WARN")
    
    def load_config(self):
        """从文件加载配置"""
        try:
            if not os.path.exists(CONFIG_FILE):
                return  # 配置文件不存在，使用默认值
            
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 加载SSH配置
            if "ssh" in config:
                ssh = config["ssh"]
                if "username" in ssh:
                    self.username_var.set(ssh["username"])
                if "host" in ssh:
                    self.host_var.set(ssh["host"])
                if "ssh_port" in ssh:
                    self.ssh_port_var.set(ssh["ssh_port"])
                if "password" in ssh:
                    self.password_var.set(ssh["password"])
            
            # 加载Ollama配置
            if "ollama" in config:
                ollama = config["ollama"]
                if "local_port" in ollama:
                    self.local_port_var.set(ollama["local_port"])
                if "remote_port" in ollama:
                    self.remote_port_var.set(ollama["remote_port"])
                if "model" in ollama:
                    self.model_var.set(ollama["model"])
                if "model_size" in ollama:
                    self.model_size_var.set(ollama["model_size"])
                if "ollama_path" in ollama:
                    self.ollama_path_var.set(ollama["ollama_path"])
                if "ollama_custom_dir" in ollama:
                    self.ollama_custom_dir_var.set(ollama["ollama_custom_dir"])
                if "gpu" in ollama:
                    self.gpu_var.set(ollama["gpu"])
            
            # 加载模式选择
            if "api_mode" in config:
                self.api_mode_var.set(config["api_mode"])
                # 更新Tab选择
                if hasattr(self, 'mode_notebook'):
                    if config["api_mode"] == "online":
                        self.mode_notebook.select(0)
                    else:
                        self.mode_notebook.select(1)
                self.on_mode_changed()  # 更新界面显示
            
            # 加载在线API配置
            if "online_api" in config:
                online_api = config["online_api"]
                if "api_key" in online_api:
                    self.online_api_key_var.set(online_api["api_key"])
                if "api_url" in online_api:
                    self.online_api_url_var.set(online_api["api_url"])
                if "model" in online_api:
                    self.online_model_var.set(online_api["model"])
                if "provider" in online_api:
                    self.online_api_provider_var.set(online_api["provider"])
                    # 延迟调用，确保界面已创建
                    if hasattr(self, 'online_model_combo'):
                        self.on_api_provider_changed()
                if "temperature" in online_api:
                    self.online_api_temperature_var.set(online_api["temperature"])
                if "max_tokens" in online_api:
                    self.online_api_max_tokens_var.set(online_api["max_tokens"])
                if "top_p" in online_api:
                    self.online_api_top_p_var.set(online_api["top_p"])
                if "enable_thinking" in online_api:
                    self.online_api_enable_thinking_var.set(online_api["enable_thinking"])
                if "thinking_budget" in online_api:
                    self.online_api_thinking_budget_var.set(online_api["thinking_budget"])
            
            # 加载表格配置
            if "table" in config:
                table = config["table"]
                if "table_file" in table:
                    self.table_var.set(table["table_file"])
                if "output_file" in table:
                    self.output_file_var.set(table["output_file"])
                if "output_columns" in table:
                    self.output_columns_var.set(table["output_columns"])
                if "max_workers" in table:
                    self.max_workers_var.set(table["max_workers"])
                if "api_delay" in table:
                    self.api_delay_var.set(table["api_delay"])
            
            # 加载批处理配置
            if "batch_processing" in config:
                batch = config["batch_processing"]
                if "enabled" in batch:
                    self.batch_processing_var.set(batch["enabled"])
                if "model" in batch:
                    self.batch_model_var.set(batch["model"])
                if "output_dir" in batch:
                    self.batch_output_dir_var.set(batch["output_dir"])
                if "task_id" in batch:
                    self.batch_task_id_var.set(batch["task_id"])
                if "temperature" in batch:
                    self.batch_temperature_var.set(batch["temperature"])
                if "max_tokens" in batch:
                    self.batch_max_tokens_var.set(batch["max_tokens"])
                if "top_p" in batch:
                    self.batch_top_p_var.set(batch["top_p"])
                if "enable_thinking" in batch:
                    self.batch_enable_thinking_var.set(batch["enable_thinking"])
                if "thinking_budget" in batch:
                    self.batch_thinking_budget_var.set(batch["thinking_budget"])
            
            # 加载Prompt配置
            if "prompt" in config:
                self.prompt_text.delete(1.0, tk.END)
                self.prompt_text.insert(1.0, config["prompt"])
            
            # 加载监控配置
            if "monitor" in config:
                monitor = config["monitor"]
                if "enabled" in monitor:
                    self.monitor_enabled_var.set(monitor["enabled"])
                    # 更新监控显示状态
                    self.on_monitor_enabled_changed()
                if "rpm_limit" in monitor:
                    self.rpm_limit_var.set(monitor["rpm_limit"])
                if "tpm_limit" in monitor:
                    self.tpm_limit_var.set(monitor["tpm_limit"])
                if "total_tokens_limit" in monitor:
                    self.total_tokens_limit_var.set(monitor["total_tokens_limit"])
            
            # 如果加载了表格文件，自动分析列名
            if "table" in config and "table_file" in config["table"]:
                table_file = config["table"]["table_file"]
                if table_file and os.path.exists(table_file):
                    self.auto_analyze_columns()
            
            # 加载论文爬虫配置
            if "crawler" in config:
                crawler = config["crawler"]
                if "source" in crawler:
                    self.crawler_source_var.set(crawler["source"])
                if "start_date" in crawler:
                    self.crawler_start_date_var.set(crawler["start_date"])
                if "end_date" in crawler:
                    self.crawler_end_date_var.set(crawler["end_date"])
                if "output_file" in crawler:
                    self.crawler_output_file_var.set(crawler["output_file"])
                if "selected_categories" in crawler:
                    # 保存选中的分类代码，稍后在listbox创建后恢复
                    selected_categories = crawler["selected_categories"]
                    if isinstance(selected_categories, list):
                        self._saved_category_selection = set(selected_categories)
            
            self.log("✓ 配置已加载", "SUCCESS")
        except Exception as e:
            self.log(f"加载配置失败: {e}，使用默认配置", "WARN")
    
    def save_models_cache(self):
        """保存模型缓存到文件"""
        try:
            cache_data = {
                "models": self.ollama_models_cache,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(MODELS_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # 静默失败，不影响主程序
            pass
    
    def load_models_cache(self):
        """从文件加载模型缓存"""
        try:
            if os.path.exists(MODELS_CACHE_FILE):
                with open(MODELS_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    if "models" in cache_data:
                        self.ollama_models_cache = cache_data["models"]
                        # 更新模型下拉框
                        if hasattr(self, 'model_combo') and self.model_combo and self.ollama_models_cache:
                            model_list = sorted(self.ollama_models_cache.keys())
                            self.model_combo['values'] = model_list
                            
                            # 如果当前选择的模型有缓存的大小信息，更新模型大小下拉列表
                            current_model = self.model_var.get() if hasattr(self, 'model_var') else None
                            if current_model and current_model in self.ollama_models_cache:
                                sizes = self.ollama_models_cache[current_model]
                                if sizes and hasattr(self, 'model_size_combo') and self.model_size_combo:
                                    self.model_size_combo['values'] = sorted(sizes, key=lambda x: (len(x), x))
                                    self.model_size_combo['state'] = 'readonly'
                                    if sizes:
                                        self.model_size_var.set(sizes[0])  # 默认选择第一个
                        
                        # 如果有最后更新时间，显示在日志中
                        if "last_updated" in cache_data:
                            self.log(f"已加载模型缓存（最后更新: {cache_data['last_updated']}）", "INFO")
                        else:
                            self.log(f"已加载 {len(self.ollama_models_cache)} 个模型的缓存", "INFO")
        except Exception as e:
            # 静默失败，如果缓存文件损坏，使用空缓存
            self.ollama_models_cache = {}
        
        # 如果缓存为空，使用默认模型列表（不自动从官网获取）
        if not self.ollama_models_cache:
            # 使用默认模型列表初始化
            for model_name in DEFAULT_MODELS:
                self.ollama_models_cache[model_name] = []
            # 更新模型下拉框
            if hasattr(self, 'model_combo') and self.model_combo:
                self.model_combo['values'] = DEFAULT_MODELS
                
                # 如果当前选择的模型有缓存的大小信息，更新模型大小下拉列表
                current_model = self.model_var.get() if hasattr(self, 'model_var') else None
                if current_model and current_model in self.ollama_models_cache:
                    sizes = self.ollama_models_cache[current_model]
                    if sizes and hasattr(self, 'model_size_combo') and self.model_size_combo:
                        self.model_size_combo['values'] = sorted(sizes, key=lambda x: (len(x), x))
                        self.model_size_combo['state'] = 'readonly'
                        if sizes:
                            self.model_size_var.set(sizes[0])  # 默认选择第一个
            self.log(f"使用默认模型列表（共 {len(DEFAULT_MODELS)} 个模型）", "INFO")
            self.log("如需更新模型列表，请点击'刷新'按钮", "INFO")
        
        # 加载模型大小下拉列表（如果当前选择的模型有缓存）
        if hasattr(self, 'model_var') and hasattr(self, 'model_size_combo') and self.model_size_combo:
            try:
                self.on_model_selected()
            except:
                pass  # 如果出错，静默失败
    
    def on_closing(self):
        """关闭窗口时的处理"""
        if self.is_running:
            if messagebox.askokcancel("退出", "程序正在运行，确定要退出吗？"):
                self.stop_research()
                time.sleep(1)
        
        # 保存配置
        self.save_config()
        
        # 保存模型缓存
        self.save_models_cache()
        
        # 停止Ollama模型以节省资源
        self.log("正在停止Ollama模型以节省资源...")
        self.stop_ollama_model()
        time.sleep(0.5)
        
        # 关闭SSH隧道（paramiko）
        if self.ssh_client:
            try:
                self.ssh_client.close()
                self.log("✓ SSH隧道（paramiko）已关闭", "SUCCESS")
            except:
                pass
            self.ssh_client = None
        
        
        # 释放本地端口
        try:
            local_port = int(self.local_port_var.get())
            self.log(f"正在释放本地端口 {local_port}...")
            self.kill_process_on_port(local_port)
            time.sleep(0.5)
        except Exception as e:
            self.log(f"释放端口时出错: {e}", "WARN")
        
        # 检查是否有待更新的文件，如果有则创建批处理脚本自动替换
        if self.pending_update_file and os.path.exists(self.pending_update_file):
            try:
                if hasattr(sys, '_MEIPASS'):
                    # 打包后的exe环境
                    current_exe = sys.executable
                    exe_dir = os.path.dirname(current_exe)
                    exe_name = os.path.basename(current_exe)
                    
                    # 创建批处理脚本来替换exe
                    temp_dir = tempfile.gettempdir()
                    batch_file = os.path.join(temp_dir, f"PaperResearchTool_update_{int(time.time())}.bat")
                    
                    with open(batch_file, 'w', encoding='utf-8') as f:
                        f.write('@echo off\n')
                        f.write('chcp 65001 >nul\n')  # 设置UTF-8编码
                        f.write('timeout /t 2 /nobreak >nul\n')  # 等待2秒确保程序完全关闭
                        f.write(f'if exist "{current_exe}" (\n')
                        f.write(f'    del /f /q "{current_exe}"\n')
                        f.write(')\n')
                        f.write(f'if exist "{self.pending_update_file}" (\n')
                        f.write(f'    move /y "{self.pending_update_file}" "{current_exe}"\n')
                        f.write(f'    echo 更新完成！\n')
                        f.write(')\n')
                        f.write(f'del /f /q "%~f0"\n')  # 删除批处理脚本自身
                    
                    # 以隐藏窗口方式运行批处理脚本
                    subprocess.Popen(['cmd.exe', '/c', batch_file], 
                                    creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    # 开发环境，提示手动替换
                    messagebox.showinfo("更新提示", 
                        f"更新文件已下载到：\n{self.pending_update_file}\n\n"
                        f"请手动替换程序文件。", 
                        parent=self.root)
            except Exception as e:
                self.log(f"创建自动更新脚本时出错: {e}", "WARN")
        
        self.root.destroy()
    
    def check_for_updates(self):
        """检查GitHub Release是否有新版本"""
        def check_in_thread():
            try:
                # 请求GitHub API获取最新版本
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "PaperResearchTool"
                }
                response = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
                response.raise_for_status()
                
                release_data = response.json()
                latest_version = release_data.get("tag_name", "").lstrip("v")  # 移除可能的"v"前缀
                release_url = release_data.get("html_url", "")
                release_notes = release_data.get("body", "")
                
                # 比较版本号
                current_version = CURRENT_VERSION
                has_update = self._compare_versions(current_version, latest_version)
                
                # 在主线程中显示结果
                if has_update:
                    # 有新版本
                    msg = f"发现新版本！\n\n当前版本: v{current_version}\n最新版本: v{latest_version}\n\n是否下载更新？"
                    result = messagebox.askyesno("发现新版本", msg, parent=self.root)
                    if result:
                        self._download_update(release_data)
                else:
                    # 已是最新版本
                    messagebox.showinfo("检查更新", f"当前已是最新版本！\n\n当前版本: v{current_version}", parent=self.root)
                    
            except requests.exceptions.RequestException as e:
                self.root.after(0, lambda: messagebox.showerror("检查更新失败", f"无法连接到GitHub检查更新：\n{str(e)}", parent=self.root))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("检查更新失败", f"检查更新时出错：\n{str(e)}", parent=self.root))
        
        # 在后台线程中检查更新
        threading.Thread(target=check_in_thread, daemon=True).start()
    
    def _compare_versions(self, current, latest):
        """比较版本号，返回True表示latest版本更新"""
        try:
            current_parts = [int(x) for x in current.split('.')]
            latest_parts = [int(x) for x in latest.split('.')]
            
            # 补齐长度
            max_len = max(len(current_parts), len(latest_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            latest_parts.extend([0] * (max_len - len(latest_parts)))
            
            # 逐位比较
            for i in range(max_len):
                if latest_parts[i] > current_parts[i]:
                    return True
                elif latest_parts[i] < current_parts[i]:
                    return False
            return False  # 版本相同
        except:
            # 如果版本号格式不正确，使用字符串比较
            return latest > current
    
    def _download_update(self, release_data):
        """下载更新"""
        try:
            # 获取下载链接（查找Windows exe文件）
            assets = release_data.get("assets", [])
            download_url = None
            filename = None
            
            for asset in assets:
                name = asset.get("name", "")
                if name.endswith(".exe") or name.endswith(".zip"):
                    download_url = asset.get("browser_download_url", "")
                    filename = name
                    break
            
            if not download_url:
                messagebox.showwarning("下载更新", "未找到可下载的更新文件（.exe或.zip）", parent=self.root)
                return
            
            # 检查是否是exe文件，如果是则自动替换
            is_exe = filename.endswith(".exe")
            if is_exe:
                # 自动替换模式：下载到临时目录
                temp_dir = tempfile.gettempdir()
                save_path = os.path.join(temp_dir, f"PaperResearchTool_update_{int(time.time())}.exe")
                auto_replace = True
            else:
                # zip文件：询问保存位置
                save_path = filedialog.asksaveasfilename(
                    title="保存更新文件",
                    initialfile=filename,
                    defaultextension=".zip",
                    filetypes=[("压缩文件", "*.zip"), ("所有文件", "*.*")]
                )
                if not save_path:
                    return  # 用户取消
                auto_replace = False
            
            # 显示下载进度窗口
            progress_window = tk.Toplevel(self.root)
            progress_window.title("下载更新")
            progress_window.geometry("400x150")
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            progress_label = tk.Label(progress_window, text=f"正在下载: {filename}", font=(self.chinese_font, 10))
            progress_label.pack(pady=10)
            
            progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=100, length=300)
            progress_bar.pack(pady=10)
            
            status_label = tk.Label(progress_window, text="准备下载...", font=(self.chinese_font, 9))
            status_label.pack(pady=5)
            
            def download_in_thread():
                try:
                    response = requests.get(download_url, stream=True, timeout=30)
                    response.raise_for_status()
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(save_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    progress = (downloaded / total_size) * 100
                                    progress_var.set(progress)
                                    status_label.config(text=f"已下载: {downloaded / 1024 / 1024:.2f} MB / {total_size / 1024 / 1024:.2f} MB")
                                    progress_window.update()
                    
                    progress_window.after(0, lambda: progress_window.destroy())
                    
                    if auto_replace:
                        # 自动替换模式：保存待更新文件路径，程序关闭时自动替换
                        self.pending_update_file = save_path
                        current_exe = sys.executable if hasattr(sys, '_MEIPASS') else __file__
                        if not hasattr(sys, '_MEIPASS'):
                            # 开发环境，提示手动替换
                            messagebox.showinfo("下载完成", 
                                f"更新文件已下载到：\n{save_path}\n\n"
                                f"程序将在关闭时自动替换。请关闭程序以完成更新。", 
                                parent=self.root)
                        else:
                            # 打包后的exe，可以自动替换
                            messagebox.showinfo("下载完成", 
                                f"更新文件已下载完成！\n\n"
                                f"程序将在关闭时自动替换为最新版本。\n"
                                f"请关闭程序以完成更新。", 
                                parent=self.root)
                    else:
                        # 手动安装模式
                        messagebox.showinfo("下载完成", f"更新文件已下载到：\n{save_path}\n\n请手动安装更新。", parent=self.root)
                    
                except Exception as e:
                    progress_window.after(0, lambda: progress_window.destroy())
                    messagebox.showerror("下载失败", f"下载更新文件时出错：\n{str(e)}", parent=self.root)
            
            threading.Thread(target=download_in_thread, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("下载更新", f"准备下载时出错：\n{str(e)}", parent=self.root)


def main():
    """主函数"""
    root = tk.Tk()
    app = ResearchGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

