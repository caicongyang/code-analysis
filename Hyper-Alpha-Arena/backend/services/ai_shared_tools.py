"""
AI Shared Tools - Common tools for AI Program and AI Prompt Generation services

Provides tools for:
- Signal pool configuration access
- Signal backtest execution
"""
"""
AI共享工具集

为AI编程服务和AI提示词生成服务提供公共的Function Calling工具。
这些工具允许AI助手查询系统配置和执行分析任务。

共享工具：
1. get_signal_pools: 获取信号池配置
   - 返回所有信号池的详细配置
   - 包含信号条件、逻辑关系、监控标的
   - 帮助AI理解交易触发机制

2. run_signal_backtest: 运行信号回测
   - 在历史数据上测试信号表现
   - 返回触发频率和样本触发点
   - 帮助验证信号参数是否合适

指标解释（SIGNAL_METRIC_EXPLANATIONS）：
为AI提供各种市场指标的上下文说明：
- cvd: 累积成交量差值
- oi_delta: 持仓量变化百分比
- oi: 持仓量变化（美元）
- taker_ratio: 主动买卖比率
- volume: 交易量
- funding_rate: 资金费率

设计目的：
- 代码复用：避免在多个AI服务中重复定义相同工具
- 一致性：确保工具行为在所有服务中保持一致
- 可维护性：集中管理工具定义和实现
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Signal metric explanations for AI context
SIGNAL_METRIC_EXPLANATIONS = {
    "cvd": {
        "name": "Cumulative Volume Delta",
        "description": "Taker Buy Volume - Taker Sell Volume in USD. Positive = buying pressure, Negative = selling pressure.",
        "typical_range": "±5M to ±50M for BTC",
        "interpretation": "CVD > 15M suggests strong buying; CVD < -15M suggests strong selling"
    },
    "oi_delta": {
        "name": "Open Interest Change %",
        "description": "Percentage change in open interest. Shows new positions entering or exiting.",
        "typical_range": "±0.5% to ±3%",
        "interpretation": "> 1% with price up = new longs; > 1% with price down = new shorts"
    },
    "oi": {
        "name": "Open Interest Change (USD)",
        "description": "Absolute change in open interest in USD.",
        "typical_range": "±10M to ±100M for BTC",
        "interpretation": "Rising OI = new positions; Falling OI = positions closing"
    },
    "taker_ratio": {
        "name": "Taker Buy/Sell Ratio",
        "description": "Ratio of taker buy volume to taker sell volume.",
        "typical_range": "0.3 to 3.0",
        "interpretation": "> 2.0 = aggressive buying; < 0.5 = aggressive selling"
    },
    "volume": {
        "name": "Trading Volume",
        "description": "Total trading volume in USD for the period.",
        "typical_range": "> 10M to > 50M for significance",
        "interpretation": "High volume confirms price moves; low volume suggests weak moves"
    },
    "funding_rate": {
        "name": "Funding Rate",
        "description": "Perpetual funding rate percentage.",
        "typical_range": "-0.05% to +0.05%",
        "interpretation": "> 0.01% = longs pay shorts (bullish sentiment); < -0.01% = shorts pay longs"
    }
}


# Tool definitions in OpenAI format (shared between services)
SHARED_SIGNAL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_signal_pools",
            "description": "Get all configured signal pools and their signal conditions. Returns pool names, logic (AND/OR), monitored symbols, and detailed signal definitions with metric explanations. Use this to understand what triggers the AI Trader.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_signal_backtest",
            "description": "Run a backtest on a signal pool to check trigger frequency and see sample triggers. Returns trigger count, average frequency, and recent trigger examples. Use this to verify if signal thresholds are appropriate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {
                        "type": "integer",
                        "description": "Signal pool ID to backtest"
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Trading symbol to backtest (e.g., 'BTC')",
                        "default": "BTC"
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Lookback hours for backtest (default: 24, max: 168)",
                        "default": 24
                    }
                },
                "required": ["pool_id"]
            }
        }
    }
]


def execute_get_signal_pools(db) -> str:
    """
    Execute get_signal_pools tool - returns all signal pools with explanations.

    Args:
        db: SQLAlchemy database session

    Returns:
        JSON string with signal pools and metric explanations
    """
    from sqlalchemy import text

    try:
        # Get all signal definitions
        signals_result = db.execute(text("""
            SELECT id, signal_name, description, trigger_condition, enabled
            FROM signal_definitions ORDER BY id
        """))

        signals_map = {}
        for row in signals_result:
            trigger_condition = row[3]
            if isinstance(trigger_condition, str):
                trigger_condition = json.loads(trigger_condition)
            signals_map[row[0]] = {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "condition": trigger_condition,
                "enabled": row[4]
            }

        # Get all signal pools
        pools_result = db.execute(text("""
            SELECT id, pool_name, signal_ids, symbols, enabled, logic
            FROM signal_pools ORDER BY id
        """))

        pools = []
        for row in pools_result:
            signal_ids = row[2]
            if isinstance(signal_ids, str):
                signal_ids = json.loads(signal_ids)
            symbols = row[3]
            if isinstance(symbols, str):
                symbols = json.loads(symbols)

            # Get signal details for this pool
            pool_signals = []
            for sig_id in (signal_ids or []):
                if sig_id in signals_map:
                    sig = signals_map[sig_id]
                    cond = sig["condition"]
                    metric = cond.get("metric", "unknown")
                    pool_signals.append({
                        "id": sig_id,
                        "name": sig["name"],
                        "description": sig["description"],
                        "metric": metric,
                        "operator": cond.get("operator", ""),
                        "threshold": cond.get("threshold", ""),
                        "time_window": cond.get("time_window", "5m"),
                        "metric_explanation": SIGNAL_METRIC_EXPLANATIONS.get(metric, {})
                    })

            pools.append({
                "id": row[0],
                "name": row[1],
                "logic": row[5] or "OR",
                "symbols": symbols or [],
                "enabled": row[4],
                "signals": pool_signals
            })

        result = {
            "total_pools": len(pools),
            "pools": pools,
            "note": "Use run_signal_backtest tool to check trigger frequency for a specific pool."
        }

        if not pools:
            result["suggestion"] = "No signal pools configured. Consider creating a signal pool to trigger AI decisions based on market conditions."

        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[get_signal_pools] Error: {e}")
        return json.dumps({"error": str(e)})


def execute_run_signal_backtest(db, pool_id: int, symbol: str = "BTC", hours: int = 24) -> str:
    """
    Execute run_signal_backtest tool - runs backtest and returns trigger statistics.

    Args:
        db: SQLAlchemy database session
        pool_id: Signal pool ID to backtest
        symbol: Trading symbol (default: BTC)
        hours: Lookback hours (default: 24, max: 168)

    Returns:
        JSON string with backtest results
    """
    from services.signal_backtest_service import signal_backtest_service

    try:
        # Limit hours to reasonable range
        hours = min(max(hours, 1), 168)  # 1 hour to 7 days

        # Calculate timestamp range
        now = datetime.now(timezone.utc)
        end_ts = int(now.timestamp() * 1000)
        start_ts = int((now - timedelta(hours=hours)).timestamp() * 1000)

        logger.info(f"[run_signal_backtest] pool_id={pool_id}, symbol={symbol}, hours={hours}")

        # Run backtest
        backtest_result = signal_backtest_service.backtest_pool(
            db, pool_id, symbol, start_ts, end_ts
        )

        if "error" in backtest_result:
            return json.dumps({"error": backtest_result["error"]})

        # Extract key statistics
        triggers = backtest_result.get("triggers", [])
        trigger_count = len(triggers)

        # Calculate frequency
        if trigger_count > 0:
            avg_per_hour = trigger_count / hours
            if avg_per_hour >= 1:
                frequency_desc = f"{avg_per_hour:.1f} triggers per hour"
            else:
                hours_per_trigger = hours / trigger_count
                frequency_desc = f"1 trigger every {hours_per_trigger:.1f} hours"
        else:
            frequency_desc = "No triggers in this period"

        # Get recent trigger samples (last 5)
        recent_triggers = []
        for t in triggers[-5:]:
            trigger_time = datetime.fromtimestamp(t["timestamp"] / 1000, tz=timezone.utc)
            recent_triggers.append({
                "time": trigger_time.strftime("%Y-%m-%d %H:%M UTC"),
                "signals": [s.get("signal_name", "Unknown") for s in t.get("triggered_signals", [])]
            })

        result = {
            "pool_id": pool_id,
            "pool_name": backtest_result.get("pool_name", "Unknown"),
            "symbol": symbol,
            "backtest_period": f"{hours} hours",
            "trigger_count": trigger_count,
            "frequency": frequency_desc,
            "recent_triggers": recent_triggers,
        }

        # Add recommendations based on frequency
        if trigger_count == 0:
            result["recommendation"] = "No triggers found. Consider lowering thresholds or extending the backtest period."
        elif avg_per_hour > 10:
            result["recommendation"] = "Very high trigger frequency. Consider raising thresholds to reduce noise."
        elif avg_per_hour > 2:
            result["recommendation"] = "High trigger frequency. May lead to overtrading."
        elif avg_per_hour < 0.1:
            result["recommendation"] = "Low trigger frequency. Thresholds may be too strict."
        else:
            result["recommendation"] = "Trigger frequency looks reasonable."

        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"[run_signal_backtest] Error: {e}")
        return json.dumps({"error": str(e)})


