#!/usr/bin/env python3
"""
更新服务：处理GitHub Release检查和更新下载
"""

import os
import time
import tempfile
import subprocess
import requests
from typing import Optional, Callable, Dict, Any

import sys
import os

# 添加父目录到路径以便导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import GITHUB_API_URL, CURRENT_VERSION
from utils.version_utils import compare_versions


class UpdateService:
    """更新服务类"""
    
    def __init__(self, log_callback: Optional[Callable] = None):
        """
        初始化更新服务
        
        Args:
            log_callback: 日志回调函数
        """
        self.log_callback = log_callback
        self.pending_update_file: Optional[str] = None
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """
        检查GitHub Release是否有新版本
        
        Returns:
            如果有更新，返回release数据字典；否则返回None
        """
        try:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PaperResearchTool"
            }
            response = requests.get(GITHUB_API_URL, headers=headers, timeout=10)
            response.raise_for_status()
            
            release_data = response.json()
            latest_version = release_data.get("tag_name", "").lstrip("v")
            
            has_update = compare_versions(CURRENT_VERSION, latest_version)
            
            if has_update:
                return release_data
            return None
            
        except requests.exceptions.RequestException as e:
            self.log(f"无法连接到GitHub检查更新：{e}", "ERROR")
            return None
        except Exception as e:
            self.log(f"检查更新时出错：{e}", "ERROR")
            return None
    
    def download_update(self, release_data: Dict[str, Any], save_path: Optional[str] = None) -> Optional[str]:
        """
        下载更新文件
        
        Args:
            release_data: GitHub Release数据
            save_path: 保存路径，如果为None则自动选择临时目录
        
        Returns:
            下载文件的路径，失败返回None
        """
        try:
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
                self.log("未找到可下载的更新文件（.exe或.zip）", "WARN")
                return None
            
            if save_path is None:
                temp_dir = tempfile.gettempdir()
                save_path = os.path.join(temp_dir, f"PaperResearchTool_update_{int(time.time())}.exe")
            
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            
            self.pending_update_file = save_path
            return save_path
            
        except Exception as e:
            self.log(f"下载更新文件时出错：{e}", "ERROR")
            return None
    
    def create_update_script(self, current_exe: str) -> Optional[str]:
        """
        创建自动更新脚本（批处理文件）
        
        Args:
            current_exe: 当前exe文件路径
        
        Returns:
            批处理脚本路径
        """
        if not self.pending_update_file or not os.path.exists(self.pending_update_file):
            return None
        
        try:
            temp_dir = tempfile.gettempdir()
            batch_file = os.path.join(temp_dir, f"PaperResearchTool_update_{int(time.time())}.bat")
            
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write('@echo off\n')
                f.write('chcp 65001 >nul\n')
                f.write('timeout /t 2 /nobreak >nul\n')
                f.write(f'if exist "{current_exe}" (\n')
                f.write(f'    del /f /q "{current_exe}"\n')
                f.write(')\n')
                f.write(f'if exist "{self.pending_update_file}" (\n')
                f.write(f'    move /y "{self.pending_update_file}" "{current_exe}"\n')
                f.write(f'    echo 更新完成！\n')
                f.write(')\n')
                f.write(f'del /f /q "%~f0"\n')
            
            return batch_file
        except Exception as e:
            self.log(f"创建自动更新脚本时出错：{e}", "ERROR")
            return None

