#!/usr/bin/env python3
"""
帮助标签页：使用指南、联系方式、更新检查
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import Optional, Callable

from config import CURRENT_VERSION


class HelpTab:
    """帮助标签页类"""
    
    def __init__(
        self,
        parent: ttk.Frame,
        main_window,
        log_callback: Optional[Callable] = None
    ):
        """
        初始化帮助标签页
        
        Args:
            parent: 父容器
            main_window: 主窗口实例
            log_callback: 日志回调函数
        """
        self.parent = parent
        self.main_window = main_window
        self.log_callback = log_callback
        self.chinese_font = main_window.chinese_font
        self.update_service = main_window.update_service
        
        # 创建界面
        self.create_widgets()
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = ttk.Frame(self.parent, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=3)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # 左侧：使用指南
        self.create_guide_section(main_frame)
        
        # 右侧：联系方式和更新
        self.create_info_section(main_frame)
    
    def create_guide_section(self, parent):
        """创建使用指南区域"""
        left_frame = ttk.Frame(parent, padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        left_frame.columnconfigure(0, weight=1)
        
        # 标题
        title = tk.Label(
            left_frame,
            text="使用指南",
            font=(self.chinese_font, 20, "bold"),
            fg="#2c3e50"
        )
        title.pack(pady=(0, 15))
        
        # 使用指南内容（可滚动）
        guide_frame = ttk.Frame(left_frame)
        guide_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        guide_frame.columnconfigure(0, weight=1)
        guide_frame.columnconfigure(1, weight=1)
        guide_frame.rowconfigure(0, weight=1)
        
        # 左列内容
        left_text = """一、论文调研模块使用步骤

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
        
        left_widget = scrolledtext.ScrolledText(
            guide_frame,
            wrap=tk.WORD,
            font=(self.chinese_font, 10),
            fg="#34495e",
            bg="#fafafa",
            relief=tk.FLAT,
            borderwidth=0,
            padx=5,
            pady=5
        )
        left_widget.insert(1.0, left_text.strip())
        left_widget.config(state=tk.DISABLED)
        left_widget.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 15))
        
        # 右列内容
        right_text = """二、论文爬虫模块使用步骤

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
        
        right_widget = scrolledtext.ScrolledText(
            guide_frame,
            wrap=tk.WORD,
            font=(self.chinese_font, 10),
            fg="#34495e",
            bg="#fafafa",
            relief=tk.FLAT,
            borderwidth=0,
            padx=5,
            pady=5
        )
        right_widget.insert(1.0, right_text.strip())
        right_widget.config(state=tk.DISABLED)
        right_widget.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(15, 0))
        
        guide_frame.rowconfigure(0, weight=1)
    
    def create_info_section(self, parent):
        """创建信息区域（联系方式、更新等）"""
        right_frame = ttk.Frame(parent, padding="10")
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(10, 0))
        right_frame.columnconfigure(0, weight=1)
        
        # 联系方式
        contact_title = tk.Label(
            right_frame,
            text="联系方式",
            font=(self.chinese_font, 18, "bold"),
            fg="#2c3e50"
        )
        contact_title.pack(pady=(0, 15))
        
        contact_text = """如有问题或建议，欢迎联系：

胡子谦 中国科学技术大学 信息科学与计算学院"""
        
        contact_label = tk.Label(
            right_frame,
            text=contact_text.strip(),
            font=(self.chinese_font, 12),
            fg="#34495e",
            justify=tk.LEFT,
            anchor="w"
        )
        contact_label.pack(pady=10)
        
        # 邮箱链接
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
        
        def copy_email(event=None):
            self.main_window.root.clipboard_clear()
            self.main_window.root.clipboard_append("huziqian@mail.ustc.edu.cn")
            tooltip = tk.Toplevel(self.main_window.root)
            tooltip.wm_overrideredirect(True)
            if event:
                tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            else:
                tooltip.wm_geometry("+100+100")
            label = tk.Label(tooltip, text="邮箱已复制到剪贴板", bg="yellow", font=(self.chinese_font, 10))
            label.pack()
            tooltip.after(2000, tooltip.destroy)
        
        email_link.bind("<Button-1>", copy_email)
        
        # 检查更新按钮
        update_frame = ttk.Frame(right_frame)
        update_frame.pack(pady=30)
        
        check_update_btn = tk.Button(
            update_frame,
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
        
        # 更新内容
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
• 加入模型用量监控"""
        
        update_label = tk.Label(
            right_frame,
            text=update_text.strip(),
            font=(self.chinese_font, 11),
            fg="#34495e",
            justify=tk.LEFT,
            anchor="w"
        )
        update_label.pack(pady=10, padx=10)
    
    def check_for_updates(self):
        """检查更新"""
        import threading
        
        def check_in_thread():
            release_data = self.update_service.check_for_updates()
            if release_data:
                latest_version = release_data.get("tag_name", "").lstrip("v")
                msg = f"发现新版本！\n\n当前版本: v{CURRENT_VERSION}\n最新版本: v{latest_version}\n\n是否下载更新？"
                result = messagebox.askyesno("发现新版本", msg, parent=self.main_window.root)
                if result:
                    # TODO: 实现下载更新逻辑
                    messagebox.showinfo("下载更新", "下载功能待实现", parent=self.main_window.root)
            else:
                messagebox.showinfo("检查更新", f"当前已是最新版本！\n\n当前版本: v{CURRENT_VERSION}", parent=self.main_window.root)
        
        threading.Thread(target=check_in_thread, daemon=True).start()

