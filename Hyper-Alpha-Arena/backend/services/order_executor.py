"""
订单执行服务（传统版本）

这是一个早期的订单执行服务，主要用于美国股票市场的订单处理。
注意：当前项目主要使用Hyperliquid加密货币交易，此模块可能已不是主要使用的版本。

功能特点：
- 支持美国股票市场的订单执行
- 实现基础的订单生命周期管理
- 处理手续费计算和资金检查
- 维护订单、持仓和交易记录

设计限制：
- 仅支持美国市场（US Market）
- 不支持加密货币永续合约
- 缺少现代化的风险控制功能
- 没有集成Hyperliquid等DeFi协议

注意：在当前Hyper Alpha Arena架构中，主要的订单执行逻辑位于：
- services/hyperliquid_trading_client.py（Hyperliquid交易客户端）
- services/trading_commands.py（交易命令处理）
- 相关的AI驱动订单执行服务

此文件主要作为传统交易系统的参考实现保留。
"""

import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from database.models import Order, Position, Trade, User, US_MIN_COMMISSION, US_COMMISSION_RATE, US_MIN_ORDER_QUANTITY, US_LOT_SIZE
from .market_data import get_last_price


def _calc_commission(notional: Decimal) -> Decimal:
    """
    计算交易手续费（美国市场）

    根据美国股票市场的手续费规则计算订单手续费。
    采用百分比手续费和最低手续费中的较大值。

    Args:
        notional: 订单名义金额（价格 × 数量）

    Returns:
        Decimal: 计算得出的手续费金额

    计算规则：
    - 百分比手续费：notional × US_COMMISSION_RATE
    - 最低手续费：US_MIN_COMMISSION
    - 实际手续费：max(百分比手续费, 最低手续费)

    注意：
    - 使用Decimal类型确保财务计算精度
    - 手续费标准基于美国股票市场规则
    - 加密货币市场使用不同的手续费计算逻辑
    """
    pct_fee = notional * Decimal(str(US_COMMISSION_RATE))  # 百分比手续费
    min_fee = Decimal(str(US_MIN_COMMISSION))              # 最低手续费
    return max(pct_fee, min_fee)                           # 取较大值

def place_and_execute(db: Session, user: User, symbol: str, name: str, market: str, side: str, order_type: str, price: float | None, quantity: int) -> Order:
    # Only support US market
    if market != "US":
        raise ValueError("Only US market is supported")

    # Adjust quantity to lot size
    if quantity % US_LOT_SIZE != 0:
        raise ValueError(f"quantity must be a multiple of lot_size={US_LOT_SIZE}")
    if quantity < US_MIN_ORDER_QUANTITY:
        raise ValueError(f"quantity must be >= min_order_quantity={US_MIN_ORDER_QUANTITY}")

    exec_price = Decimal(str(price if (order_type == "LIMIT" and price) else get_last_price(symbol, market)))

    order = Order(
        version="v1",
        user_id=user.id,
        order_no=uuid.uuid4().hex[:16],
        symbol=symbol,
        name=name,
        market=market,
        side=side,
        order_type=order_type,
        price=float(exec_price),
        quantity=quantity,
        filled_quantity=0,
        status="PENDING",
    )
    db.add(order)
    db.flush()

    notional = exec_price * Decimal(quantity)
    commission = _calc_commission(notional)

    if side == "BUY":
        cash_needed = notional + commission
        if Decimal(str(user.current_cash)) < cash_needed:
            raise ValueError("Insufficient USD cash")
        user.current_cash = float(Decimal(str(user.current_cash)) - cash_needed)
        
        # position update (avg cost)
        pos = (
            db.query(Position)
            .filter(Position.user_id == user.id, Position.symbol == symbol, Position.market == market)
            .first()
        )
        if not pos:
            pos = Position(
                version="v1",
                user_id=user.id,
                symbol=symbol,
                name=name,
                market=market,
                quantity=0,
                available_quantity=0,
                avg_cost=0,
            )
            db.add(pos)
            db.flush()
        new_qty = int(pos.quantity) + quantity
        new_cost = (Decimal(str(pos.avg_cost)) * Decimal(int(pos.quantity)) + notional) / Decimal(new_qty)
        pos.quantity = new_qty
        pos.available_quantity = int(pos.available_quantity) + quantity
        pos.avg_cost = float(new_cost)
    else:  # SELL
        pos = (
            db.query(Position)
            .filter(Position.user_id == user.id, Position.symbol == symbol, Position.market == market)
            .first()
        )
        if not pos or int(pos.available_quantity) < quantity:
            raise ValueError("Insufficient position to sell")
        pos.quantity = int(pos.quantity) - quantity
        pos.available_quantity = int(pos.available_quantity) - quantity
        
        cash_gain = notional - commission
        user.current_cash = float(Decimal(str(user.current_cash)) + cash_gain)

    trade = Trade(
        order_id=order.id,
        user_id=user.id,
        symbol=symbol,
        name=name,
        market=market,
        side=side,
        price=float(exec_price),
        quantity=quantity,
        commission=float(commission),
    )
    db.add(trade)

    order.filled_quantity = quantity
    order.status = "FILLED"

    db.commit()
    db.refresh(order)
    return order
