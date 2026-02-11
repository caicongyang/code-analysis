"""
Order matching service
Implements conditional execution logic for limit orders
"""
"""
订单匹配服务

实现加密货币限价订单的条件执行逻辑和完整的订单生命周期管理。
提供从订单创建到执行完成的完整交易流程支持。

核心功能：
1. **订单创建**: 支持市价单和限价单的创建与验证
2. **资金检查**: 创建前验证账户资金和持仓充足性
3. **条件执行**: 基于市场价格的限价单自动执行逻辑
4. **订单管理**: 支持订单查询、取消和状态更新
5. **交易记录**: 自动创建交易记录和更新账户状态
6. **实时推送**: 通过WebSocket推送交易和持仓更新

设计特点：
- **精确计算**: 使用Decimal避免浮点数精度问题
- **原子操作**: 数据库事务确保操作的原子性
- **并发安全**: 执行前再次检查资金避免竞态条件
- **实时反馈**: 交易完成后立即推送状态更新

订单类型支持：
1. **市价单(MARKET)**: 立即以市场价格执行
2. **限价单(LIMIT)**: 满足价格条件时执行
   - 买入限价单: 限价 >= 市场价时执行
   - 卖出限价单: 限价 <= 市场价时执行

交易流程：
创建订单 → 验证资金/持仓 → 等待执行条件 → 执行交易 → 更新状态 → 实时推送

应用场景：
- **手动下单**: 用户通过界面创建限价单和市价单
- **自动交易**: AI交易系统的订单执行
- **订单管理**: 查询和取消待处理订单
- **实时监控**: 监控订单执行状态和资金变化
"""

import uuid
from decimal import Decimal
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
import logging

from database.models import Order, Position, Trade, Account, User, CRYPTO_MIN_COMMISSION, CRYPTO_COMMISSION_RATE, CRYPTO_MIN_ORDER_QUANTITY, CRYPTO_LOT_SIZE
from .market_data import get_last_price

logger = logging.getLogger(__name__)


def _calc_commission(notional: Decimal) -> Decimal:
    """Calculate commission"""
    """
    计算交易手续费

    基于交易名义金额计算手续费，采用比例费率和最低费用的较大值。
    确保小额交易有合理的最低费用，大额交易按比例收费。

    Args:
        notional: 交易名义金额（价格 × 数量）

    Returns:
        Decimal: 计算得出的手续费金额

    计算公式：
    - 比例费用 = 名义金额 × 费率（CRYPTO_COMMISSION_RATE）
    - 最低费用 = CRYPTO_MIN_COMMISSION
    - 最终费用 = max(比例费用, 最低费用)

    费率配置：
    - CRYPTO_COMMISSION_RATE: 加密货币交易的费率百分比
    - CRYPTO_MIN_COMMISSION: 最低手续费金额

    设计考虑：
    - 使用Decimal确保精确的货币计算
    - 避免浮点数精度导致的费用偏差
    - 保护小额交易者的费用合理性
    - 确保大额交易的费率一致性
    """
    pct_fee = notional * Decimal(str(CRYPTO_COMMISSION_RATE))
    min_fee = Decimal(str(CRYPTO_MIN_COMMISSION))
    return max(pct_fee, min_fee)


def create_order(db: Session, account: Account, symbol: str, name: str,
                side: str, order_type: str, price: Optional[float], quantity: float) -> Order:
    """
    Create limit order

    Args:
        db: Database session
        account: Account object
        symbol: crypto Symbol
        name: crypto name
        side: Buy/side direction (BUY/SELL)
        order_type: Order type (MARKET/LIMIT)
        price: Order price (required for limit orders)
        quantity: Order quantity

    Returns:
        Created order object

    Raises:
        ValueError: Parameter validation failed or insufficient funds/positions
    """
    # Basic parameter validation (crypto-only)
    
    # For crypto, we support fractional quantities, so no lot size validation needed
    # if quantity % CRYPTO_LOT_SIZE != 0:
    #     raise ValueError(f"Order quantity must be integer multiple of {CRYPTO_LOT_SIZE}")

    # For crypto, allow very small quantities (minimum $1 worth)
    if quantity <= 0:
        raise ValueError(f"Order quantity must be > 0")

    if order_type == "LIMIT" and (price is None or price <= 0):
        raise ValueError("Limit order must specify valid order price")
    
    # Get current market price for fund validation (only when cookie is configured)
    current_market_price = None
    if order_type == "MARKET":
        # Market order: get current price for fund validation
        try:
            current_market_price = get_last_price(symbol)
        except Exception as err:
            raise ValueError(f"Unable to get market price for market order: {err}")
        check_price = Decimal(str(current_market_price))
    else:
        # Limit order: use order price for fund validation
        check_price = Decimal(str(price))

    # Pre-check funds and positions
    if side == "BUY":
        # Buy: check if sufficient cash available
        notional = check_price * Decimal(quantity)
        commission = _calc_commission(notional)
        cash_needed = notional + commission

        if Decimal(str(account.current_cash)) < cash_needed:
            raise ValueError(f"Insufficient cash. Need ${cash_needed:.2f}, current cash ${account.current_cash:.2f}")

    else:  # SELL
        # Sell: check if sufficient positions available
        position = (
            db.query(Position)
            .filter(Position.account_id == account.id, Position.symbol == symbol, Position.market == "CRYPTO")
            .first()
        )

        if not position or Decimal(str(position.available_quantity)) < Decimal(str(quantity)):
            available_qty = float(position.available_quantity) if position else 0
            raise ValueError(f"Insufficient positions. Need {quantity} {symbol}, available {available_qty} {symbol}")
    
    # Create order
    order = Order(
        version="v1",
        account_id=account.id,
        order_no=uuid.uuid4().hex[:16],
        symbol=symbol,
        name=name,
        market="CRYPTO",
        side=side,
        order_type=order_type,
        price=price,
        quantity=quantity,
        filled_quantity=0,
        status="PENDING",
    )

    db.add(order)
    db.flush()

    logger.info(f"Created limit order: {order.order_no}, {side} {quantity} {symbol} @ {price if price else 'MARKET'}")

    return order


def check_and_execute_order(db: Session, order: Order) -> bool:
    """
    Check and execute limit order

    Execution conditions:
    - Buy: order price >= current market price and sufficient funds
    - Sell: order price <= current market price and sufficient positions

    Args:
        db: Database session
        order: Order to check

    Returns:
        Whether order was executed
    """
    if order.status != "PENDING":
        return False
    
    # Check if cookie is configured, skip order checking if not
    try:
        # Get current market price
        current_price = get_last_price(order.symbol, order.market)
        current_price_decimal = Decimal(str(current_price))

        # Get user information
        account = db.query(Account).filter(Account.id == order.account_id).first()
        if not account:
            logger.error(f"Account corresponding to order {order.order_no} does not exist")
            return False

        # Check execution conditions
        should_execute = False
        execution_price = current_price_decimal

        if order.order_type == "MARKET":
            # Market order executes immediately
            should_execute = True
            execution_price = current_price_decimal

        elif order.order_type == "LIMIT":
            # Limit order conditional execution
            limit_price = Decimal(str(order.price))

            if order.side == "BUY":
                # Buy: order price >= current market price
                if limit_price >= current_price_decimal:
                    should_execute = True
                    execution_price = current_price_decimal  # Execute at market price

            else:  # SELL
                # Sell: order price <= current market price
                if limit_price <= current_price_decimal:
                    should_execute = True
                    execution_price = current_price_decimal  # Execute at market price

        if not should_execute:
            logger.debug(f"Order {order.order_no} does not meet execution condition: {order.side} {order.price} vs market {current_price}")
            return False

        # Execute order
        return _execute_order(db, order, account, execution_price)

    except Exception as e:
        logger.error(f"Error checking order {order.order_no}: {e}")
        return False


def _release_frozen_on_fill(account: Account, order: Order, execution_price: Decimal, commission: Decimal):
    """Release frozen cash on fill (for BUY only)"""
    if order.side == "BUY":
        # Estimated frozen amount may differ from actual execution, release based on actual execution amount
        notional = execution_price * Decimal(order.quantity)
        frozen_to_release = notional + commission
        account.frozen_cash = float(max(Decimal(str(account.frozen_cash)) - frozen_to_release, Decimal('0')))


def _execute_order(db: Session, order: Order, account: Account, execution_price: Decimal) -> bool:
    """
    Execute order fill

    Args:
        db: Database session
        order: Order object
        account: Account object
        execution_price: Execution price

    Returns:
        Whether execution was successful
    """
    try:
        quantity = Decimal(str(order.quantity))  # Ensure quantity is Decimal
        notional = execution_price * quantity
        commission = _calc_commission(notional)
        
        # Re-check funds and positions (prevent concurrency issues)
        if order.side == "BUY":
            cash_needed = notional + commission
            if Decimal(str(account.current_cash)) < cash_needed:
                logger.warning(f"Insufficient cash when executing order {order.order_no}")
                return False
                
            # Deduct cash
            account.current_cash = float(Decimal(str(account.current_cash)) - cash_needed)
            
            # Update position
            position = (
                db.query(Position)
                .filter(Position.account_id == account.id, Position.symbol == order.symbol, Position.market == order.market)
                .first()
            )
            
            if not position:
                position = Position(
                    version="v1",
                    account_id=account.id,
                    symbol=order.symbol,
                    name=order.name,
                    market=order.market,
                    quantity=0,
                    available_quantity=0,
                    avg_cost=0,
                )
                db.add(position)
                db.flush()
            
            # Calculate new average cost (use Decimal for precision)
            old_qty = Decimal(str(position.quantity))
            old_cost = Decimal(str(position.avg_cost))
            new_qty = old_qty + quantity
            
            if old_qty == 0:
                new_avg_cost = execution_price
            else:
                new_avg_cost = (old_cost * old_qty + notional) / new_qty
            
            position.quantity = float(new_qty)  # Store as float for database
            position.available_quantity = float(Decimal(str(position.available_quantity)) + quantity)
            position.avg_cost = float(new_avg_cost)
            
        else:  # SELL
            # Check position
            position = (
                db.query(Position)
                .filter(Position.account_id == account.id, Position.symbol == order.symbol, Position.market == order.market)
                .first()
            )

            if not position or Decimal(str(position.available_quantity)) < quantity:
                logger.warning(f"Insufficient position when executing order {order.order_no}")
                return False

            # Reduce position (use Decimal for precision)
            position.quantity = float(Decimal(str(position.quantity)) - quantity)
            position.available_quantity = float(Decimal(str(position.available_quantity)) - quantity)
            
            # Add cash
            cash_gain = notional - commission
            account.current_cash = float(Decimal(str(account.current_cash)) + cash_gain)
        
        # Create trade record
        trade = Trade(
            order_id=order.id,
            account_id=account.id,
            symbol=order.symbol,
            name=order.name,
            market=order.market,
            side=order.side,
            price=float(execution_price),
            quantity=float(quantity),
            commission=float(commission),
        )
        db.add(trade)

        # Release frozen (BUY)
        _release_frozen_on_fill(account, order, execution_price, commission)
        
        # Update order status
        order.filled_quantity = float(quantity)
        order.status = "FILLED"

        db.commit()

        logger.info(f"Order {order.order_no} executed: {order.side} {quantity} {order.symbol} @ ${execution_price}")

        # Broadcast real-time updates via WebSocket
        import asyncio
        from api.ws import broadcast_trade_update, broadcast_position_update
        from repositories.position_repo import list_positions

        try:
            # Broadcast trade update
            asyncio.create_task(broadcast_trade_update({
                "trade_id": trade.id,
                "account_id": account.id,
                "account_name": account.name,
                "symbol": trade.symbol,
                "name": trade.name,
                "market": trade.market,
                "side": trade.side,
                "price": float(execution_price),
                "quantity": float(quantity),
                "commission": float(commission),
                "notional": float(notional),
                "trade_time": trade.trade_time.isoformat() if hasattr(trade.trade_time, 'isoformat') else str(trade.trade_time),
                "direction": trade.side  # For frontend compatibility
            }))

            # Broadcast position update
            positions = list_positions(db, account.id)
            positions_data = [
                {
                    "id": p.id,
                    "account_id": p.account_id,
                    "symbol": p.symbol,
                    "name": p.name,
                    "market": p.market,
                    "quantity": float(p.quantity),
                    "available_quantity": float(p.available_quantity),
                    "avg_cost": float(p.avg_cost),
                    "last_price": None,  # Will be updated by frontend
                    "market_value": None  # Will be updated by frontend
                }
                for p in positions
            ]
            asyncio.create_task(broadcast_position_update(account.id, positions_data))

        except Exception as broadcast_err:
            # Don't fail the order execution if broadcast fails
            logger.warning(f"Failed to broadcast updates for order {order.order_no}: {broadcast_err}")

        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Error executing order {order.order_no}: {e}")
        return False


def get_pending_orders(db: Session, account_id: Optional[int] = None) -> List[Order]:
    """
    Get pending orders

    Args:
        db: Database session
        account_id: Account ID, when None get all accounts' pending orders

    Returns:
        List of pending orders
    """
    query = db.query(Order).filter(Order.status == "PENDING")
    
    if account_id is not None:
        query = query.filter(Order.account_id == account_id)
    
    return query.order_by(Order.created_at).all()


def _release_frozen_on_cancel(account: Account, order: Order):
    """Release frozen on order cancel (BUY only)"""
    if order.side == "BUY":
        # Conservative release: estimate frozen amount based on order price, avoid getting market price
        ref_price = float(order.price or 0.0)
        if ref_price <= 0:
            # If no order price (theoretically shouldn't happen), use conservative estimate
            logger.warning(f"Order {order.order_no} has no order price, unable to accurately release frozen funds")
            ref_price = 100.0  # Use default value

        notional = Decimal(str(ref_price)) * Decimal(order.quantity)
        commission = _calc_commission(notional)
        release_amt = notional + commission
        account.frozen_cash = float(max(Decimal(str(account.frozen_cash)) - release_amt, Decimal('0')))


def cancel_order(db: Session, order: Order, reason: str = "User cancelled") -> bool:
    """
    Cancel order

    Args:
        db: Database session
        order: Order object
        reason: Cancel reason

    Returns:
        Whether cancellation was successful
    """
    if order.status != "PENDING":
        return False
    
    try:
        order.status = "CANCELLED"
        # Release frozen
        account = db.query(Account).filter(Account.id == order.account_id).first()
        if account:
            _release_frozen_on_cancel(account, order)
        db.commit()
        
        logger.info(f"Order {order.order_no} cancelled: {reason}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error cancelling order {order.order_no}: {e}")
        return False


def process_all_pending_orders(db: Session) -> Tuple[int, int]:
    """
    Process all pending orders

    Args:
        db: Database session

    Returns:
        (Executed orders count, Total checked orders)
    """
    pending_orders = get_pending_orders(db)
    executed_count = 0
    
    for order in pending_orders:
        if check_and_execute_order(db, order):
            executed_count += 1
    
    logger.info(f"Processing pending orders: checked {len(pending_orders)} orders, executed {executed_count} orders")
    return executed_count, len(pending_orders)