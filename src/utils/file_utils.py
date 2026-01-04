#!/usr/bin/env python3
"""
文件操作工具函数
"""

import json
import os
from typing import Any, Dict, Optional


def load_json(file_path: str, default: Optional[Dict] = None) -> Dict:
    """
    加载JSON文件
    
    Args:
        file_path: JSON文件路径
        default: 如果文件不存在，返回的默认值
    
    Returns:
        解析后的字典，如果文件不存在且未提供default则返回空字典
    """
    if default is None:
        default = {}
    
    if not os.path.exists(file_path):
        return default
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"加载JSON文件失败 {file_path}: {e}")
        return default


def save_json(data: Dict, file_path: str) -> bool:
    """
    保存数据到JSON文件
    
    Args:
        data: 要保存的数据字典
        file_path: JSON文件路径
    
    Returns:
        是否保存成功
    """
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else '.', exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        print(f"保存JSON文件失败 {file_path}: {e}")
        return False

