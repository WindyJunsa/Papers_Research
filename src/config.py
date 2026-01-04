#!/usr/bin/env python3
"""
配置模块：定义常量、版本信息、路径配置等
"""

import os
import sys

# ==================== 版本信息 ====================
CURRENT_VERSION = "0.1.0"
GITHUB_REPO_OWNER = "WindyJnsa"
GITHUB_REPO_NAME = "Papers_Research"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/releases/latest"

# ==================== 默认模型列表 ====================
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

# ==================== 批处理支持的模型 ====================
BATCH_SUPPORTED_MODELS = [
    "deepseek-ai/DeepSeek-V3",
    "deepseek-ai/DeepSeek-R1",
    "Qwen/QwQ-32B",
    "deepseek-ai/DeepSeek-V3.1-Terminus",
    "moonshotai/Kimi-K2-Instruct-0905",
    "MiniMaxAI/MiniMax-M2",
    "Qwen/Qwen3-235B-A22B-Thinking-2507"
]

# ==================== 路径配置 ====================
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

APP_DIR = get_app_dir()
USER_DATA_DIR = get_user_data_dir()

# ==================== 文件路径 ====================
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
MODELS_CACHE_FILE = os.path.join(APP_DIR, "models_cache.json")
ONLINE_MODELS_CACHE_FILE = os.path.join(APP_DIR, "online_models_cache.json")
LOCK_FILE = os.path.join(USER_DATA_DIR, ".lock")
UNLOCK_CODE = "unlock_hzq"

# ==================== IP白名单 ====================
ALLOWED_IPS = [
    "222.195.78.54",
    "211.86.155.236",
    "211.86.152.184",
    "10.8.0.2"
]

# ==================== 可选依赖检查 ====================
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    OpenAI = None

try:
    import paramiko
    USE_PARAMIKO = True
except ImportError:
    USE_PARAMIKO = False
    paramiko = None

