#!/usr/bin/env python3
"""
路径工具函数
"""

import os
import sys


def get_app_dir():
    """获取应用程序目录（支持打包后的exe）"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后的exe，使用exe所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境，使用脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))


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


def get_ollama_cmd():
    """获取Ollama命令路径"""
    app_dir = get_app_dir()
    # 检查当前目录
    ollama_path = os.path.join(app_dir, "ollama")
    if os.path.exists(ollama_path):
        return ollama_path
    # 检查系统PATH
    import shutil
    ollama_cmd = shutil.which("ollama")
    if ollama_cmd:
        return ollama_cmd
    return None


def get_full_model_name(base_name, size=""):
    """获取完整的模型名称"""
    if size:
        return f"{base_name}:{size}"
    return base_name

