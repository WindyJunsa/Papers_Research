#!/usr/bin/env python3
"""
主入口文件：启动应用程序
"""

import tkinter as tk
import sys
import os

# 添加src目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow


def main():
    """主函数"""
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()

