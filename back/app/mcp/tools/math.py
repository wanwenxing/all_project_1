"""纯计算逻辑（无 LangChain / MCP 装饰器，供多端复用）。"""

from __future__ import annotations


def multiply(a: float, b: float) -> float:
    """计算两个数的乘积并返回结果。"""
    return a * b


def add(a: float, b: float) -> float:
    """计算两个数的和并返回结果。"""
    return a + b
