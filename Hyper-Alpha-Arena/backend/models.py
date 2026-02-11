from __future__ import annotations

from typing import Dict, Optional, List, Callable, Any
import pandas as pd
from dataclasses import dataclass


@dataclass
class Factor:
    """Factor definition for ranking calculations"""
    """
    因子定义类，用于排名计算

    在量化交易中，因子是用来评估资产表现或预测市场趋势的指标。
    该类定义了一个标准化的因子结构，包含计算逻辑和元数据。

    属性说明：
    - id: 因子的唯一标识符，用于系统内部识别
    - name: 因子的显示名称，用于用户界面展示
    - description: 因子的详细描述，说明其计算逻辑和用途
    - columns: 因子计算结果的列定义，包含字段名、数据类型等元信息
    - compute: 因子计算函数，接收市场数据并返回计算结果

    使用场景：
    - 股票/加密货币排名系统
    - 多因子选股策略
    - 风险评估模型
    - 投资组合优化
    """
    id: str                     # 因子唯一标识符，如"momentum_factor"
    name: str                   # 因子显示名称，如"动量因子"
    description: str            # 因子描述，说明计算逻辑和应用场景
    columns: List[Dict[str, Any]]  # 输出列定义，包含字段名、类型、格式等
    compute: Callable[[Dict[str, pd.DataFrame], Optional[pd.DataFrame]], pd.DataFrame]  # 计算函数