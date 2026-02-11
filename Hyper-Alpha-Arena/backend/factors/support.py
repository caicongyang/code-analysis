"""
Support Factor Module - Support Strength Calculation
"""
"""
支撑因子模块 - 支撑强度计算

实现基于K线形态的支撑因子，用于评估价格支撑的强度。
该因子结合了时间维度和价格波动维度来衡量支撑质量。

因子定义：
Support = (距最大K线天数 / 窗口大小) × 价格比率

核心概念：
1. 最大K线：指定窗口内实体最长的K线
2. 距离天数：当前日期距离最大K线的天数
3. 价格比率：基于前后两天低点变化的调整系数

因子逻辑：
- 最大K线越早出现（距今越远），说明近期没有剧烈波动，支撑更稳定
- 价格比率反映短期价格变动方向
- 两者结合可以识别在稳定区域形成支撑的标的

输出列：
- Support: 原始支撑因子值
- Support Score: 标准化得分（0-1，使用sigmoid函数）
- Days From Longest Candle: 距最大K线的天数

配置参数：
- DEFAULT_WINDOW_SIZE: 默认回看窗口大小（30天）

应用场景：
- 寻找底部支撑强劲的标的
- 震荡行情中的低吸策略
- 风险控制中的支撑位判断
"""

from __future__ import annotations

from typing import Dict, Optional, List
import pandas as pd
import numpy as np

from models import Factor


def calculate_days_from_longest_candle(df_window):
    """
    Days since candle with largest real body (vectorized)
    计算距离最大实体K线的天数（向量化实现）

    Args:
        df_window: 包含K线数据的DataFrame窗口

    Returns:
        int: 从最近一根K线往回数，到最大实体K线的天数

    计算逻辑：
    1. 计算每根K线的实体长度（相对于第一天收盘价的百分比）
    2. 找到实体最长的K线（如有相同则取最近的）
    3. 计算该K线距离最后一天的天数
    """
    if len(df_window) < 2:
        return 0
    
    # Calculate real body length relative to prior close
    first_close = df_window.iloc[0]['Close']
    body_lengths = (df_window.iloc[1:]['Close'] - df_window.iloc[1:]['Open']).abs() * 100 / first_close
    
    # Find index of maximum body (searching from end prefers recent when tied)
    max_idx_rev = body_lengths.iloc[::-1].idxmax()
    
    # Days counted from latest candle backward
    return len(df_window) - 1 - max_idx_rev + 1


def compute_support(history: Dict[str, pd.DataFrame], top_spot: Optional[pd.DataFrame] = None, window_size: int = 60) -> pd.DataFrame:
    """Calculate support factor using days from longest candle
    
    Args:
        history: Historical price data
        top_spot: Optional spot data (unused)
        window_size: Number of days to look back for analysis (default: 60)
    """
    rows: List[dict] = []
    
    for code, df in history.items():
        # Require at least window_size + 1 days for meaningful analysis (extra day for previous close)
        if df is None or df.empty or len(df) < window_size + 1:
            continue
            
        # Convert date column to datetime for proper sorting if needed
        df_copy = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df_copy['Date']):
            df_copy['Date'] = pd.to_datetime(df_copy['Date'])
        
        df_sorted = df_copy.sort_values("Date", ascending=True)
        
        # Convert DataFrame to list of candle dictionaries
        candles = []
        for _, row in df_sorted.iterrows():
            candles.append({
                'open': row['Open'],
                'close': row['Close'],
                'high': row['High'],
                'low': row['Low']
            })
        
        # Calculate days from longest candle with specified window
        # We need window_size + 1 days for proper previous close reference
        actual_window = min(window_size, len(df_sorted) - 1)
        
        # Get the extended window data (window_size + 1 days)
        df_extended_window = df_sorted.iloc[-(actual_window + 1):]
        
        days_from_longest = calculate_days_from_longest_candle(df_extended_window)
        
        # Support factor: days from longest candle (more distant longest candle = better support)
        # Normalize to 0-1 range, where farther from recent = higher score
        support_factor_base = (days_from_longest / (actual_window - 1)) if actual_window > 1 else 0
        
        # Get the window for price ratio calculation
        window = candles[-actual_window:]
        
        # For support factor, higher values when price declined from window start

        # Calculate price ratio: (Prev Open - Prev Close)/(Prev Low - Curr Low) scaled
        if len(window) >= 2:
            yesterday = window[-2]
            today = window[-1]
            yesterday_open = yesterday['open']
            yesterday_close = yesterday['close']
            yesterday_low = yesterday['low']
            today_low = today['low']
            
            denominator = yesterday_low - today_low
            if denominator != 0:
                price_ratio = (yesterday_open - yesterday_close) * 2 / denominator
            else:
                price_ratio = 1.0
        else:
            price_ratio = 1.0
        
        # Combine time factor with price movement; higher suggests stronger support
        support_factor = support_factor_base * price_ratio
        
        normalized = 1 / (1 + np.exp(-support_factor))

        rows.append({
            "Symbol": code, 
            "Support": support_factor,
            "Support Score": normalized,
            f"Days From Longest Candle_{window_size}": days_from_longest,
        })
    
    return pd.DataFrame(rows)


# Configuration
DEFAULT_WINDOW_SIZE = 30

def compute_support_with_default_window(history: Dict[str, pd.DataFrame], top_spot: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Wrapper function that uses the default window size"""
    result = compute_support(history, top_spot, DEFAULT_WINDOW_SIZE)
    
    # Rename the dynamic column to a fixed name for the factor definition
    dynamic_col = f"Days From Longest Candle_{DEFAULT_WINDOW_SIZE}"
    if dynamic_col in result.columns:
        result = result.rename(columns={dynamic_col: "Days From Longest Candle"})
    
    return result

SUPPORT_FACTOR = Factor(
    id="support",
    name="Support",
    description=f"Support strength based on distance from largest candle within {DEFAULT_WINDOW_SIZE} days; higher is better",
    columns=[
        {"key": "Support", "label": "Support", "type": "number", "sortable": True},
        {"key": "Support Score", "label": "Support Score", "type": "score", "sortable": True},
        {"key": "Days From Longest Candle", "label": f"{DEFAULT_WINDOW_SIZE} Days From Longest Candle", "type": "number", "sortable": True},
    ],
    compute=lambda history, top_spot=None: compute_support_with_default_window(history, top_spot),
)

MODULE_FACTORS = [SUPPORT_FACTOR]
