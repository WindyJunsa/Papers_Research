#!/usr/bin/env python3
"""
主窗口：管理整个应用程序的GUI界面
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable

# 添加父目录到路径以便导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CURRENT_VERSION, CONFIG_FILE, MODELS_CACHE_FILE
from utils.file_utils import load_json, save_json
from services.ssh_service import SSHService
from services.ollama_service import OllamaService
from services.api_service import APIService
from services.update_service import UpdateService


class MainWindow:
    """主窗口类"""
    
    def __init__(self, root: tk.Tk):
        """
        初始化主窗口
        
        Args:
            root: Tkinter根窗口
        """
        self.root = root
        self.root.title(f"论文调研工具 v{CURRENT_VERSION}")
        self.root.geometry("1400x800")
        self.root.minsize(1200, 700)
        self.root.state('zoomed')  # Windows上最大化窗口
        
        # 配置中文字体
        self.chinese_font = self._setup_chinese_font()
        
        # 配置ttk样式
        self._setup_ttk_styles()
        
        # 初始化服务
        self.ssh_service: Optional[SSHService] = None
        self.ollama_service: Optional[OllamaService] = None
        self.api_service = APIService(log_callback=self.log)
        self.update_service = UpdateService(
            log_callback=self.log,
            root_window=self.root,
            current_version=CURRENT_VERSION,
            repo_owner="WindyJunsa",
            repo_name="Papers_Research"
        )
        
        # 状态变量
        self.is_running = False
        self.is_locked = False
        
        # 创建GUI组件
        self.create_widgets()
        
        # 加载配置
        self.load_config()
        
        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def _setup_chinese_font(self) -> str:
        """设置中文字体"""
        font = "Microsoft YaHei"
        try:
            import tkinter.font as tkfont
            available_fonts = tkfont.families()
            if font not in available_fonts:
                for font_name in ["SimHei", "SimSun", "KaiTi"]:
                    if font_name in available_fonts:
                        font = font_name
                        break
        except:
            font = "Arial"
        return font
    
    def _setup_ttk_styles(self):
        """配置ttk样式"""
        style = ttk.Style()
        style.configure("TCombobox", anchor="center")
        style.configure("Treeview", anchor="center")
        style.configure("Treeview.Heading", anchor="center")
    
    def create_widgets(self):
        """创建GUI组件"""
        # 创建Notebook（标签页容器）
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # 创建各个标签页
        from .research_tab import ResearchTab
        from .crawler_tab import CrawlerTab
        from .model_management_tab import ModelManagementTab
        from .help_tab import HelpTab
        
        # 论文调研标签页
        research_tab = ttk.Frame(notebook)
        notebook.add(research_tab, text="论文调研")
        self.research_tab = ResearchTab(research_tab, self, log_callback=self.log)
        
        # 论文爬虫标签页
        crawler_tab = ttk.Frame(notebook)
        notebook.add(crawler_tab, text="论文爬虫")
        self.crawler_tab = CrawlerTab(crawler_tab, self, log_callback=self.log)
        
        # 模型管理标签页
        model_mgmt_tab = ttk.Frame(notebook)
        notebook.add(model_mgmt_tab, text="模型管理")
        self.model_mgmt_tab = ModelManagementTab(model_mgmt_tab, self, log_callback=self.log)
        
        # 帮助标签页
        help_tab = ttk.Frame(notebook)
        notebook.add(help_tab, text="帮助")
        self.help_tab = HelpTab(help_tab, self, log_callback=self.log)
    
    def log(self, message: str, level: str = "INFO"):
        """
        记录日志（占位方法，需要在实际GUI组件中实现）
        
        Args:
            message: 日志消息
            level: 日志级别
        """
        print(f"[{level}] {message}")
    
    def load_config(self):
        """加载配置"""
        config = load_json(CONFIG_FILE)
        # TODO: 加载配置到各个组件
    
    def save_config(self):
        """保存配置"""
        config = {}
        # TODO: 从各个组件收集配置
        save_json(config, CONFIG_FILE)
    
    def on_closing(self):
        """关闭窗口时的处理"""
        # 保存配置（由各个标签页自己处理）
        if hasattr(self, 'research_tab') and hasattr(self.research_tab, 'save_config'):
            self.research_tab.save_config()
        
        # 断开服务
        if self.ssh_service:
            try:
                self.ssh_service.close_tunnel()
                self.ssh_service.disconnect()
            except:
                pass
        
        # 销毁窗口
        self.root.destroy()


def main():
    """主函数"""
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()

