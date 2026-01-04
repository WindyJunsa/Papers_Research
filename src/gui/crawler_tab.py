#!/usr/bin/env python3
"""
论文爬虫标签页：ArXiv论文爬取功能
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
from typing import Optional, Callable


class CrawlerTab:
    """论文爬虫标签页类"""
    
    def __init__(
        self,
        parent: ttk.Frame,
        main_window,
        log_callback: Optional[Callable] = None
    ):
        """
        初始化论文爬虫标签页
        
        Args:
            parent: 父容器
            main_window: 主窗口实例
            log_callback: 日志回调函数
        """
        self.parent = parent
        self.main_window = main_window
        self.log_callback = log_callback
        self.chinese_font = main_window.chinese_font
        
        # 状态变量
        self.is_running = False
        
        # 创建界面
        self.create_widgets()
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def create_widgets(self):
        """创建GUI组件"""
        # 主框架：左侧配置 + 右侧日志
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # 左侧：配置区域
        self.create_config_area(main_frame)
        
        # 右侧：日志输出
        self.create_output_area(main_frame)
        
        # 底部：控制按钮
        self.create_control_buttons(main_frame)
    
    def create_config_area(self, parent):
        """创建配置区域"""
        config_frame = ttk.LabelFrame(parent, text="爬虫配置", padding="10")
        config_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        config_frame.columnconfigure(0, weight=1)
        
        # TODO: 从原代码迁移ArXiv爬虫配置界面
        label = tk.Label(config_frame, text="ArXiv爬虫配置（待实现）", font=(self.chinese_font, 12))
        label.pack(pady=50)
    
    def create_output_area(self, parent):
        """创建输出区域"""
        output_frame = ttk.LabelFrame(parent, text="爬取日志", padding="5")
        output_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        
        # 日志输出文本框
        self.output_text = scrolledtext.ScrolledText(
            output_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4"
        )
        self.output_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    def create_control_buttons(self, parent):
        """创建控制按钮"""
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=1, column=0, columnspan=2, pady=10)
        
        # 开始按钮
        self.start_button = tk.Button(
            button_frame,
            text="开始爬取",
            font=(self.chinese_font, 12, "bold"),
            bg="#27ae60",
            fg="white",
            padx=20,
            pady=5,
            command=self.start_crawler
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
            command=self.stop_crawler,
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
    
    def start_crawler(self):
        """开始爬取"""
        self.log("开始爬取功能（待实现）", "INFO")
        # TODO: 实现爬虫逻辑
    
    def stop_crawler(self):
        """停止爬取"""
        self.log("停止爬取功能（待实现）", "INFO")
        # TODO: 实现停止逻辑
    
    def clear_output(self):
        """清空输出"""
        if hasattr(self, 'output_text'):
            self.output_text.delete(1.0, tk.END)

