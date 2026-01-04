#!/usr/bin/env python3
"""
Ollama服务：处理Ollama服务启动、模型管理、连接测试
"""

import os
import sys
import time
import requests
from typing import Optional, Callable, List, Dict, Tuple

# 添加父目录到路径以便导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.path_utils import get_full_model_name


class OllamaService:
    """Ollama服务类"""
    
    def __init__(self, ssh_service=None, log_callback: Optional[Callable] = None):
        """
        初始化Ollama服务
        
        Args:
            ssh_service: SSH服务实例（用于远程操作）
            log_callback: 日志回调函数
        """
        self.ssh_service = ssh_service
        self.log_callback = log_callback
        self.ollama_path: Optional[str] = None
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def find_ollama_path(
        self,
        username: str,
        custom_dir: str = ""
    ) -> Optional[str]:
        """
        查找Ollama安装路径
        
        Args:
            username: 服务器用户名
            custom_dir: 用户自定义目录
        
        Returns:
            Ollama路径，如果未找到返回None
        """
        if not self.ssh_service:
            return None
        
        # 优先使用用户自定义路径
        if custom_dir:
            custom_path = f"{custom_dir.rstrip('/')}/ollama/bin/ollama"
            success, output, _ = self.ssh_service.execute_command(
                f"test -x {custom_path} && {custom_path} --version 2>&1 || echo 'NOT_FOUND'",
                show_console=False
            )
            if success and "NOT_FOUND" not in output:
                self.ollama_path = custom_path
                return custom_path
        
        # 检测默认路径
        data_path = f"/data/{username}/ollama/bin/ollama"
        home_path = f"/home/{username}/ollama/bin/ollama"
        
        for path in [data_path, home_path]:
            success, output, _ = self.ssh_service.execute_command(
                f"test -x {path} && {path} --version 2>&1 || echo 'NOT_FOUND'",
                show_console=False
            )
            if success and "NOT_FOUND" not in output:
                self.ollama_path = path
                return path
        
        return None
    
    def start_service(
        self,
        local_port: int,
        gpu_devices: str = ""
    ) -> bool:
        """
        启动Ollama服务
        
        Args:
            local_port: 本地端口（通过SSH隧道访问）
            gpu_devices: GPU设备ID（如"0,1"）
        
        Returns:
            是否启动成功
        """
        if not self.ollama_path:
            self.log("✗ Ollama路径未设置", "ERROR")
            return False
        
        # 检查服务是否已运行
        try:
            test_url = f"http://localhost:{local_port}/api/tags"
            response = requests.get(test_url, timeout=3)
            if response.status_code == 200:
                self.log("✓ Ollama服务已在运行", "SUCCESS")
                return True
        except:
            pass
        
        # 启动服务
        if gpu_devices:
            serve_cmd = f"CUDA_VISIBLE_DEVICES={gpu_devices} {self.ollama_path} serve > /dev/null 2>&1 &"
        else:
            serve_cmd = f"{self.ollama_path} serve > /dev/null 2>&1 &"
        
        self.log(f"启动Ollama服务: {serve_cmd}", "INFO")
        success, output, code = self.ssh_service.execute_command(serve_cmd)
        
        # 等待服务启动
        self.log("等待服务启动...", "INFO")
        for i in range(10):
            time.sleep(2)
            try:
                test_url = f"http://localhost:{local_port}/api/tags"
                response = requests.get(test_url, timeout=2)
                if response.status_code == 200:
                    self.log("✓ Ollama服务已启动", "SUCCESS")
                    return True
            except:
                pass
            if i < 9:
                self.log(f"等待服务就绪... ({i+1}/10)", "INFO")
        
        self.log("⚠ Ollama服务启动可能失败", "WARN")
        return False
    
    def test_connection(
        self,
        local_port: int,
        model_name: str
    ) -> bool:
        """
        测试Ollama连接
        
        Args:
            local_port: 本地端口
            model_name: 模型名称
        
        Returns:
            是否连接成功
        """
        base_url = f"http://localhost:{local_port}"
        
        # 测试服务连接
        for i in range(5):
            try:
                test_url = f"{base_url}/api/tags"
                response = requests.get(test_url, timeout=5)
                if response.status_code == 200:
                    self.log("✓ Ollama服务器连接成功", "SUCCESS")
                    break
            except:
                if i < 4:
                    time.sleep(1)
                else:
                    self.log("✗ Ollama服务器连接失败", "ERROR")
                    return False
        
        # 测试模型
        try:
            generate_url = f"{base_url}/api/generate"
            test_payload = {
                "model": model_name,
                "prompt": "Hello",
                "stream": False
            }
            response = requests.post(generate_url, json=test_payload, timeout=30)
            if response.status_code == 200:
                self.log(f"✓ 模型 {model_name} 测试成功", "SUCCESS")
                return True
            else:
                self.log(f"✗ 模型测试失败: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"✗ 模型测试失败: {e}", "ERROR")
            return False
    
    def list_models(self) -> List[str]:
        """
        获取模型列表
        
        Returns:
            模型名称列表
        """
        if not self.ollama_path:
            return []
        
        success, output, code = self.ssh_service.execute_command(f"{self.ollama_path} list")
        if not success:
            return []
        
        models = []
        lines = output.strip().split('\n')
        if len(lines) > 1:
            for line in lines[1:]:  # 跳过表头
                parts = line.split()
                if parts:
                    models.append(parts[0])
        return models
    
    def check_model_exists(self, model_name: str) -> bool:
        """
        检查模型是否存在
        
        Args:
            model_name: 模型名称
        
        Returns:
            模型是否存在
        """
        models = self.list_models()
        for listed_model in models:
            if listed_model == model_name or listed_model.startswith(model_name + ":"):
                return True
        return False
    
    def pull_model(
        self,
        model_name: str,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """
        下载模型
        
        Args:
            model_name: 模型名称
            progress_callback: 进度回调函数，接收(progress_text)参数
        
        Returns:
            是否下载成功
        """
        if not self.ollama_path:
            self.log("✗ Ollama路径未设置", "ERROR")
            return False
        
        self.log(f"开始下载模型 {model_name}...", "INFO")
        cmd = f"{self.ollama_path} pull {model_name}"
        
        # 执行下载命令并实时显示进度
        if self.ssh_service and self.ssh_service.ssh_client:
            stdin, stdout, stderr = self.ssh_service.ssh_client.exec_command(cmd, timeout=None)
            
            # 实时读取输出
            while True:
                line = stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    if progress_callback:
                        progress_callback(line)
                    else:
                        self.log(line, "INFO")
            
            exit_code = stdout.channel.recv_exit_status()
            if exit_code == 0:
                self.log(f"✓ 模型 {model_name} 下载完成", "SUCCESS")
                return True
            else:
                self.log(f"✗ 模型下载失败，退出码: {exit_code}", "ERROR")
                return False
        
        return False
    
    def stop_model(self, model_name: str) -> bool:
        """
        停止运行中的模型
        
        Args:
            model_name: 模型名称
        
        Returns:
            是否停止成功
        """
        if not self.ollama_path:
            return False
        
        # 查找运行中的模型进程
        cmd = f"pgrep -f '{self.ollama_path} run' | head -1"
        success, output, _ = self.ssh_service.execute_command(cmd, show_console=False)
        
        if success and output.strip():
            # 停止进程
            pid = output.strip()
            self.ssh_service.execute_command(f"kill {pid}", show_console=False)
            time.sleep(1)
            self.log(f"✓ 已停止运行中的模型", "SUCCESS")
            return True
        
        return False
    
    def check_model_running(self, model_name: str) -> bool:
        """
        检查模型是否正在运行
        
        Args:
            model_name: 模型名称
        
        Returns:
            模型是否正在运行
        """
        if not self.ollama_path:
            return False
        
        cmd = f"pgrep -f '{self.ollama_path} run {model_name}'"
        success, output, _ = self.ssh_service.execute_command(cmd, show_console=False)
        return success and bool(output.strip())

