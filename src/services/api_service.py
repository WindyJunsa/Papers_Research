#!/usr/bin/env python3
"""
API服务：处理在线API和Ollama API调用
"""

import json
import time
import requests
from typing import Dict, Optional, Callable, Any


class APIService:
    """API服务类"""
    
    def __init__(self, log_callback: Optional[Callable] = None):
        """
        初始化API服务
        
        Args:
            log_callback: 日志回调函数
        """
        self.log_callback = log_callback
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def fetch_online_models(self, provider: str, api_key: str, api_url: str) -> list:
        """
        获取在线模型列表
        
        Args:
            provider: API提供商（siliconflow/custom）
            api_key: API密钥
            api_url: API地址
        
        Returns:
            模型名称列表
        """
        try:
            if provider == "siliconflow":
                # 硅基流动：从模型列表API获取
                models_url = "https://api.siliconflow.cn/v1/models"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                response = requests.get(models_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    models = [model.get("id", "") for model in data.get("data", [])]
                    return [m for m in models if m]  # 过滤空字符串
                else:
                    self.log(f"获取模型列表失败: {response.status_code}", "ERROR")
                    return []
            else:
                # 自定义API：尝试从API地址推断或返回空列表
                self.log("自定义API暂不支持自动获取模型列表", "WARN")
                return []
        except Exception as e:
            self.log(f"获取模型列表时出错: {e}", "ERROR")
            return []
    
    def call_online_api(
        self,
        api_url: str,
        api_key: str,
        model_name: str,
        prompt: str,
        provider: str = "siliconflow",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        top_p: float = 0.7,
        enable_thinking: bool = False,
        thinking_budget: int = 4096
    ) -> Dict[str, Any]:
        """
        调用在线API
        
        Returns:
            包含response和usage的字典
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        if provider == "siliconflow":
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "max_tokens": max_tokens,
                "enable_thinking": enable_thinking,
                "thinking_budget": thinking_budget,
                "min_p": 0.05,
                "stop": None,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": 50,
                "frequency_penalty": 0.5,
                "n": 1,
                "response_format": {"type": "json_object"}
            }
        else:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": top_p
            }
            if enable_thinking and thinking_budget:
                payload["thinking_budget"] = thinking_budget
        
        response = requests.post(api_url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        return response.json()
    
    def call_ollama_api(
        self,
        api_url: str,
        model_name: str,
        prompt: str
    ) -> Dict[str, Any]:
        """
        调用Ollama API
        
        Returns:
            Ollama API响应字典
        """
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False
        }
        
        response = requests.post(api_url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()
    
    def extract_tokens(self, response_data: Dict[str, Any], api_mode: str = "online") -> int:
        """
        从API响应中提取token使用量
        
        Args:
            response_data: API响应数据
            api_mode: API模式（"online"或"ollama"）
        
        Returns:
            token使用量
        """
        if api_mode == "online":
            if "usage" in response_data and "total_tokens" in response_data["usage"]:
                return response_data["usage"]["total_tokens"]
        else:  # ollama
            if "usage" in response_data and "total_tokens" in response_data["usage"]:
                return response_data["usage"]["total_tokens"]
            elif "prompt_eval_count" in response_data and "eval_count" in response_data:
                return response_data.get("prompt_eval_count", 0) + response_data.get("eval_count", 0)
        return 0
    
    def extract_response_text(self, response_data: Dict[str, Any], api_mode: str = "online") -> str:
        """
        从API响应中提取文本内容
        
        Args:
            response_data: API响应数据
            api_mode: API模式
        
        Returns:
            响应文本
        """
        if api_mode == "online":
            if "choices" in response_data and len(response_data["choices"]) > 0:
                return response_data["choices"][0]["message"]["content"].strip()
        else:  # ollama
            return response_data.get("response", "").strip()
        return ""
    
    def parse_json_response(self, text: str) -> Optional[Dict]:
        """
        解析JSON响应，处理各种格式问题
        
        Args:
            text: 响应文本
        
        Returns:
            解析后的JSON字典，失败返回None
        """
        # 清理响应文本，提取JSON部分
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        
        if not text:
            return None
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试修复常见的转义问题
            try:
                import re
                start_idx = text.find('{')
                end_idx = text.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = text[start_idx:end_idx+1]
                    return json.loads(json_str)
            except:
                pass
        return None

