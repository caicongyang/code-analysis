"""
Market Flow Indicators API Routes

Provides aggregated market flow indicators:
- CVD (Cumulative Volume Delta)
- Taker Buy/Sell Volume
- OI (Open Interest) - absolute and delta
- Funding Rate
- Depth Ratio
- Order Imbalance
"""
"""
市场流量指标API路由

提供聚合的市场微观结构数据，用于前端图表展示和量化分析。
这些指标反映市场的买卖力量对比和参与者行为。

API端点：
- GET /api/market-flow/cvd: 获取累积成交量差值时间序列
- GET /api/market-flow/taker-volume: 获取主动买卖成交量
- GET /api/market-flow/oi: 获取持仓量变化
- GET /api/market-flow/funding: 获取资金费率历史
- GET /api/market-flow/depth: 获取订单簿深度比率
- GET /api/market-flow/indicators: 批量获取多个指标

支持的指标：
1. CVD（累积成交量差值）：买方主动成交-卖方主动成交
2. Taker Volume：主动买入和卖出的成交量
3. OI（持仓量）：市场未平仓合约总量及变化
4. Funding Rate（资金费率）：永续合约的资金费率
5. Depth Ratio（深度比率）：买卖盘深度对比
6. Order Imbalance（订单失衡）：订单簿的买卖失衡程度

时间周期支持：
1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d

数据用途：
- 前端流量图表展示
- 信号检测和触发条件
- 市场制度分类输入
- AI策略的市场上下文
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel

from database.connection import SessionLocal
from database.models import MarketTradesAggregated, MarketOrderbookSnapshots, MarketAssetMetrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-flow", tags=["market-flow"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Timeframe to milliseconds mapping
TIMEFRAME_MS = {
    "1m": 60 * 1000,
    "3m": 3 * 60 * 1000,
    "5m": 5 * 60 * 1000,
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "2h": 2 * 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "8h": 8 * 60 * 60 * 1000,
    "12h": 12 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


class IndicatorDataPoint(BaseModel):
    time: int  # Unix timestamp in seconds (for chart compatibility)
    value: Optional[float] = None


class TakerVolumeDataPoint(BaseModel):
    time: int
    buy: float
    sell: float


class MarketFlowResponse(BaseModel):
    symbol: str
    timeframe: str
    data_available_from: Optional[int] = None
    indicators: Dict[str, List[Any]]


def decimal_to_float(val) -> Optional[float]:
    """Convert Decimal to float, handling None"""
    if val is None:
        return None
    return float(val)


def floor_timestamp(ts_ms: int, interval_ms: int) -> int:
    """Floor timestamp to interval boundary"""
    return (ts_ms // interval_ms) * interval_ms


@router.get("/indicators", response_model=MarketFlowResponse)
async def get_market_flow_indicators(
    symbol: str = Query(..., description="Trading symbol, e.g., BTC"),
    timeframe: str = Query("1h", description="Aggregation timeframe"),
    start_time: Optional[int] = Query(None, description="Start timestamp in ms"),
    end_time: Optional[int] = Query(None, description="End timestamp in ms"),
    indicators: str = Query(
        "cvd,taker_volume,oi,oi_delta,funding,depth_ratio,order_imbalance",
        description="Comma-separated list of indicators"
    ),
    db: Session = Depends(get_db)
):
    """
    Get aggregated market flow indicators for charting.

    Available indicators:
    - cvd: Cumulative Volume Delta
    - taker_volume: Taker buy/sell volume (separate)
    - oi: Open Interest (absolute value)
    - oi_delta: Open Interest change
    - funding: Funding Rate
    - depth_ratio: Bid/Ask depth ratio
    - order_imbalance: Order book imbalance (-1 to 1)
    """
    # Validate timeframe
    if timeframe not in TIMEFRAME_MS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timeframe. Supported: {list(TIMEFRAME_MS.keys())}"
        )

    interval_ms = TIMEFRAME_MS[timeframe]

    # Default time range: last 7 days
    if end_time is None:
        end_time = int(datetime.utcnow().timestamp() * 1000)
    if start_time is None:
        start_time = end_time - (7 * 24 * 60 * 60 * 1000)

    # Parse requested indicators
    requested = set(ind.strip().lower() for ind in indicators.split(","))

    result = {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "data_available_from": None,
        "indicators": {}
    }

    try:
        # Get earliest data timestamp
        earliest = db.query(func.min(MarketTradesAggregated.timestamp)).filter(
            MarketTradesAggregated.symbol == symbol.upper()
        ).scalar()

        if earliest:
            result["data_available_from"] = earliest

        # Calculate indicators based on request
        if "cvd" in requested or "taker_volume" in requested:
            cvd_data, taker_data = _calculate_volume_indicators(
                db, symbol.upper(), start_time, end_time, interval_ms
            )
            if "cvd" in requested:
                result["indicators"]["cvd"] = cvd_data
            if "taker_volume" in requested:
                result["indicators"]["taker_volume"] = taker_data

        if "oi" in requested or "oi_delta" in requested:
            oi_data, oi_delta_data = _calculate_oi_indicators(
                db, symbol.upper(), start_time, end_time, interval_ms
            )
            if "oi" in requested:
                result["indicators"]["oi"] = oi_data
            if "oi_delta" in requested:
                result["indicators"]["oi_delta"] = oi_delta_data

        if "funding" in requested:
            result["indicators"]["funding"] = _calculate_funding_indicator(
                db, symbol.upper(), start_time, end_time, interval_ms
            )

        if "depth_ratio" in requested or "order_imbalance" in requested:
            depth_data, imbalance_data = _calculate_orderbook_indicators(
                db, symbol.upper(), start_time, end_time, interval_ms
            )
            if "depth_ratio" in requested:
                result["indicators"]["depth_ratio"] = depth_data
            if "order_imbalance" in requested:
                result["indicators"]["order_imbalance"] = imbalance_data

        return result

    except Exception as e:
        logger.error(f"Failed to calculate market flow indicators: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _calculate_volume_indicators(
    db: Session, symbol: str, start_time: int, end_time: int, interval_ms: int
) -> tuple:
    """
    Calculate CVD and Taker Volume indicators.

    CVD = Cumulative(Taker Buy Volume - Taker Sell Volume)
    """
    # Query aggregated trade data
    records = db.query(
        MarketTradesAggregated.timestamp,
        MarketTradesAggregated.taker_buy_volume,
        MarketTradesAggregated.taker_sell_volume
    ).filter(
        MarketTradesAggregated.symbol == symbol,
        MarketTradesAggregated.timestamp >= start_time,
        MarketTradesAggregated.timestamp <= end_time
    ).order_by(MarketTradesAggregated.timestamp).all()

    if not records:
        return [], []

    # Aggregate by timeframe
    buckets = {}
    for ts, buy_vol, sell_vol in records:
        bucket_ts = floor_timestamp(ts, interval_ms)
        if bucket_ts not in buckets:
            buckets[bucket_ts] = {"buy": Decimal("0"), "sell": Decimal("0")}
        buckets[bucket_ts]["buy"] += buy_vol or Decimal("0")
        buckets[bucket_ts]["sell"] += sell_vol or Decimal("0")

    # Sort by time and calculate CVD
    sorted_times = sorted(buckets.keys())
    cvd_data = []
    taker_data = []
    cumulative_delta = Decimal("0")

    for ts in sorted_times:
        bucket = buckets[ts]
        delta = bucket["buy"] - bucket["sell"]
        cumulative_delta += delta

        # Convert to seconds for chart (Lightweight Charts uses seconds)
        time_sec = ts // 1000

        cvd_data.append({"time": time_sec, "value": float(cumulative_delta)})
        taker_data.append({
            "time": time_sec,
            "buy": float(bucket["buy"]),
            "sell": float(bucket["sell"])
        })

    return cvd_data, taker_data


def _calculate_oi_indicators(
    db: Session, symbol: str, start_time: int, end_time: int, interval_ms: int
) -> tuple:
    """
    Calculate OI (Open Interest) indicators.

    OI: Absolute open interest value (last value in each bucket)
    OI Delta: Change from previous bucket
    """
    # Query asset metrics data
    records = db.query(
        MarketAssetMetrics.timestamp,
        MarketAssetMetrics.open_interest
    ).filter(
        MarketAssetMetrics.symbol == symbol,
        MarketAssetMetrics.timestamp >= start_time,
        MarketAssetMetrics.timestamp <= end_time
    ).order_by(MarketAssetMetrics.timestamp).all()

    if not records:
        return [], []

    # Aggregate by timeframe - take last value in each bucket
    buckets = {}
    for ts, oi in records:
        bucket_ts = floor_timestamp(ts, interval_ms)
        # Always overwrite to get the last value in the bucket
        buckets[bucket_ts] = oi

    # Sort by time and calculate delta
    sorted_times = sorted(buckets.keys())
    oi_data = []
    oi_delta_data = []
    prev_oi = None

    for ts in sorted_times:
        oi = buckets[ts]
        time_sec = ts // 1000

        oi_value = decimal_to_float(oi)
        oi_data.append({"time": time_sec, "value": oi_value})

        # Calculate delta
        if prev_oi is not None and oi is not None:
            delta = float(oi - prev_oi)
        else:
            delta = 0.0

        oi_delta_data.append({"time": time_sec, "value": delta})
        prev_oi = oi

    return oi_data, oi_delta_data


def _calculate_funding_indicator(
    db: Session, symbol: str, start_time: int, end_time: int, interval_ms: int
) -> list:
    """
    Calculate Funding Rate indicator.

    Takes the last funding rate value in each bucket.
    """
    records = db.query(
        MarketAssetMetrics.timestamp,
        MarketAssetMetrics.funding_rate
    ).filter(
        MarketAssetMetrics.symbol == symbol,
        MarketAssetMetrics.timestamp >= start_time,
        MarketAssetMetrics.timestamp <= end_time
    ).order_by(MarketAssetMetrics.timestamp).all()

    if not records:
        return []

    # Aggregate by timeframe - take last value
    buckets = {}
    for ts, funding in records:
        bucket_ts = floor_timestamp(ts, interval_ms)
        buckets[bucket_ts] = funding

    # Sort and format
    sorted_times = sorted(buckets.keys())
    funding_data = []

    for ts in sorted_times:
        funding = buckets[ts]
        time_sec = ts // 1000
        # Convert to percentage for display (e.g., 0.0001 -> 0.01%)
        funding_pct = decimal_to_float(funding) * 100 if funding else 0.0
        funding_data.append({"time": time_sec, "value": funding_pct})

    return funding_data


def _calculate_orderbook_indicators(
    db: Session, symbol: str, start_time: int, end_time: int, interval_ms: int
) -> tuple:
    """
    Calculate orderbook-based indicators.

    Depth Ratio: Bid Depth / Ask Depth (>1 = more buy support)
    Order Imbalance: (Bid - Ask) / (Bid + Ask), range -1 to 1
    """
    records = db.query(
        MarketOrderbookSnapshots.timestamp,
        MarketOrderbookSnapshots.bid_depth_5,
        MarketOrderbookSnapshots.ask_depth_5
    ).filter(
        MarketOrderbookSnapshots.symbol == symbol,
        MarketOrderbookSnapshots.timestamp >= start_time,
        MarketOrderbookSnapshots.timestamp <= end_time
    ).order_by(MarketOrderbookSnapshots.timestamp).all()

    if not records:
        return [], []

    # Aggregate by timeframe - take last value
    buckets = {}
    for ts, bid_depth, ask_depth in records:
        bucket_ts = floor_timestamp(ts, interval_ms)
        buckets[bucket_ts] = {"bid": bid_depth, "ask": ask_depth}

    # Sort and calculate
    sorted_times = sorted(buckets.keys())
    depth_ratio_data = []
    imbalance_data = []

    for ts in sorted_times:
        bucket = buckets[ts]
        bid = bucket["bid"] or Decimal("0")
        ask = bucket["ask"] or Decimal("0")
        time_sec = ts // 1000

        # Depth Ratio
        if ask > 0:
            ratio = float(bid / ask)
        else:
            ratio = 1.0
        depth_ratio_data.append({"time": time_sec, "value": ratio})

        # Order Imbalance: (bid - ask) / (bid + ask)
        total = bid + ask
        if total > 0:
            imbalance = float((bid - ask) / total)
        else:
            imbalance = 0.0
        imbalance_data.append({"time": time_sec, "value": imbalance})

    return depth_ratio_data, imbalance_data
