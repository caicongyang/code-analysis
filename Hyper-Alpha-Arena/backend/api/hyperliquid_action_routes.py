"""
Hyperliquid Exchange Actions API Routes
"""
"""
Hyperliquid交易所操作记录API路由

提供Hyperliquid交易所操作记录的查询和统计接口，用于审计、
监控和分析交易执行情况。

API端点：
- GET /api/hyperliquid/actions/: 获取操作记录列表
- GET /api/hyperliquid/actions/stats: 获取操作统计数据

记录内容：
- 操作类型：开仓、平仓、设置杠杆等
- 执行状态：成功、失败、待处理
- 请求详情：原始请求参数
- 响应详情：交易所返回结果
- 错误信息：失败时的错误详情

查询过滤：
- 按账户ID筛选
- 按环境（testnet/mainnet）筛选
- 按钱包地址筛选
- 分页和数量限制

应用场景：
- 交易执行审计和追踪
- 故障排查和问题定位
- 交易行为分析统计
- 系统健康监控
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import HyperliquidExchangeAction

router = APIRouter(prefix="/api/hyperliquid/actions", tags=["Hyperliquid Actions"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize_action(action: HyperliquidExchangeAction) -> Dict[str, Any]:
    return {
        "id": action.id,
        "timestamp": action.created_at.isoformat() if action.created_at else None,
        "account_id": action.account_id,
        "environment": action.environment,
        "wallet_address": action.wallet_address,
        "action_type": action.action_type,
        "status": action.status,
        "symbol": action.symbol,
        "side": action.side,
        "leverage": action.leverage,
        "size": float(action.size) if action.size is not None else None,
        "price": float(action.price) if action.price is not None else None,
        "notional": float(action.notional) if action.notional is not None else None,
        "request_weight": action.request_weight,
        "error_message": action.error_message,
        "request_payload": action.request_payload,
        "response_payload": action.response_payload,
    }


@router.get("/")
def list_exchange_actions(
    limit: int = Query(100, ge=1, le=500),
    account_id: Optional[int] = Query(None),
    environment: Optional[str] = Query(None, regex="^(testnet|mainnet)$"),
    wallet_address: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    query = db.query(HyperliquidExchangeAction)

    if account_id is not None:
        query = query.filter(HyperliquidExchangeAction.account_id == account_id)
    if environment is not None:
        query = query.filter(HyperliquidExchangeAction.environment == environment)
    if wallet_address is not None:
        query = query.filter(HyperliquidExchangeAction.wallet_address == wallet_address)

    total = query.count()

    entries = (
        query.order_by(HyperliquidExchangeAction.created_at.desc())
        .limit(limit)
        .all()
    )

    success_count = (
        query.filter(HyperliquidExchangeAction.status == "success").count()
    )
    error_count = (
        query.filter(HyperliquidExchangeAction.status == "error").count()
    )
    request_weight_sum = (
        query.with_entities(
            func.coalesce(func.sum(HyperliquidExchangeAction.request_weight), 0)
        ).scalar()
    )

    last_24h = (
        query.filter(
            HyperliquidExchangeAction.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).count()
    )

    return {
        "entries": [_serialize_action(entry) for entry in entries],
        "stats": {
            "total": total,
            "success": success_count,
            "error": error_count,
            "last24h": last_24h,
            "request_weight_sum": request_weight_sum,
        },
    }
