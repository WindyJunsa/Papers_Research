#!/usr/bin/env python3
"""
版本比较工具函数
"""


def compare_versions(current: str, latest: str) -> bool:
    """
    比较版本号，返回True表示latest版本更新
    
    Args:
        current: 当前版本号（如 "1.0.0"）
        latest: 最新版本号（如 "1.0.1"）
    
    Returns:
        True表示latest版本更新，False表示current版本更新或相同
    """
    try:
        current_parts = [int(x) for x in current.split('.')]
        latest_parts = [int(x) for x in latest.split('.')]
        
        # 补齐长度
        max_len = max(len(current_parts), len(latest_parts))
        current_parts.extend([0] * (max_len - len(current_parts)))
        latest_parts.extend([0] * (max_len - len(latest_parts)))
        
        # 逐位比较
        for i in range(max_len):
            if latest_parts[i] > current_parts[i]:
                return True
            elif latest_parts[i] < current_parts[i]:
                return False
        return False  # 版本相同
    except (ValueError, AttributeError):
        # 如果版本号格式不正确，使用字符串比较
        return latest > current

