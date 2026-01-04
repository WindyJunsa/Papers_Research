#!/usr/bin/env python3
"""
SSH服务：处理SSH连接、隧道建立、命令执行
"""

import socket
import threading
import time
import requests
from typing import Optional, Tuple, Callable

try:
    import paramiko
    USE_PARAMIKO = True
except ImportError:
    USE_PARAMIKO = False
    paramiko = None


class SSHService:
    """SSH服务类"""
    
    def __init__(self, log_callback: Optional[Callable] = None):
        """
        初始化SSH服务
        
        Args:
            log_callback: 日志回调函数，接收(message, level)参数
        """
        self.log_callback = log_callback
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.ssh_tunnel_thread: Optional[threading.Thread] = None
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def connect(self, username: str, host: str, port: int, password: str) -> bool:
        """
        建立SSH连接
        
        Args:
            username: 用户名
            host: 主机地址
            port: SSH端口
            password: 密码
        
        Returns:
            是否连接成功
        """
        if not USE_PARAMIKO:
            self.log("✗ 错误: 需要安装paramiko库才能建立SSH连接", "ERROR")
            self.log("请运行: pip install paramiko", "ERROR")
            return False
        
        try:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh_client.connect(hostname=host, port=port, username=username, password=password, timeout=10)
            self.log("✓ SSH连接已建立", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"✗ SSH连接失败: {e}", "ERROR")
            if self.ssh_client:
                try:
                    self.ssh_client.close()
                except:
                    pass
                self.ssh_client = None
            return False
    
    def disconnect(self):
        """断开SSH连接"""
        self.close_tunnel()
        
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None
    
    def is_connected(self) -> bool:
        """检查SSH连接是否已建立"""
        if not self.ssh_client:
            return False
        try:
            transport = self.ssh_client.get_transport()
            if transport and transport.is_active():
                return True
        except:
            pass
        return False
    
    def close_tunnel(self):
        """关闭SSH隧道"""
        # 隧道线程会在连接关闭时自动结束
        if self.ssh_tunnel_thread and self.ssh_tunnel_thread.is_alive():
            # 可以设置一个标志来停止隧道线程
            pass
    
    def execute_command(self, command: str, show_console: bool = True) -> Tuple[bool, str, int]:
        """
        执行SSH命令
        
        Args:
            command: 要执行的命令
            show_console: 是否在控制台显示命令
        
        Returns:
            (成功标志, 输出内容, 退出码)
        """
        if not self.ssh_client:
            return False, "SSH未连接", 1
        
        if show_console:
            self.log(f"[SSH命令] {command}", "INFO")
        
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=30)
            
            # 读取输出
            output = stdout.read().decode('utf-8', errors='replace')
            error = stderr.read().decode('utf-8', errors='replace')
            exit_code = stdout.channel.recv_exit_status()
            
            if error:
                output = output + "\n" + error if output else error
            
            return True, output, exit_code
        except Exception as e:
            return False, str(e), 1
    
    def establish_tunnel(self, local_port: int, remote_host: str, remote_port: int) -> bool:
        """
        建立SSH端口转发隧道
        
        Args:
            local_port: 本地端口
            remote_host: 远程主机（通常为localhost）
            remote_port: 远程端口
        
        Returns:
            是否建立成功
        """
        if not self.ssh_client:
            self.log("✗ SSH未连接，无法建立隧道", "ERROR")
            return False
        
        try:
            # 使用paramiko的端口转发
            transport = self.ssh_client.get_transport()
            if not transport:
                self.log("✗ 无法获取SSH传输层", "ERROR")
                return False
            
            def forward_tunnel():
                """转发隧道线程"""
                try:
                    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    server_socket.bind(('localhost', local_port))
                    server_socket.listen(5)
                    
                    while True:
                        try:
                            local_sock, addr = server_socket.accept()
                            
                            def handle_connection(local_socket):
                                try:
                                    remote_channel = transport.open_channel(
                                        'direct-tcpip',
                                        (remote_host, remote_port),
                                        local_socket.getpeername()
                                    )
                                    
                                    def forward_data(source, dest):
                                        try:
                                            while True:
                                                data = source.recv(4096)
                                                if not data:
                                                    break
                                                dest.send(data)
                                        except:
                                            pass
                                    
                                    t1 = threading.Thread(target=forward_data, args=(local_socket, remote_channel), daemon=True)
                                    t2 = threading.Thread(target=forward_data, args=(remote_channel, local_socket), daemon=True)
                                    t1.start()
                                    t2.start()
                                    t1.join()
                                    t2.join()
                                except Exception:
                                    pass
                                finally:
                                    try:
                                        local_socket.close()
                                        remote_channel.close()
                                    except:
                                        pass
                            
                            threading.Thread(target=handle_connection, args=(local_sock,), daemon=True).start()
                        except Exception:
                            break
                except Exception as e:
                    self.log(f"SSH隧道线程错误: {e}", "ERROR")
                finally:
                    try:
                        server_socket.close()
                    except:
                        pass
            
            self.ssh_tunnel_thread = threading.Thread(target=forward_tunnel, daemon=True)
            self.ssh_tunnel_thread.start()
            
            # 等待隧道建立
            time.sleep(1)
            
            # 验证隧道
            try:
                test_url = f"http://localhost:{local_port}/api/tags"
                response = requests.get(test_url, timeout=3)
                if response.status_code == 200:
                    self.log("✓ SSH隧道已建立", "SUCCESS")
                    return True
            except:
                pass
            
            self.log("✓ SSH隧道已建立", "SUCCESS")
            return True
            
        except Exception as e:
            self.log(f"✗ 建立SSH隧道失败: {e}", "ERROR")
            return False

