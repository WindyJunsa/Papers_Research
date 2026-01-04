#!/usr/bin/env python3
"""
模型管理标签页：Ollama模型列表、下载、删除
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Optional, Callable, List


class ModelManagementTab:
    """模型管理标签页类"""
    
    def __init__(
        self,
        parent: ttk.Frame,
        main_window,
        log_callback: Optional[Callable] = None
    ):
        """
        初始化模型管理标签页
        
        Args:
            parent: 父容器
            main_window: 主窗口实例
            log_callback: 日志回调函数
        """
        self.parent = parent
        self.main_window = main_window
        self.log_callback = log_callback
        self.chinese_font = main_window.chinese_font
        
        # 创建界面
        self.create_widgets()
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def create_widgets(self):
        """创建GUI组件"""
        # 主框架：左侧模型列表 + 右侧操作和日志
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # 左侧：模型列表
        self.create_model_list(main_frame)
        
        # 右侧：操作和日志
        self.create_operations_area(main_frame)
    
    def create_model_list(self, parent):
        """创建模型列表"""
        list_frame = ttk.LabelFrame(parent, text="已安装模型", padding="10")
        list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 模型列表Treeview
        columns = ("模型名称", "大小", "更新时间")
        self.model_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=20)
        
        for col in columns:
            self.model_tree.heading(col, text=col)
            self.model_tree.column(col, width=150)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.model_tree.yview)
        self.model_tree.configure(yscrollcommand=scrollbar.set)
        
        self.model_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        list_frame.rowconfigure(0, weight=1)
    
    def create_operations_area(self, parent):
        """创建操作区域"""
        ops_frame = ttk.Frame(parent)
        ops_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        ops_frame.columnconfigure(0, weight=1)
        ops_frame.rowconfigure(1, weight=1)
        
        # 操作按钮区域
        button_frame = ttk.LabelFrame(ops_frame, text="操作", padding="10")
        button_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        button_frame.columnconfigure(0, weight=1)
        
        # 下载模型
        download_frame = ttk.Frame(button_frame)
        download_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        download_frame.columnconfigure(1, weight=1)
        
        tk.Label(download_frame, text="模型名称:", font=(self.chinese_font, 10)).grid(row=0, column=0, padx=5)
        self.model_name_entry = ttk.Entry(download_frame, font=(self.chinese_font, 10))
        self.model_name_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        
        self.download_button = tk.Button(
            download_frame,
            text="下载",
            font=(self.chinese_font, 10),
            bg="#3498db",
            fg="white",
            padx=15,
            pady=5,
            command=self.download_model
        )
        self.download_button.grid(row=0, column=2, padx=5)
        
        # 删除模型
        self.delete_button = tk.Button(
            button_frame,
            text="删除选中模型",
            font=(self.chinese_font, 10),
            bg="#e74c3c",
            fg="white",
            padx=15,
            pady=5,
            command=self.delete_model
        )
        self.delete_button.grid(row=1, column=0, pady=5)
        
        # 刷新列表
        self.refresh_button = tk.Button(
            button_frame,
            text="刷新列表",
            font=(self.chinese_font, 10),
            padx=15,
            pady=5,
            command=self.refresh_model_list
        )
        self.refresh_button.grid(row=2, column=0, pady=5)
        
        # 日志输出
        log_frame = ttk.LabelFrame(ops_frame, text="操作日志", padding="5")
        log_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 9),
            height=15,
            bg="#1e1e1e",
            fg="#d4d4d4"
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    def download_model(self):
        """下载模型"""
        model_name = self.model_name_entry.get().strip()
        if not model_name:
            self.log("请输入模型名称", "WARN")
            return
        
        self.log(f"开始下载模型 {model_name}（待实现）", "INFO")
        # TODO: 实现模型下载逻辑
    
    def delete_model(self):
        """删除模型"""
        selected = self.model_tree.selection()
        if not selected:
            self.log("请先选择要删除的模型", "WARN")
            return
        
        self.log("删除模型功能（待实现）", "INFO")
        # TODO: 实现模型删除逻辑
    
    def refresh_model_list(self):
        """刷新模型列表"""
        self.log("刷新模型列表（待实现）", "INFO")
        # TODO: 实现模型列表刷新逻辑

