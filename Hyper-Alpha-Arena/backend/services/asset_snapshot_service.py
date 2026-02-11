"""
Record account asset snapshots on price updates.
"""
"""
账户资产快照记录服务

基于价格更新事件记录账户资产快照，为资产曲线计算和性能分析
提供历史数据支持。这是投资组合管理和风险控制的重要数据源。

核心功能：
1. 实时资产快照：价格变动时自动记录账户总资产
2. 持仓价值计算：基于最新价格计算所有持仓的市值
3. 历史数据管理：定期清理旧快照，控制存储空间
4. 实时广播：向WebSocket客户端推送资产更新
5. 缓存管理：更新后失效资产曲线缓存

数据结构：
- 账户余额（现金）
- 持仓市值（基于当前价格）
- 总资产价值（余额+持仓）
- 未实现盈亏
- 快照时间戳

应用场景：
1. 资产曲线绘制：展示账户净值变化趋势
2. 收益率计算：计算各时间段的投资回报
3. 风险分析：分析资产波动和最大回撤
4. 性能对比：多账户性能的横向比较
5. 实时监控：资产变动的实时提醒

技术特点：
- 事件驱动：基于价格更新事件触发快照
- 频率控制：限制快照频率，避免存储空间浪费
- 批量处理：一次价格更新处理所有活跃账户
- 异步广播：实时向前端推送资产更新
- 数据清理：自动清理过期历史数据

性能优化：
- 限频机制：60秒内最多记录一次快照
- 批量查询：一次查询获取所有账户信息
- 缓存失效：智能缓存更新策略
- 异步处理：不阻塞主线程的数据处理
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Account, AccountAssetSnapshot, Position
from services.asset_curve_calculator import invalidate_asset_curve_cache
from services.market_data import get_last_price
from api.ws import broadcast_arena_asset_update, manager

logger = logging.getLogger(__name__)

SNAPSHOT_RETENTION_HOURS = 24 * 30  # Keep 30 days of asset snapshots
# 快照保留时间配置：保留30天的资产快照历史
# - 30天足够支持月度性能分析和回测
# - 平衡存储成本和历史数据的价值
# - 支持用户查看近期投资表现趋势


def _get_active_accounts(db: Session) -> List[Account]:
    """
    获取所有活跃的AI交易账户

    查询数据库中所有启用状态的AI交易账户，用于批量创建资产快照。
    只处理AI类型的账户，因为手动账户的资产变动不需要自动快照。

    Args:
        db: 数据库会话对象

    Returns:
        List[Account]: 活跃的AI交易账户列表

    查询条件：
    - is_active == "true": 账户处于启用状态
    - account_type == "AI": 仅处理AI自动交易账户
    """
    return (
        db.query(Account)
        .filter(Account.is_active == "true", Account.account_type == "AI")
        .all()
    )


# Global variable to track last snapshot time
# 全局变量：跟踪上次快照记录时间
_last_snapshot_time = 0  # Unix时间戳，用于实现频率限制（60秒一次）

def handle_price_update(event: Dict[str, Any]) -> None:
    """Persist account asset snapshots based on the latest price event."""
    global _last_snapshot_time

    # Limit to once per 60 seconds
    import time
    current_time = time.time()
    if current_time - _last_snapshot_time < 60:
        return

    _last_snapshot_time = current_time

    session = SessionLocal()
    try:
        accounts = _get_active_accounts(session)
        if not accounts:
            return

        trigger_symbol = event.get("symbol")
        trigger_market = event.get("market", "CRYPTO")
        event_time: datetime = event.get("event_time") or datetime.now(tz=timezone.utc)

        snapshots: List[AccountAssetSnapshot] = []
        symbol_totals = defaultdict(float)
        accounts_payload: List[Dict[str, Any]] = []
        total_available_cash = 0.0
        total_frozen_cash = 0.0
        total_positions_value = 0.0
        price_cache: Dict[str, float] = {}

        for account in accounts:
            try:
                positions = (
                    session.query(Position)
                    .filter(Position.account_id == account.id)
                    .all()
                )

                positions_value = 0.0
                for position in positions:
                    symbol_key = (position.symbol or "").upper()
                    market_key = position.market or "CRYPTO"
                    cache_key = f"{symbol_key}.{market_key}"

                    try:
                        if cache_key in price_cache:
                            price = price_cache[cache_key]
                        else:
                            price = float(get_last_price(symbol_key, market_key))
                            price_cache[cache_key] = price
                    except Exception as price_err:
                        logger.debug(
                            "Skipping valuation for %s.%s: %s",
                            symbol_key,
                            market_key,
                            price_err,
                        )
                        continue

                    current_value = price * float(position.quantity or 0.0)
                    positions_value += current_value
                    symbol_totals[symbol_key] += current_value

                available_cash = float(account.current_cash or 0.0)
                frozen_cash = float(account.frozen_cash or 0.0)
                total_assets = positions_value + available_cash

                total_available_cash += available_cash
                total_frozen_cash += frozen_cash
                total_positions_value += positions_value

                accounts_payload.append(
                    {
                        "account_id": account.id,
                        "account_name": account.name,
                        "model": account.model,
                        "available_cash": round(available_cash, 2),
                        "frozen_cash": round(frozen_cash, 2),
                        "positions_value": round(positions_value, 2),
                        "total_assets": round(total_assets, 2),
                    }
                )

                snapshot = AccountAssetSnapshot(
                    account_id=account.id,
                    total_assets=total_assets,
                    cash=available_cash,
                    positions_value=positions_value,
                    trigger_symbol=trigger_symbol,
                    trigger_market=trigger_market,
                    event_time=event_time,
                )
                snapshots.append(snapshot)
            except Exception as account_err:
                logger.warning(
                    "Failed to compute snapshot for account %s: %s",
                    account.name,
                    account_err,
                )

        if snapshots:
            session.bulk_save_objects(snapshots)
            session.commit()
            invalidate_asset_curve_cache()

        if manager.has_connections():
            update_payload = {
                "generated_at": event_time.isoformat(),
                "totals": {
                    "available_cash": round(total_available_cash, 2),
                    "frozen_cash": round(total_frozen_cash, 2),
                    "positions_value": round(total_positions_value, 2),
                    "total_assets": round(
                        total_available_cash + total_frozen_cash + total_positions_value, 2
                    ),
                },
                "symbols": {symbol: round(value, 2) for symbol, value in symbol_totals.items()},
                "accounts": accounts_payload,
            }
            try:
                manager.schedule_task(broadcast_arena_asset_update(update_payload))
            except Exception as broadcast_err:
                logger.debug("Failed to schedule arena asset broadcast: %s", broadcast_err)

        _purge_old_snapshots(session, cutoff_hours=SNAPSHOT_RETENTION_HOURS)
    except Exception as err:
        session.rollback()
        logger.error("Failed to record asset snapshots: %s", err)
    finally:
        session.close()


def _purge_old_snapshots(session: Session, cutoff_hours: int) -> None:
    """Remove snapshots older than retention window to control storage."""
    cutoff_time = datetime.now(tz=timezone.utc) - timedelta(hours=cutoff_hours)
    deleted = (
        session.query(AccountAssetSnapshot)
        .filter(AccountAssetSnapshot.event_time < cutoff_time)
        .delete(synchronize_session=False)
    )
    if deleted:
        session.commit()
        logger.debug("Purged %d old asset snapshots", deleted)
