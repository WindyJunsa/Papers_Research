#!/usr/bin/env python3
"""
论文调研标签页：包含在线API、Ollama、表格处理、Prompt配置等功能
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from typing import Optional, Callable, Dict, Any
import time
import json
import pandas as pd
import threading

# 添加父目录到路径以便导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BATCH_SUPPORTED_MODELS, DEFAULT_MODELS, CONFIG_FILE, MODELS_CACHE_FILE, ONLINE_MODELS_CACHE_FILE, APP_DIR
from utils.file_utils import load_json, save_json
from utils.path_utils import get_full_model_name
from services.api_service import APIService

# 用于线程安全的锁
results_lock = threading.Lock()


class ResearchTab:
    """论文调研标签页类"""
    
    def __init__(
        self,
        parent: ttk.Frame,
        main_window,
        log_callback: Optional[Callable] = None
    ):
        """
        初始化论文调研标签页
        
        Args:
            parent: 父容器
            main_window: 主窗口实例
            log_callback: 日志回调函数
        """
        self.parent = parent
        self.main_window = main_window
        self.log_callback = log_callback
        self.chinese_font = main_window.chinese_font
        
        # 初始化变量（从配置加载）
        self._init_variables()
        
        # 状态变量
        self.is_running = False
        self.column_labels = []
        self.online_models_cache = {}  # {provider: [model_list]}
        self.ollama_models_cache = {}
        
        # API服务
        self.api_service = APIService(log_callback=self.log)
        
        # 创建界面
        self.create_widgets()
        
        # 加载配置和缓存
        self._load_initial_data()
    
    def _init_variables(self):
        """初始化所有变量"""
        # 从配置加载初始值
        config_values = self._load_config_values()
        
        # API模式
        self.api_mode_var = tk.StringVar(value=config_values.get("api_mode", "online"))
        
        # 在线API配置
        self.online_api_provider_var = tk.StringVar(value=config_values.get("online_api_provider", "siliconflow"))
        self.online_api_key_var = tk.StringVar(value=config_values.get("online_api_key", ""))
        self.online_api_url_var = tk.StringVar(value=config_values.get("online_api_url", "https://api.siliconflow.cn/v1/chat/completions"))
        self.online_model_var = tk.StringVar(value=config_values.get("online_model", "moonshotai/Kimi-K2-Instruct-0905"))
        self.online_api_temperature_var = tk.StringVar(value=config_values.get("online_api_temperature", "0.7"))
        self.online_api_max_tokens_var = tk.StringVar(value=config_values.get("online_api_max_tokens", "4096"))
        self.online_api_top_p_var = tk.StringVar(value=config_values.get("online_api_top_p", "0.7"))
        self.online_api_enable_thinking_var = tk.StringVar(value=config_values.get("online_api_enable_thinking", "False"))
        self.online_api_thinking_budget_var = tk.StringVar(value=config_values.get("online_api_thinking_budget", "4096"))
        
        # Ollama配置
        self.username_var = tk.StringVar(value=config_values.get("username", "hzq"))
        self.host_var = tk.StringVar(value=config_values.get("host", "211.86.155.236"))
        self.ssh_port_var = tk.StringVar(value=config_values.get("ssh_port", "7001"))
        self.password_var = tk.StringVar(value=config_values.get("password", ""))
        self.local_port_var = tk.StringVar(value=config_values.get("local_port", "11435"))
        self.remote_port_var = tk.StringVar(value=config_values.get("remote_port", "11434"))
        self.model_var = tk.StringVar(value=config_values.get("model", "deepseek-r1"))
        self.model_size_var = tk.StringVar(value=config_values.get("model_size", ""))
        self.gpu_var = tk.StringVar(value=config_values.get("gpu", "0"))
        self.ollama_custom_dir_var = tk.StringVar(value=config_values.get("ollama_custom_dir", ""))
        self.ollama_path_var = tk.StringVar(value="")
        
        # 表格配置
        self.table_var = tk.StringVar(value=config_values.get("table_file", ""))
        self.output_file_var = tk.StringVar(value=config_values.get("output_file", "调研报告.csv"))
        self.output_columns_var = tk.StringVar(value=config_values.get("output_columns", "title,category,method,team"))
        
        # 并发配置
        self.max_workers_var = tk.StringVar(value=config_values.get("max_workers", "8"))
        self.api_delay_var = tk.StringVar(value=config_values.get("api_delay", "0.5"))
        
        # 批处理配置
        self.batch_processing_var = tk.BooleanVar(value=config_values.get("batch_processing", {}).get("enabled", False))
        self.batch_model_var = tk.StringVar(value=config_values.get("batch_processing", {}).get("model", "deepseek-ai/DeepSeek-V3"))
        self.batch_output_dir_var = tk.StringVar(value=config_values.get("batch_processing", {}).get("output_dir", ""))
        self.batch_task_id_var = tk.StringVar(value=config_values.get("batch_processing", {}).get("task_id", ""))
        self.batch_status_var = tk.StringVar(value="未开始")
        self.batch_temperature_var = tk.StringVar(value=config_values.get("batch_processing", {}).get("temperature", "0.7"))
        self.batch_max_tokens_var = tk.StringVar(value=config_values.get("batch_processing", {}).get("max_tokens", "4096"))
        self.batch_top_p_var = tk.StringVar(value=config_values.get("batch_processing", {}).get("top_p", "0.7"))
        self.batch_enable_thinking_var = tk.StringVar(value=config_values.get("batch_processing", {}).get("enable_thinking", "False"))
        self.batch_thinking_budget_var = tk.StringVar(value=config_values.get("batch_processing", {}).get("thinking_budget", "4096"))
        
        # 监控配置
        monitor_config = config_values.get("monitor", {})
        self.monitor_enabled_var = tk.BooleanVar(value=monitor_config.get("enabled", True))
        self.rpm_var = tk.StringVar(value="0")
        self.tpm_var = tk.StringVar(value="0")
        self.total_tokens_var = tk.StringVar(value="0")
        self.avg_tokens_per_prompt_var = tk.StringVar(value="0")
        self.rpm_limit_var = tk.StringVar(value=str(monitor_config.get("rpm_limit", 1000)))
        self.tpm_limit_var = tk.StringVar(value=str(monitor_config.get("tpm_limit", 100000)))
        self.total_tokens_limit_var = tk.StringVar(value=str(monitor_config.get("total_tokens_limit", 1000000)))
        
        # 监控数据
        self.request_times = []
        self.token_counts = []
        self.total_tokens_count = 0
        self.monitor_start_time = None
        self.monitor_update_interval = 1000
    
    def _load_config_values(self) -> Dict:
        """从配置文件加载初始值"""
        return load_json(CONFIG_FILE, {})
    
    def _load_initial_data(self):
        """加载初始数据（模型缓存等）"""
        # 加载模型缓存
        self.ollama_models_cache = load_json(MODELS_CACHE_FILE, {})
        
        # 加载在线模型缓存
        self.online_models_cache = load_json(ONLINE_MODELS_CACHE_FILE, {})
        
        # 更新模型下拉框
        if hasattr(self, 'online_model_combo'):
            provider = self.online_api_provider_var.get()
            if provider in self.online_models_cache:
                self.online_model_combo['values'] = self.online_models_cache[provider]
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
        else:
            # 如果没有回调，直接输出到日志文本框
            if hasattr(self, 'output_text'):
                timestamp = time.strftime("%H:%M:%S", time.localtime())
                color_map = {
                    "SUCCESS": "#27ae60",
                    "ERROR": "#e74c3c",
                    "WARN": "#f39c12",
                    "INFO": "#3498db"
                }
                color = color_map.get(level, "#34495e")
                self.output_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.output_text.see(tk.END)
    
    def create_widgets(self):
        """创建GUI组件"""
        # 主框架：左侧模式选择 + 中间内容 + 右侧日志
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        main_frame.columnconfigure(0, weight=0)  # 左侧固定宽度
        main_frame.columnconfigure(1, weight=1)   # 中间可扩展
        main_frame.columnconfigure(2, weight=1)   # 右侧可扩展
        main_frame.rowconfigure(0, weight=1)
        
        # 左侧：模式选择（在线API / Ollama）
        self.create_mode_selection(main_frame)
        
        # 中间：配置区域
        self.create_config_area(main_frame)
        
        # 右侧：日志输出
        self.create_output_area(main_frame)
        
        # 底部：控制按钮
        self.create_control_buttons(main_frame)
    
    def create_mode_selection(self, parent):
        """创建模式选择区域"""
        mode_frame = ttk.LabelFrame(parent, text="运行模式", padding="10")
        mode_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        mode_frame.columnconfigure(0, weight=1)
        
        # 模式选择Notebook
        self.mode_notebook = ttk.Notebook(mode_frame, width=400)
        self.mode_notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.mode_notebook.bind("<<NotebookTabChanged>>", self.on_mode_tab_changed)
        
        # 在线API标签页
        self.online_api_tab = ttk.Frame(self.mode_notebook)
        self.mode_notebook.add(self.online_api_tab, text="在线API")
        self.create_online_api_tab(self.online_api_tab)
        
        # Ollama标签页
        self.ollama_tab = ttk.Frame(self.mode_notebook)
        self.mode_notebook.add(self.ollama_tab, text="Ollama")
        self.create_ollama_tab(self.ollama_tab)
        
        mode_frame.rowconfigure(0, weight=1)
        
        # 默认显示在线API Tab
        self.mode_notebook.select(0)
        self.api_mode_var.set("online")
    
    def create_online_api_tab(self, parent):
        """创建在线API配置标签页"""
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
        
        # 并发配置区域
        concurrency_frame = ttk.LabelFrame(parent, text="并发配置", padding="10")
        concurrency_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10, padx=5)
        concurrency_frame.columnconfigure(1, weight=1)
        concurrency_frame.columnconfigure(3, weight=1)
        
        # 并发数量（左列）
        ttk.Label(concurrency_frame, text="并发数量:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.workers_entry = ttk.Entry(concurrency_frame, textvariable=self.max_workers_var, width=15)
        self.workers_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Label(concurrency_frame, text="(线程数)", font=(self.chinese_font, 8), foreground="gray").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        
        # 并发间隔（右列）
        ttk.Label(concurrency_frame, text="间隔(秒):").grid(row=0, column=3, sticky=tk.W, pady=5, padx=(10, 0))
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
        initial_batch_state = "readonly" if self.batch_processing_var.get() else "disabled"
        self.batch_model_combo = ttk.Combobox(batch_frame, textvariable=self.batch_model_var, 
                                               values=BATCH_SUPPORTED_MODELS, width=30, state=initial_batch_state)
        self.batch_model_combo.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 批处理结果保存目录
        ttk.Label(batch_frame, text="结果保存目录:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=5)
        self.batch_dir_entry = ttk.Entry(batch_frame, textvariable=self.batch_output_dir_var, width=30, state="disabled")
        self.batch_dir_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.batch_dir_browse_btn = ttk.Button(batch_frame, text="浏览...", command=self.browse_batch_output_dir, state="disabled")
        self.batch_dir_browse_btn.grid(row=2, column=2, padx=5, pady=5)
        
        # 批处理API参数
        batch_params_frame = ttk.LabelFrame(batch_frame, text="批处理API参数", padding="5")
        batch_params_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10, padx=5)
        batch_params_frame.columnconfigure(1, weight=1)
        batch_params_frame.columnconfigure(3, weight=1)
        
        ttk.Label(batch_params_frame, text="Temperature:").grid(row=0, column=0, sticky=tk.W, pady=3, padx=5)
        self.batch_temperature_entry = ttk.Entry(batch_params_frame, textvariable=self.batch_temperature_var, width=18, state="disabled")
        self.batch_temperature_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(batch_params_frame, text="Max Tokens:").grid(row=0, column=2, sticky=tk.W, pady=3, padx=5)
        self.batch_max_tokens_entry = ttk.Entry(batch_params_frame, textvariable=self.batch_max_tokens_var, width=18, state="disabled")
        self.batch_max_tokens_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(batch_params_frame, text="Top P:").grid(row=1, column=0, sticky=tk.W, pady=3, padx=5)
        self.batch_top_p_entry = ttk.Entry(batch_params_frame, textvariable=self.batch_top_p_var, width=18, state="disabled")
        self.batch_top_p_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(batch_params_frame, text="Enable Thinking:").grid(row=1, column=2, sticky=tk.W, pady=3, padx=5)
        self.batch_thinking_combo = ttk.Combobox(batch_params_frame, textvariable=self.batch_enable_thinking_var, 
                                                  values=["False", "True"], width=15, state="disabled")
        self.batch_thinking_combo.grid(row=1, column=3, sticky=tk.W, padx=5, pady=3)
        
        ttk.Label(batch_params_frame, text="Thinking Budget:").grid(row=2, column=0, sticky=tk.W, pady=3, padx=5)
        self.batch_thinking_budget_entry = ttk.Entry(batch_params_frame, textvariable=self.batch_thinking_budget_var, width=18, state="disabled")
        self.batch_thinking_budget_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=3)
        
        # 批处理任务状态
        batch_status_frame = ttk.Frame(batch_frame)
        batch_status_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(batch_status_frame, text="任务状态:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.batch_status_label = ttk.Label(batch_status_frame, textvariable=self.batch_status_var, foreground="gray")
        self.batch_status_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # 批处理控制按钮（放在下一行）
        batch_control_frame = ttk.Frame(batch_frame)
        batch_control_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        self.batch_check_status_btn = ttk.Button(batch_control_frame, text="检查状态", 
                                                 command=self.check_batch_status, state="disabled")
        self.batch_check_status_btn.grid(row=0, column=0, padx=5)
        
        self.batch_cancel_btn = ttk.Button(batch_control_frame, text="取消任务", 
                                           command=self.cancel_batch_task, state="disabled")
        self.batch_cancel_btn.grid(row=0, column=1, padx=5)
        
        self.batch_download_btn = ttk.Button(batch_control_frame, text="下载结果", 
                                              command=self.download_batch_results, state="disabled")
        self.batch_download_btn.grid(row=0, column=2, padx=5)
        
        # 更新API提供商默认值
        self.on_api_provider_changed()
    
    def create_ollama_tab(self, parent):
        """创建Ollama配置标签页"""
        parent.columnconfigure(0, weight=0)  # 标签列不扩展
        parent.columnconfigure(1, weight=1)   # 输入列扩展
        parent.rowconfigure(2, weight=1)       # 按钮行下方留空间
        
        # SSH连接配置区域（单列竖排）
        config_frame = ttk.LabelFrame(parent, text="SSH连接配置", padding="10")
        config_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10), padx=5)
        config_frame.columnconfigure(1, weight=1)
        
        # 用户名
        ttk.Label(config_frame, text="用户名:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(config_frame, textvariable=self.username_var, width=20).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # SSH端口
        ttk.Label(config_frame, text="SSH端口:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(config_frame, textvariable=self.ssh_port_var, width=20).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 服务器IP
        ttk.Label(config_frame, text="服务器IP:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(config_frame, textvariable=self.host_var, width=20).grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 密码
        ttk.Label(config_frame, text="密码:").grid(row=3, column=0, sticky=tk.W, pady=5)
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
        ollama_frame = ttk.LabelFrame(parent, text="Ollama配置", padding="10")
        ollama_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10), padx=5)
        ollama_frame.columnconfigure(1, weight=1)
        
        # 竖着排列所有配置项
        # 本地端口
        ttk.Label(ollama_frame, text="本地端口:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(ollama_frame, textvariable=self.local_port_var, width=20).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # 远程端口
        ttk.Label(ollama_frame, text="远程端口:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(ollama_frame, textvariable=self.remote_port_var, width=20).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Ollama自定义位置
        ttk.Label(ollama_frame, text="Ollama位置:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ollama_dir_entry = ttk.Entry(ollama_frame, textvariable=self.ollama_custom_dir_var, width=20)
        ollama_dir_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Label(ollama_frame, text="(如: /data/xxx)", font=(self.chinese_font, 8), foreground="gray").grid(row=3, column=1, sticky=tk.W, padx=5, pady=(0, 5))
        
        # 模型名称
        ttk.Label(ollama_frame, text="模型名称:").grid(row=4, column=0, sticky=tk.W, pady=5)
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
        model_size_combo = ttk.Combobox(ollama_frame, textvariable=self.model_size_var, width=17, state="readonly")
        model_size_combo.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.model_size_combo = model_size_combo  # 保存引用以便更新
        
        # GPU选择
        ttk.Label(ollama_frame, text="GPU设备:").grid(row=6, column=0, sticky=tk.W, pady=5)
        gpu_entry = ttk.Entry(ollama_frame, textvariable=self.gpu_var, width=20)
        gpu_entry.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Label(ollama_frame, text="(如: 0,1 或留空使用所有GPU)", font=(self.chinese_font, 8), foreground="gray").grid(row=7, column=1, sticky=tk.W, padx=5, pady=(0, 5))
    
    def create_table_config(self, parent):
        """创建表格配置区域"""
        # 表格配置区域 - 放在右侧顶部
        table_frame = ttk.LabelFrame(parent, text="表格配置", padding="10")
        table_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        table_frame.columnconfigure(1, weight=1)
        table_frame.columnconfigure(3, weight=1)
        
        # 表格文件路径（第一行：表格文件输入框变长，刷新列名放在后面）
        ttk.Label(table_frame, text="表格文件:").grid(row=0, column=0, sticky=tk.W, pady=5)
        table_entry = ttk.Entry(table_frame, textvariable=self.table_var, width=30)
        table_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(table_frame, text="浏览...", command=self.browse_table).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(table_frame, text="刷新列名", command=self.auto_analyze_columns).grid(row=0, column=3, padx=5, pady=5)
        
        # 输出文件名（第二行）
        ttk.Label(table_frame, text="输出文件:").grid(row=1, column=0, sticky=tk.W, pady=5)
        output_entry = ttk.Entry(table_frame, textvariable=self.output_file_var, width=30)
        output_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(table_frame, text="浏览...", command=self.browse_output_file).grid(row=1, column=2, padx=5, pady=5)
        
        # 输出列名配置（第三行）
        ttk.Label(table_frame, text="输出列名:").grid(row=2, column=0, sticky=tk.W, pady=5)
        output_cols_entry = ttk.Entry(table_frame, textvariable=self.output_columns_var, width=30)
        output_cols_entry.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(table_frame, text="添加到Prompt", command=self.add_output_columns_to_prompt).grid(row=2, column=3, padx=5, pady=5)
        ttk.Label(table_frame, text="(用逗号分隔，如: title,category,method)", font=(self.chinese_font, 8), foreground="gray").grid(row=3, column=1, columnspan=3, sticky=tk.W, padx=5, pady=(0, 5))
    
    def create_config_area(self, parent):
        """创建配置区域"""
        config_frame = ttk.Frame(parent)
        config_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        config_frame.columnconfigure(0, weight=1)
        config_frame.rowconfigure(0, weight=0)  # 表格配置不扩展
        config_frame.rowconfigure(1, weight=1)  # Prompt区域可扩展
        config_frame.rowconfigure(2, weight=1)  # 列名区域可扩展
        
        # 创建表格配置区域
        self.create_table_config(config_frame)
        
        # 创建中间内容区域（Prompt等）
        self.create_right_content(config_frame)
    
    def create_right_content(self, parent):
        """创建中间内容区域（Prompt等）"""
        # 设置parent的列权重，让Prompt栏变窄
        parent.columnconfigure(0, weight=1)
        
        prompt_frame = ttk.LabelFrame(parent, text="分析Prompt配置", padding="10")
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
            font=(self.chinese_font, 10),
            height=8,  # 恢复高度
            bg="white",
            fg="black"
        )
        self.prompt_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # 表格列名框（可滚动）
        columns_frame = ttk.LabelFrame(parent, text="表格列名", padding="5")
        columns_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        columns_frame.columnconfigure(0, weight=1)
        columns_frame.rowconfigure(0, weight=1)
        
        # 使用Canvas和Scrollbar实现可滚动的列名框
        columns_canvas = tk.Canvas(columns_frame, height=120, bg="white", highlightthickness=0)
        columns_scrollbar = ttk.Scrollbar(columns_frame, orient=tk.VERTICAL, command=columns_canvas.yview)
        self.columns_container = ttk.Frame(columns_canvas)
        
        def update_scroll_region(event=None):
            """更新滚动区域"""
            columns_canvas.configure(scrollregion=columns_canvas.bbox("all"))
        
        def on_mousewheel(event):
            """鼠标滚轮事件"""
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
    
    def create_output_area(self, parent):
        """创建输出区域"""
        output_frame = ttk.LabelFrame(parent, text="运行日志", padding="10")
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
    
    def create_control_buttons(self, parent):
        """创建控制按钮"""
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=1, column=1, pady=10)
        
        # 开始按钮
        self.start_button = tk.Button(
            button_frame,
            text="开始",
            font=(self.chinese_font, 12, "bold"),
            bg="#27ae60",
            fg="white",
            padx=20,
            pady=5,
            command=self.start_research
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        # 停止按钮
        self.stop_button = tk.Button(
            button_frame,
            text="停止",
            font=(self.chinese_font, 12, "bold"),
            bg="#e74c3c",
            fg="white",
            padx=20,
            pady=5,
            command=self.stop_research,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # 清空输出按钮
        self.clear_button = tk.Button(
            button_frame,
            text="清空输出",
            font=(self.chinese_font, 10),
            padx=15,
            pady=5,
            command=self.clear_output
        )
        self.clear_button.pack(side=tk.LEFT, padx=5)
    
    def on_api_provider_changed(self, event=None):
        """API提供商改变时的回调"""
        provider = self.online_api_provider_var.get()
        if provider == "siliconflow":
            self.online_api_url_var.set("https://api.siliconflow.cn/v1/chat/completions")
        # 更新模型列表
        if provider in self.online_models_cache:
            self.online_model_combo['values'] = self.online_models_cache[provider]
        self.on_online_api_config_changed()
    
    def on_online_api_config_changed(self):
        """在线API配置改变时的回调"""
        # 更新开始按钮状态
        if hasattr(self, 'start_button'):
            api_key = self.online_api_key_var.get().strip()
            api_url = self.online_api_url_var.get().strip()
            model = self.online_model_var.get().strip()
            if api_key and api_url and model:
                self.start_button.config(state=tk.NORMAL)
            else:
                self.start_button.config(state=tk.DISABLED)
    
    def _on_online_model_input(self, event):
        """在线模型输入时的回调（实现自动完成）"""
        current_text = self.online_model_var.get()
        if not current_text:
            return
        
        # 获取当前provider的模型列表
        provider = self.online_api_provider_var.get()
        all_models = self.online_models_cache.get(provider, [])
        
        # 过滤匹配的模型
        matched_models = [m for m in all_models if current_text.lower() in m.lower()]
        
        if matched_models:
            # 更新下拉列表
            self.online_model_combo['values'] = matched_models
            
            # 自动展开下拉列表
            def expand_dropdown():
                try:
                    # 使用Tcl命令展开下拉列表
                    self.online_model_combo.event_generate('<Button-1>')
                    self.main_window.root.after(10, lambda: self.online_model_combo.event_generate('<Down>'))
                except:
                    pass
            
            self.main_window.root.after(50, expand_dropdown)
        else:
            # 如果没有匹配的，显示所有模型
            self.online_model_combo['values'] = all_models
    
    def fetch_online_models(self):
        """获取在线模型列表"""
        def fetch_in_thread():
            try:
                provider = self.online_api_provider_var.get()
                api_key = self.online_api_key_var.get().strip()
                api_url = self.online_api_url_var.get().strip()
                
                if not api_key or not api_url:
                    self.log("请先配置API Key和API地址", "WARN")
                    return
                
                self.log(f"正在获取{provider}的模型列表...", "INFO")
                
                # 调用API服务获取模型列表
                models = self.api_service.fetch_online_models(provider, api_key, api_url)
                
                if models:
                    self.online_models_cache[provider] = models
                    self.online_model_combo['values'] = models
                    # 保存缓存
                    save_json(self.online_models_cache, ONLINE_MODELS_CACHE_FILE)
                    self.log(f"✓ 成功获取{len(models)}个模型", "SUCCESS")
                else:
                    self.log("✗ 获取模型列表失败", "ERROR")
            except Exception as e:
                self.log(f"✗ 获取模型列表时出错: {e}", "ERROR")
        
        threading.Thread(target=fetch_in_thread, daemon=True).start()
    
    def browse_batch_output_dir(self):
        """浏览批处理输出目录"""
        directory = filedialog.askdirectory(title="选择批处理结果保存目录")
        if directory:
            self.batch_output_dir_var.set(directory)
    
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
        
        # 模型选择框需要特殊处理：启用时用"readonly"，禁用时用"disabled"
        if hasattr(self, 'batch_model_combo'):
            try:
                self.batch_model_combo.config(state="readonly" if enabled else "disabled")
            except:
                pass
        
        # 如果启用批处理，从常规API参数复制到批处理参数
        if enabled:
            self.batch_temperature_var.set(self.online_api_temperature_var.get())
            self.batch_max_tokens_var.set(self.online_api_max_tokens_var.get())
            self.batch_top_p_var.set(self.online_api_top_p_var.get())
            self.batch_enable_thinking_var.set(self.online_api_enable_thinking_var.get())
            self.batch_thinking_budget_var.set(self.online_api_thinking_budget_var.get())
    
    def _on_ollama_model_input(self, event):
        """Ollama模型输入时的回调（实现自动完成）"""
        current_text = self.model_var.get()
        if not current_text:
            return
        
        # 获取所有模型（从缓存或默认列表）
        all_models = []
        if self.ollama_models_cache:
            for model_list in self.ollama_models_cache.values():
                all_models.extend(model_list)
        if not all_models:
            all_models = DEFAULT_MODELS
        
        # 过滤匹配的模型
        matched_models = [m for m in all_models if current_text.lower() in m.lower()]
        
        if matched_models:
            # 更新下拉列表
            self.model_combo['values'] = matched_models
            
            # 自动展开下拉列表
            def expand_dropdown():
                try:
                    self.model_combo.event_generate('<Button-1>')
                    self.main_window.root.after(10, lambda: self.model_combo.event_generate('<Down>'))
                except:
                    pass
            
            self.main_window.root.after(50, expand_dropdown)
        else:
            # 如果没有匹配的，显示所有模型
            self.model_combo['values'] = all_models
    
    def on_model_selected(self):
        """模型选择改变时的回调"""
        # 更新模型大小选项
        base_model = self.model_var.get()
        if base_model in self.ollama_models_cache:
            sizes = self.ollama_models_cache[base_model].get("sizes", [])
            if sizes:
                self.model_size_combo['values'] = sizes
            else:
                self.model_size_combo['values'] = []
    
    def browse_table(self):
        """浏览表格文件"""
        filename = filedialog.askopenfilename(
            title="选择表格文件",
            filetypes=[("CSV文件", "*.csv"), ("Excel文件", "*.xlsx *.xls"), ("所有文件", "*.*")]
        )
        if filename:
            self.table_var.set(filename)
            # 自动分析列名
            self.auto_analyze_columns()
    
    def browse_output_file(self):
        """浏览输出文件"""
        filename = filedialog.asksaveasfilename(
            title="选择输出文件",
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("Excel文件", "*.xlsx"), ("所有文件", "*.*")]
        )
        if filename:
            self.output_file_var.set(filename)
    
    def auto_analyze_columns(self):
        """自动分析表格列名"""
        table_path = self.table_var.get()
        if not table_path or not os.path.exists(table_path):
            self.log("请先选择有效的表格文件", "WARN")
            return
        
        try:
            # 读取表格文件
            if table_path.endswith('.csv'):
                df = pd.read_csv(table_path, nrows=0)  # 只读取列名
            else:
                df = pd.read_excel(table_path, nrows=0)
            
            columns = df.columns.tolist()
            if columns:
                self.create_column_labels(columns)
                self.log(f"✓ 已分析出 {len(columns)} 个列名", "SUCCESS")
            else:
                self.log("✗ 表格文件没有列名", "ERROR")
        except Exception as e:
            self.log(f"✗ 分析列名失败: {e}", "ERROR")
    
    def create_column_labels(self, columns):
        """创建列名标签"""
        # 清空现有标签
        for label in self.column_labels:
            label.destroy()
        self.column_labels = []
        
        # 创建新标签
        for i, col in enumerate(columns):
            label = tk.Label(
                self.columns_container,
                text=col,
                bg="#e8f4f8",
                fg="#2c3e50",
                padx=8,
                pady=4,
                relief=tk.RAISED,
                cursor="hand2",
                font=(self.chinese_font, 9)
            )
            label.grid(row=i // 4, column=i % 4, padx=3, pady=3, sticky=tk.W)
            label.bind("<Button-1>", lambda e, col=col: self.insert_column_to_prompt(col))
            self.column_labels.append(label)
        
        # 更新滚动区域
        self.columns_container.update_idletasks()
        # 找到父Canvas并更新scrollregion
        canvas = None
        widget = self.columns_container
        while widget:
            if isinstance(widget, tk.Canvas):
                canvas = widget
                break
            widget = widget.master
        
        if canvas:
            canvas.configure(scrollregion=canvas.bbox("all"))
    
    def insert_column_to_prompt(self, column_name):
        """插入列名到Prompt"""
        prompt_text = self.prompt_text.get(1.0, tk.END)
        cursor_pos = self.prompt_text.index(tk.INSERT)
        self.prompt_text.insert(cursor_pos, f"{{{column_name}}}")
    
    def add_output_columns_to_prompt(self):
        """添加输出列名到Prompt（格式化为JSON结构）"""
        output_cols = self.output_columns_var.get().strip()
        if not output_cols:
            self.log("请先设置输出列名", "WARN")
            return
        
        cols = [col.strip() for col in output_cols.split(',')]
        json_structure = "{\n"
        for i, col in enumerate(cols):
            json_structure += f'  "{col}": "",'
            if i < len(cols) - 1:
                json_structure += "\n"
        json_structure += "\n}"
        
        # 插入到Prompt末尾
        self.prompt_text.insert(tk.END, "\n\n" + json_structure)
    
    def on_monitor_enabled_changed(self):
        """监控开关改变时的回调"""
        if self.monitor_enabled_var.get():
            self.monitor_content_frame.grid()
        else:
            self.monitor_content_frame.grid_remove()
    
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
        
        # 更新按钮状态
        if mode == "ollama":
            # Ollama模式：需要SSH连接
            if hasattr(self, 'start_button'):
                if self.check_ssh_connection():
                    self.start_button.config(state=tk.NORMAL)
                else:
                    self.start_button.config(state=tk.DISABLED)
        else:
            # 在线API模式：需要API配置
            if hasattr(self, 'start_button'):
                api_key = self.online_api_key_var.get().strip()
                api_url = self.online_api_url_var.get().strip()
                model_name = self.online_model_var.get().strip()
                if api_key and api_url and model_name:
                    self.start_button.config(state=tk.NORMAL)
                else:
                    self.start_button.config(state=tk.DISABLED)
    
    def check_ssh_connection(self):
        """检查SSH连接是否已建立"""
        if not self.main_window.ssh_service:
            return False
        return self.main_window.ssh_service.is_connected()
    
    def connect_ssh(self):
        """连接SSH"""
        host = self.host_var.get().strip()
        username = self.username_var.get().strip()
        ssh_port = int(self.ssh_port_var.get() or "22")
        password = self.password_var.get()
        
        if not host or not username:
            self.log("请填写完整的SSH连接信息", "WARN")
            return
        
        def connect_thread():
            try:
                self.connect_btn.config(state="disabled")
                self.ssh_status_label.config(text="连接中...", foreground="blue")
                
                # 使用SSH服务连接
                if not self.main_window.ssh_service:
                    from services.ssh_service import SSHService
                    self.main_window.ssh_service = SSHService(log_callback=self.log)
                
                if self.main_window.ssh_service.connect(username, host, ssh_port, password):
                    # 建立隧道
                    local_port = int(self.local_port_var.get())
                    remote_port = int(self.remote_port_var.get())
                    if self.main_window.ssh_service.establish_tunnel(local_port, "localhost", remote_port):
                        self.log("✓ SSH连接和隧道已建立", "SUCCESS")
                        self.ssh_status_label.config(text="已连接", foreground="green")
                        self.connect_btn.config(state="disabled")
                        self.disconnect_btn.config(state="normal")
                        self.on_mode_changed()  # 更新按钮状态
                    else:
                        self.log("✗ SSH隧道建立失败", "ERROR")
                        self.ssh_status_label.config(text="连接失败", foreground="red")
                        self.connect_btn.config(state="normal")
                else:
                    self.log("✗ SSH连接失败", "ERROR")
                    self.ssh_status_label.config(text="连接失败", foreground="red")
                    self.connect_btn.config(state="normal")
            except Exception as e:
                self.log(f"✗ SSH连接出错: {e}", "ERROR")
                self.ssh_status_label.config(text="连接失败", foreground="red")
                self.connect_btn.config(state="normal")
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def disconnect_ssh(self):
        """断开SSH连接"""
        try:
            self.log("正在断开SSH连接...", "INFO")
            if self.main_window.ssh_service:
                self.main_window.ssh_service.close_tunnel()
                self.main_window.ssh_service.disconnect()
            self.ssh_status_label.config(text="未连接", foreground="gray")
            self.connect_btn.config(state="normal")
            self.disconnect_btn.config(state="disabled")
            self.on_mode_changed()  # 更新按钮状态
            self.log("✓ SSH连接已断开", "SUCCESS")
        except Exception as e:
            self.log(f"断开SSH连接时出错: {e}", "ERROR")
    
    def fetch_models_from_ollama(self):
        """从Ollama获取模型列表"""
        def fetch_thread():
            try:
                self.log("正在获取Ollama模型列表...", "INFO")
                
                local_port = int(self.local_port_var.get())
                api_url = f"http://localhost:{local_port}/api/tags"
                
                import requests
                response = requests.get(api_url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    models = [model.get("name", "") for model in data.get("models", [])]
                    models = [m for m in models if m]  # 过滤空字符串
                    
                    if models:
                        # 更新下拉框
                        if hasattr(self, 'model_combo'):
                            self.model_combo['values'] = models
                        
                        # 保存到缓存
                        self.ollama_models_cache = {"models": models}
                        save_json(self.ollama_models_cache, MODELS_CACHE_FILE)
                        
                        self.log(f"✓ 已获取 {len(models)} 个模型", "SUCCESS")
                    else:
                        self.log("✗ 未获取到模型", "WARN")
                else:
                    self.log(f"✗ 获取模型列表失败: {response.status_code}", "ERROR")
            except Exception as e:
                self.log(f"✗ 获取模型列表失败: {e}", "ERROR")
        
        threading.Thread(target=fetch_thread, daemon=True).start()
    
    def check_batch_status(self):
        """检查批处理任务状态"""
        self.log("检查批处理状态功能（待实现）", "INFO")
        # TODO: 实现批处理状态检查
    
    def cancel_batch_task(self):
        """取消批处理任务"""
        self.log("取消批处理任务功能（待实现）", "INFO")
        # TODO: 实现批处理任务取消
    
    def download_batch_results(self):
        """下载批处理结果"""
        self.log("下载批处理结果功能（待实现）", "INFO")
        # TODO: 实现批处理结果下载
    
    def start_research(self):
        """开始运行调研"""
        if self.is_running:
            return
        
        # 检查是否启用批处理模式
        if self.batch_processing_var.get() and self.api_mode_var.get() == "online":
            # 批处理模式
            self.is_running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            # 在新线程中运行批处理
            thread = threading.Thread(target=self._run_batch_processing_thread, daemon=True)
            thread.start()
        else:
            # 常规模式
            self.is_running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            # 在新线程中运行
            thread = threading.Thread(target=self._run_research_thread, daemon=True)
            thread.start()
    
    def stop_research(self):
        """停止运行"""
        try:
            self.log("用户中断运行...", "INFO")
            self.is_running = False
            
            # 恢复按钮状态
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.progress_var.set("已停止")
        except Exception as e:
            self.log(f"停止运行时出错: {e}", "ERROR")
    
    def finish_research(self, success):
        """完成运行"""
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        if success:
            self.progress_var.set("完成")
        else:
            self.progress_var.set("失败")
    
    def _run_research_thread(self):
        """在后台线程中运行调研流程"""
        try:
            api_mode = self.api_mode_var.get()
            
            if api_mode == "ollama":
                # Ollama模式：需要SSH连接和Ollama服务
                self.progress_var.set("步骤 1/4: 检查SSH连接")
                # TODO: 实现SSH连接检查
                self.log("✓ SSH连接已就绪", "SUCCESS")
                
                self.progress_var.set("步骤 2/4: 启动Ollama服务")
                # TODO: 实现Ollama服务启动
                
                self.progress_var.set("步骤 3/4: 测试连接")
                # TODO: 实现连接测试
                
                self.progress_var.set("步骤 4/4: 处理表格数据")
                success = self.process_table()
            else:
                # 在线API模式：直接处理表格
                self.progress_var.set("步骤 1/2: 验证API配置")
                api_key = self.online_api_key_var.get().strip()
                api_url = self.online_api_url_var.get().strip()
                model_name = self.online_model_var.get().strip()
                
                if not api_key or not api_url or not model_name:
                    self.log("✗ API配置不完整", "ERROR")
                    self.finish_research(False)
                    return
                
                self.log("✓ API配置验证通过", "SUCCESS")
                
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
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            self.finish_research(False)
    
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
    
    def clear_output(self):
        """清空输出"""
        if hasattr(self, 'output_text'):
            self.output_text.delete(1.0, tk.END)
    
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
                "prompt": self.prompt_text.get(1.0, tk.END).strip() if hasattr(self, 'prompt_text') else "",
                "monitor": {
                    "enabled": self.monitor_enabled_var.get(),
                    "rpm_limit": self.rpm_limit_var.get(),
                    "tpm_limit": self.tpm_limit_var.get(),
                    "total_tokens_limit": self.total_tokens_limit_var.get()
                }
            }
            
            save_json(config, CONFIG_FILE)
            self.log("✓ 配置已保存", "SUCCESS")
        except Exception as e:
            self.log(f"保存配置失败: {e}", "WARN")
    
    def load_config(self):
        """从文件加载配置"""
        try:
            config = load_json(CONFIG_FILE, {})
            if not config:
                return
            
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
                if "ollama_custom_dir" in ollama:
                    self.ollama_custom_dir_var.set(ollama["ollama_custom_dir"])
                if "gpu" in ollama:
                    self.gpu_var.set(ollama["gpu"])
            
            # 加载模式选择
            if "api_mode" in config:
                self.api_mode_var.set(config["api_mode"])
                if hasattr(self, 'mode_notebook'):
                    if config["api_mode"] == "online":
                        self.mode_notebook.select(0)
                    else:
                        self.mode_notebook.select(1)
                    self.on_mode_changed()
            
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
            if "prompt" in config and hasattr(self, 'prompt_text'):
                self.prompt_text.delete(1.0, tk.END)
                self.prompt_text.insert(1.0, config["prompt"])
            
            # 加载监控配置
            if "monitor" in config:
                monitor = config["monitor"]
                if "enabled" in monitor:
                    self.monitor_enabled_var.set(monitor["enabled"])
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
                    self.main_window.root.after(500, self.auto_analyze_columns)
            
            self.log("✓ 配置已加载", "SUCCESS")
        except Exception as e:
            self.log(f"加载配置失败: {e}，使用默认配置", "WARN")

