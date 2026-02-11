"""
Market Regime Classification API routes
"""
"""
市场制度分类API路由

提供基于市场微观结构数据的市场状态分类功能，帮助识别
当前市场处于何种制度（趋势、震荡、突破等）。

API端点：
- GET /api/market-regime/classify/{symbol}: 获取单个币种的市场制度
- POST /api/market-regime/batch: 批量获取多个币种的市场制度
- GET /api/market-regime/configs: 获取分类配置列表
- PUT /api/market-regime/configs/{id}: 更新分类配置

市场制度类型：
1. breakout（突破）：价格突破关键位，伴随成交量放大
2. absorption（吸收）：大量订单被吸收，价格保持稳定
3. stop_hunt（扫损）：价格快速刺穿关键位后回归
4. trend（趋势）：明确的单边走势
5. range（震荡）：价格在区间内波动
6. reversal（反转）：趋势反转信号
7. neutral（中性）：无明显特征

分类指标：
- CVD比率：成交量差值与总成交量的比率
- OI变化：持仓量变化百分比
- Taker比率：主动买卖比率
- 价格ATR：价格波动率
- RSI：相对强弱指数

应用场景：
- 策略选择：不同制度使用不同策略
- 风险控制：高波动制度降低仓位
- 信号过滤：在特定制度下才执行信号
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from database.connection import SessionLocal
from database.models import MarketRegimeConfig
from services.market_regime_service import get_market_regime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-regime", tags=["market-regime"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic models
class RegimeIndicators(BaseModel):
    cvd_ratio: float  # CVD / Total Notional
    oi_delta: float   # OI change percentage
    taker_ratio: float
    price_atr: float
    rsi: float


class MarketRegimeResponse(BaseModel):
    symbol: str
    regime: str
    direction: str
    confidence: float
    reason: str
    indicators: RegimeIndicators


class BatchRegimeRequest(BaseModel):
    symbols: List[str]
    timeframe: str = "5m"
    config_id: Optional[int] = None
    timestamp_ms: Optional[int] = None  # For backtesting support


class BatchRegimeResponse(BaseModel):
    results: List[MarketRegimeResponse]
    errors: List[Dict[str, str]]


class RegimeConfigResponse(BaseModel):
    id: int
    name: str
    is_default: bool
    rolling_window: int
    breakout_cvd_z: float
    breakout_oi_z: float
    breakout_price_atr: float
    breakout_taker_high: float
    breakout_taker_low: float
    breakout_body_ratio: float
    absorption_cvd_z: float
    absorption_price_atr: float
    trap_cvd_z: float
    trap_oi_z: float
    exhaustion_cvd_z: float
    exhaustion_rsi_high: float
    exhaustion_rsi_low: float
    stop_hunt_range_atr: float
    stop_hunt_close_atr: float
    noise_cvd_z: float
    continuation_cvd_divisor: float


class RegimeConfigUpdateRequest(BaseModel):
    """Request model for updating regime config"""
    rolling_window: Optional[int] = None
    breakout_cvd_z: Optional[float] = None
    breakout_oi_z: Optional[float] = None
    breakout_price_atr: Optional[float] = None
    breakout_taker_high: Optional[float] = None
    breakout_taker_low: Optional[float] = None
    breakout_body_ratio: Optional[float] = None
    absorption_cvd_z: Optional[float] = None
    absorption_price_atr: Optional[float] = None
    trap_cvd_z: Optional[float] = None
    trap_oi_z: Optional[float] = None
    exhaustion_cvd_z: Optional[float] = None
    exhaustion_rsi_high: Optional[float] = None
    exhaustion_rsi_low: Optional[float] = None
    stop_hunt_range_atr: Optional[float] = None
    stop_hunt_close_atr: Optional[float] = None
    noise_cvd_z: Optional[float] = None
    continuation_cvd_divisor: Optional[float] = None


@router.get("/{symbol}", response_model=MarketRegimeResponse)
async def get_regime_for_symbol(
    symbol: str,
    timeframe: str = "5m",
    config_id: Optional[int] = None,
    timestamp_ms: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get market regime classification for a single symbol"""
    try:
        # Always use realtime mode (flow data aggregation) for consistent results
        # This ensures backtest/preview results match real-time trigger calculations
        result = get_market_regime(db, symbol, timeframe, config_id, timestamp_ms, use_realtime=True)
        return MarketRegimeResponse(
            symbol=symbol,
            regime=result["regime"],
            direction=result["direction"],
            confidence=result["confidence"],
            reason=result["reason"],
            indicators=RegimeIndicators(**result["indicators"])
        )
    except Exception as e:
        logger.error(f"Failed to get market regime for {symbol}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get market regime: {str(e)}"
        )


@router.post("/batch", response_model=BatchRegimeResponse)
async def get_regime_batch(
    request: BatchRegimeRequest,
    db: Session = Depends(get_db)
):
    """Get market regime classification for multiple symbols"""
    results = []
    errors = []

    for symbol in request.symbols:
        try:
            # Always use realtime mode (flow data aggregation) for consistent results
            result = get_market_regime(
                db, symbol, request.timeframe, request.config_id, request.timestamp_ms, use_realtime=True
            )
            results.append(MarketRegimeResponse(
                symbol=symbol,
                regime=result["regime"],
                direction=result["direction"],
                confidence=result["confidence"],
                reason=result["reason"],
                indicators=RegimeIndicators(**result["indicators"])
            ))
        except Exception as e:
            logger.warning(f"Failed to get regime for {symbol}: {e}")
            errors.append({"symbol": symbol, "error": str(e)})

    return BatchRegimeResponse(results=results, errors=errors)


@router.get("/configs/list", response_model=List[RegimeConfigResponse])
async def list_regime_configs(db: Session = Depends(get_db)):
    """List all market regime configurations"""
    try:
        configs = db.query(MarketRegimeConfig).all()
        return [
            RegimeConfigResponse(
                id=c.id,
                name=c.name,
                is_default=c.is_default or False,
                rolling_window=c.rolling_window or 48,
                breakout_cvd_z=c.breakout_cvd_z or 1.5,
                breakout_oi_z=c.breakout_oi_z or 1.0,
                breakout_price_atr=c.breakout_price_atr or 0.5,
                breakout_taker_high=c.breakout_taker_high or 1.8,
                breakout_taker_low=c.breakout_taker_low or 0.55,
                breakout_body_ratio=c.breakout_body_ratio or 0.4,
                absorption_cvd_z=c.absorption_cvd_z or 1.5,
                absorption_price_atr=c.absorption_price_atr or 0.3,
                trap_cvd_z=c.trap_cvd_z or 1.0,
                trap_oi_z=c.trap_oi_z or -1.0,
                exhaustion_cvd_z=c.exhaustion_cvd_z or 1.0,
                exhaustion_rsi_high=c.exhaustion_rsi_high or 70.0,
                exhaustion_rsi_low=c.exhaustion_rsi_low or 30.0,
                stop_hunt_range_atr=c.stop_hunt_range_atr or 1.0,
                stop_hunt_close_atr=c.stop_hunt_close_atr or 0.3,
                noise_cvd_z=c.noise_cvd_z or 0.5,
                continuation_cvd_divisor=c.continuation_cvd_divisor or 3.0
            )
            for c in configs
        ]
    except Exception as e:
        logger.error(f"Failed to list regime configs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list configs: {str(e)}"
        )


@router.put("/configs/{config_id}", response_model=RegimeConfigResponse)
async def update_regime_config(
    config_id: int,
    request: RegimeConfigUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update a market regime configuration"""
    try:
        config = db.query(MarketRegimeConfig).filter(MarketRegimeConfig.id == config_id).first()
        if not config:
            raise HTTPException(status_code=404, detail=f"Config {config_id} not found")

        # Update only provided fields
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(config, field, value)

        db.commit()
        db.refresh(config)

        return RegimeConfigResponse(
            id=config.id,
            name=config.name,
            is_default=config.is_default or False,
            rolling_window=config.rolling_window or 48,
            breakout_cvd_z=config.breakout_cvd_z or 1.5,
            breakout_oi_z=config.breakout_oi_z or 1.0,
            breakout_price_atr=config.breakout_price_atr or 0.5,
            breakout_taker_high=config.breakout_taker_high or 1.8,
            breakout_taker_low=config.breakout_taker_low or 0.55,
            breakout_body_ratio=config.breakout_body_ratio or 0.4,
            absorption_cvd_z=config.absorption_cvd_z or 1.5,
            absorption_price_atr=config.absorption_price_atr or 0.3,
            trap_cvd_z=config.trap_cvd_z or 1.0,
            trap_oi_z=config.trap_oi_z or -1.0,
            exhaustion_cvd_z=config.exhaustion_cvd_z or 1.0,
            exhaustion_rsi_high=config.exhaustion_rsi_high or 70.0,
            exhaustion_rsi_low=config.exhaustion_rsi_low or 30.0,
            stop_hunt_range_atr=config.stop_hunt_range_atr or 1.0,
            stop_hunt_close_atr=config.stop_hunt_close_atr or 0.3,
            noise_cvd_z=config.noise_cvd_z or 0.5,
            continuation_cvd_divisor=config.continuation_cvd_divisor or 3.0
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update regime config {config_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update config: {str(e)}"
        )
