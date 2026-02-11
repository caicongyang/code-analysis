"""
Factors Package - Quantitative Factor Computation Framework
"""
"""
因子计算框架包

提供量化因子的动态加载、计算和管理功能。支持通过插件式架构
添加新的因子模块，实现因子的自动发现和注册。

核心功能：
1. 因子发现：自动扫描并加载factors目录下的所有因子模块
2. 因子计算：批量计算多个因子并合并结果
3. 因子选择：支持只计算指定的因子子集

架构设计：
- 插件式架构：每个因子模块独立，通过MODULE_FACTORS列表注册
- 动态加载：使用importlib动态导入因子模块
- 统一接口：所有因子使用Factor模型定义统一的计算接口

因子模块规范：
1. 模块需定义MODULE_FACTORS列表
2. 列表中包含Factor实例
3. Factor需实现compute方法

数据流程：
历史K线数据 → 各因子独立计算 → 按Symbol合并 → 输出因子表

应用场景：
- 加密货币多因子排名
- 量化策略标的筛选
- 因子研究和回测
"""

from __future__ import annotations

from __future__ import annotations

import importlib
import pkgutil
from typing import List, Dict, Optional
import pandas as pd

from models import Factor

__all__ = ["list_factors", "compute_all_factors", "compute_selected_factors"]


def _iter_factor_modules() -> List[str]:
    """
    Iterate all factor module names in this package
    遍历当前包中的所有因子模块名称

    Returns:
        List[str]: 因子模块的完整名称列表（如'factors.momentum'）
    """
    modules = []
    package = __name__  # 'factors'
    for _, name, ispkg in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        if name in {"__init__"}:
            continue
        modules.append(f"{package}.{name}")
    return modules


def list_factors() -> List[Factor]:
    """Dynamically import all factor modules and collect Factor instances from MODULE_FACTORS list."""
    factors: List[Factor] = []
    for mod_name in _iter_factor_modules():
        try:
            mod = importlib.import_module(mod_name)
            module_factors = getattr(mod, "MODULE_FACTORS", None)
            if isinstance(module_factors, list):
                for f in module_factors:
                    if isinstance(f, Factor):
                        factors.append(f)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to import factor module {mod_name}: {e}")
    return factors


def compute_all_factors(history: Dict[str, pd.DataFrame], top_spot: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Compute all registered factor DataFrames and outer-join them by 'Symbol'."""
    dfs: List[pd.DataFrame] = []
    for factor in list_factors():
        try:
            df = factor.compute(history, top_spot)
            if df is not None and not df.empty:
                if 'Symbol' not in df.columns:
                    continue
                dfs.append(df)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Factor {factor.id} failed: {e}")
    if not dfs:
        return pd.DataFrame()
    result = dfs[0]
    for df in dfs[1:]:
        result = result.merge(df, on='Symbol', how='outer')
    return result


def compute_selected_factors(history: Dict[str, pd.DataFrame], top_spot: Optional[pd.DataFrame] = None, selected_factor_ids: Optional[List[str]] = None) -> pd.DataFrame:
    """Compute only selected factor DataFrames and outer-join them by 'Symbol'."""
    if selected_factor_ids is None:
        return compute_all_factors(history, top_spot)
    
    dfs: List[pd.DataFrame] = []
    all_factors = list_factors()
    selected_factors = [f for f in all_factors if f.id in selected_factor_ids]
    
    for factor in selected_factors:
        try:
            df = factor.compute(history, top_spot)
            if df is not None and not df.empty:
                if 'Symbol' not in df.columns:
                    continue
                dfs.append(df)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Factor {factor.id} failed: {e}")
    
    if not dfs:
        return pd.DataFrame()
    
    result = dfs[0]
    for df in dfs[1:]:
        result = result.merge(df, on='Symbol', how='outer')
    return result
