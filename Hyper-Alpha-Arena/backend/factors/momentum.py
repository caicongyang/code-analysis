"""
Momentum Factor Module - Price Momentum Calculation
"""
"""
动量因子模块 - 价格动量计算

实现基于价格变化的动量因子，用于识别具有上涨趋势的加密货币。
动量因子是量化投资中最经典的因子之一。

因子定义：
Momentum = (后半期最低价 - 前半期最低价) / 最大K线实体长度

计算逻辑：
1. 将历史数据分为前后两个时期
2. 分别找出两个时期的最低价
3. 计算价格变化相对于最大波动的比率
4. 使用tanh函数将结果标准化到0-1范围

因子含义：
- 正值：价格底部在抬升，说明有上涨动能
- 负值：价格底部在下降，说明有下跌动能
- 绝对值大：动量强度高

输出列：
- Momentum: 原始动量值
- Momentum Score: 标准化后的得分（0-1）

应用场景：
- 趋势跟踪策略
- 动量轮动策略
- 多因子组合中的动量维度
"""

from __future__ import annotations

from typing import Dict, Optional, List
import pandas as pd
import numpy as np

from models import Factor


def calculate_momentum_simple(df: pd.DataFrame) -> float:
    """
    Calculate momentum: (later-period low - earlier-period low) / longest candle
    计算动量：(后半期最低价 - 前半期最低价) / 最大K线实体长度

    Args:
        df: 包含OHLC数据的DataFrame，需要有Date, Open, High, Low, Close列

    Returns:
        float: 动量值，正值表示上涨动能，负值表示下跌动能

    计算步骤：
    1. 按日期排序（从旧到新）
    2. 计算前半期的最低价
    3. 计算后半期的最低价
    4. 计算整个周期中最大的K线实体长度
    5. 返回 (后半期低点 - 前半期低点) / 最大实体长度
    """
    if len(df) < 2:
        return 0.0
    
    # Convert date column to datetime for proper sorting if needed
    df_copy = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df_copy['Date']):
        df_copy['Date'] = pd.to_datetime(df_copy['Date'])
    
    # Sort by date (oldest first)
    df_sorted = df_copy.sort_values("Date", ascending=True)
    df_sorted = df_sorted.reset_index(drop=True)
    
    # Calculate the necessary values
    # Minimum price in first half of period
    half_idx = len(df_sorted) // 2
    first_half_low = df_sorted.iloc[:half_idx]["Low"].min()
    
    # Minimum price in second half of period
    second_half_low = df_sorted.iloc[half_idx:]["Low"].min()
    
    # Maximum daily body length (absolute |close - open|) in entire period
    max_daily_change = (df_sorted["Close"] - df_sorted["Open"]).abs().max()
    
    # Check for invalid data
    if pd.isna(first_half_low) or pd.isna(second_half_low) or pd.isna(max_daily_change):
        return 0.0
    
    first_half_low = float(first_half_low)
    second_half_low = float(second_half_low)
    max_daily_change = float(max_daily_change)
    
    if max_daily_change == 0:
        return 0.0
    
    return (second_half_low - first_half_low) / max_daily_change


def compute_momentum(history: Dict[str, pd.DataFrame], top_spot: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Calculate momentum factor using formula: (later-period low - earlier-period low) / longest candle
    
    Args:
        history: Historical price data
        top_spot: Optional spot data (unused)
    """
    rows: List[dict] = []
    
    for code, df in history.items():
        if df is None or df.empty or len(df) < 2:
            continue
        
        momentum = calculate_momentum_simple(df)
        score = (np.tanh(momentum) + 1) / 2

        rows.append({
            "Symbol": code, 
            "Momentum": momentum,
            "Momentum Score": score
        })
    
    # Sort by momentum factor from high to low
    df_result = pd.DataFrame(rows)
    if not df_result.empty:
        df_result = df_result.sort_values("Momentum", ascending=False)
    
    return df_result


MOMENTUM_FACTOR = Factor(
    id="momentum",
    name="Momentum",
    description="Momentum: (later-period low - earlier-period low) / longest candle, sorted descending",
    columns=[
        {"key": "Momentum", "label": "Momentum", "type": "number", "sortable": True},
        {"key": "Momentum Score", "label": "Momentum Score", "type": "score", "sortable": True},
    ],
    compute=lambda history, top_spot=None: compute_momentum(history, top_spot),
)

MODULE_FACTORS = [MOMENTUM_FACTOR]
