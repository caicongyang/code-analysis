"""
回测执行模拟器 (Execution Simulator for Backtest)

模拟真实条件下的订单执行，包括：
- 滑点计算：买入时价格上浮，卖出时价格下浮
- 手续费计算：基于交易名义价值计算手续费
- 止盈止损订单检查：检查TP/SL订单是否触发
- 持仓管理：开仓、平仓、加仓等操作
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .virtual_account import VirtualAccount, VirtualPosition
from .models import BacktestTradeRecord

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """
    Result of order execution simulation.
    
    订单执行模拟结果类。
    """
    success: bool                          # 是否执行成功
    executed_price: float = 0.0           # 执行价格（含滑点）
    executed_size: float = 0.0            # 执行数量
    fee: float = 0.0                      # 手续费
    slippage: float = 0.0                 # 滑点金额
    error: Optional[str] = None           # 错误信息


class ExecutionSimulator:
    """
    Simulates order execution for backtesting.

    Handles:
    - Slippage calculation based on order side
    - Fee calculation (maker/taker)
    - TP/SL order trigger checking
    - Position opening/closing

    回测订单执行模拟器。

    处理：
    - 基于订单方向的滑点计算
    - 手续费计算（maker/taker）
    - 止盈止损订单触发检查
    - 持仓开仓/平仓操作
    """

    def __init__(
        self,
        slippage_percent: float = 0.05,
        fee_rate: float = 0.035,
    ):
        """
        Initialize execution simulator.

        初始化执行模拟器。

        Args:
            slippage_percent: 默认滑点百分比（0.05 = 0.05%）
            fee_rate: 交易手续费率百分比（0.035 = 0.035%，Hyperliquid的taker费率）
        """
        self.slippage_percent = slippage_percent
        self.fee_rate = fee_rate

    def calculate_execution_price(
        self,
        price: float,
        side: str,
        slippage_pct: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Calculate execution price with slippage.

        计算含滑点的执行价格。

        Args:
            price: 基础价格
            side: 交易方向 "buy"（买入）或 "sell"（卖出）
            slippage_pct: 覆盖滑点百分比（如果提供）

        Returns:
            (executed_price, slippage_amount) 元组，包含执行价格和滑点金额
        """
        slippage = slippage_pct if slippage_pct is not None else self.slippage_percent

        if side.lower() == "buy":
            # Buying pushes price up 买入推高价格
            executed_price = price * (1 + slippage / 100)
        else:
            # Selling pushes price down 卖出压低价格
            executed_price = price * (1 - slippage / 100)

        slippage_amount = abs(executed_price - price)
        return executed_price, slippage_amount

    def calculate_fee(
        self,
        notional: float,
        fee_rate: Optional[float] = None,
    ) -> float:
        """
        Calculate trading fee.

        计算交易手续费。

        Args:
            notional: 交易名义价值（数量 * 价格）
            fee_rate: 覆盖手续费率（如果提供）

        Returns:
            手续费金额（美元）
        """
        rate = fee_rate if fee_rate is not None else self.fee_rate
        return notional * rate / 100

    def check_tp_sl_triggers(
        self,
        account: VirtualAccount,
        prices: Dict[str, float],
        timestamp: int,
    ) -> List[BacktestTradeRecord]:
        """
        Check if any TP/SL orders should trigger.

        Each pending order is independent (like Hyperliquid) - when triggered,
        only closes the portion of position that order controls.

        检查是否有止盈止损订单应该触发。

        每个挂单都是独立的（类似Hyperliquid）- 当触发时，只平掉该订单控制的持仓部分。

        Args:
            account: 虚拟账户状态
            prices: 当前价格字典 {标的: 价格}
            timestamp: 当前时间戳

        Returns:
            触发订单的交易记录列表
        """
        triggered_trades = []
        orders_to_remove = []

        # Check each pending order independently
        for order in account.pending_orders:
            symbol = order.symbol
            if symbol not in prices:
                continue

            pos = account.get_position(symbol)
            if not pos:
                # Position no longer exists, mark order for removal
                orders_to_remove.append(order.order_id)
                continue

            current_price = prices[symbol]
            should_trigger = False

            # Check trigger condition based on order type and position side
            if order.order_type == "take_profit":
                if pos.side == "long" and current_price >= order.trigger_price:
                    should_trigger = True
                elif pos.side == "short" and current_price <= order.trigger_price:
                    should_trigger = True
            elif order.order_type == "stop_loss":
                if pos.side == "long" and current_price <= order.trigger_price:
                    should_trigger = True
                elif pos.side == "short" and current_price >= order.trigger_price:
                    should_trigger = True

            if should_trigger:
                # Apply slippage to exit price
                close_side = "sell" if pos.side == "long" else "buy"
                executed_price, _ = self.calculate_execution_price(order.trigger_price, close_side)

                # Calculate fee for this portion
                notional = order.size * executed_price
                fee = self.calculate_fee(notional)

                # Partial close position using order's entry price for accurate PnL
                pnl = account.partial_close_position(
                    symbol=symbol,
                    size=order.size,
                    exit_price=executed_price,
                    fee=fee,
                    entry_price=order.entry_price,
                )

                if pnl is not None:
                    # Calculate PnL percent based on this order's entry
                    entry_notional = order.size * order.entry_price
                    pnl_percent = (pnl / entry_notional * 100) if entry_notional > 0 else 0

                    exit_reason = "tp" if order.order_type == "take_profit" else "sl"
                    trade = BacktestTradeRecord(
                        timestamp=order.created_at,
                        trigger_type="",
                        symbol=symbol,
                        operation="close",
                        side=pos.side,
                        entry_price=order.entry_price,
                        size=order.size,
                        leverage=pos.leverage,
                        exit_price=executed_price,
                        exit_timestamp=timestamp,
                        exit_reason=exit_reason,
                        pnl=pnl,
                        pnl_percent=pnl_percent,
                        fee=fee,
                        reason=f"{'Take Profit' if exit_reason == 'tp' else 'Stop Loss'} triggered",
                    )
                    triggered_trades.append(trade)

                # Mark order for removal (it's been executed)
                orders_to_remove.append(order.order_id)

        # Remove triggered/invalid orders
        for order_id in orders_to_remove:
            account.remove_pending_order(order_id)

        return triggered_trades

    def check_tp_sl_with_klines(
        self,
        account: VirtualAccount,
        klines: List[Dict[str, Any]],
        position_side: str,
        data_provider: Any,
    ) -> List[BacktestTradeRecord]:
        """
        Check TP/SL triggers using K-line high/low prices between triggers.

        This provides more accurate TP/SL detection by checking if price
        touched TP/SL levels at any point, not just at trigger timestamps.

        使用K线最高/最低价检查两次触发之间的止盈止损触发。

        通过检查价格是否在任何时点触及TP/SL水平，而不仅仅是在触发时间戳，
        提供更准确的TP/SL检测。

        Args:
            account: 虚拟账户状态
            klines: 上次触发和当前触发之间的K线列表，每个K线包含：timestamp, high, low, close
            position_side: 持仓方向 "long"（做多）或 "short"（做空）
            data_provider: 历史数据提供器，用于查询所有标的的价格

        Returns:
            触发订单的交易记录列表，按时间顺序排列
        """
        triggered_trades = []
        orders_to_remove = []

        # Process klines in chronological order
        for kline in klines:
            kline_time_ms = kline["timestamp"] * 1000
            high = kline["high"]
            low = kline["low"]

            # Check each pending order
            for order in list(account.pending_orders):
                if order.order_id in orders_to_remove:
                    continue

                symbol = order.symbol
                pos = account.get_position(symbol)
                if not pos:
                    orders_to_remove.append(order.order_id)
                    continue

                should_trigger = False
                trigger_price = order.trigger_price

                # Check trigger condition using kline high/low
                if order.order_type == "take_profit":
                    if pos.side == "long" and high >= trigger_price:
                        should_trigger = True
                    elif pos.side == "short" and low <= trigger_price:
                        should_trigger = True
                elif order.order_type == "stop_loss":
                    if pos.side == "long" and low <= trigger_price:
                        should_trigger = True
                    elif pos.side == "short" and high >= trigger_price:
                        should_trigger = True

                if should_trigger:
                    # Execute at trigger price (not kline close)
                    close_side = "sell" if pos.side == "long" else "buy"
                    executed_price, _ = self.calculate_execution_price(trigger_price, close_side)

                    # Calculate fee
                    notional = order.size * executed_price
                    fee = self.calculate_fee(notional)

                    # Partial close position
                    pnl = account.partial_close_position(
                        symbol=symbol,
                        size=order.size,
                        exit_price=executed_price,
                        fee=fee,
                        entry_price=order.entry_price,
                    )

                    if pnl is not None:
                        # Get prices for ALL position symbols at kline time for accurate equity
                        # For single symbol: only current symbol price
                        # For multi symbol: query all position symbols at same timestamp
                        kline_prices = {symbol: kline["close"]}
                        for pos_symbol in account.positions:
                            if pos_symbol != symbol:
                                # Query price at kline timestamp for other symbols
                                other_price = data_provider._get_price_at_time(
                                    pos_symbol, kline_time_ms
                                )
                                if other_price:
                                    kline_prices[pos_symbol] = other_price
                        account.update_equity(kline_prices)

                        entry_notional = order.size * order.entry_price
                        pnl_percent = (pnl / entry_notional * 100) if entry_notional > 0 else 0

                        exit_reason = "tp" if order.order_type == "take_profit" else "sl"
                        trade = BacktestTradeRecord(
                            timestamp=order.created_at,
                            trigger_type="",
                            symbol=symbol,
                            operation="close",
                            side=pos.side,
                            entry_price=order.entry_price,
                            size=order.size,
                            leverage=pos.leverage,
                            exit_price=executed_price,
                            exit_timestamp=kline_time_ms,
                            exit_reason=exit_reason,
                            pnl=pnl,
                            pnl_percent=pnl_percent,
                            fee=fee,
                            equity_after=account.equity,  # Record equity after this trade
                            reason=f"{'Take Profit' if exit_reason == 'tp' else 'Stop Loss'} triggered",
                        )
                        triggered_trades.append(trade)

                    orders_to_remove.append(order.order_id)

        # Remove triggered orders
        for order_id in orders_to_remove:
            account.remove_pending_order(order_id)

        return triggered_trades

    def execute_decision(
        self,
        decision: Any,
        account: VirtualAccount,
        current_price: float,
        timestamp: int,
        trigger_type: str = "",
        pool_name: Optional[str] = None,
        triggered_signals: Optional[List[str]] = None,
    ) -> Optional[BacktestTradeRecord]:
        """
        Execute a trading decision.

        执行交易决策。

        Args:
            decision: 策略返回的Decision对象
            account: 虚拟账户状态
            current_price: 当前市场价格
            timestamp: 当前时间戳
            trigger_type: 触发类型 "signal"（信号触发）或 "scheduled"（定时触发）
            pool_name: 信号池名称（如果是信号触发）
            triggered_signals: 触发的信号名称列表

        Returns:
            如果执行了交易则返回交易记录，否则返回None
        """
        operation = decision.operation.lower() if decision.operation else "hold"

        if operation == "hold":
            return None

        symbol = decision.symbol
        has_position = account.has_position(symbol)

        # Handle close operation
        if operation == "close":
            if not has_position:
                return None
            return self._execute_close(
                account, symbol, current_price, timestamp,
                trigger_type, pool_name, triggered_signals, decision.reason
            )

        # Handle buy/sell operations
        if operation in ("buy", "sell"):
            if has_position:
                pos = account.get_position(symbol)
                # If same direction, add to position (averaging)
                if (operation == "buy" and pos.side == "long") or \
                   (operation == "sell" and pos.side == "short"):
                    return self._execute_add_position(
                        account, decision, current_price, timestamp,
                        trigger_type, pool_name, triggered_signals
                    )
                # If opposite direction, close existing first
                self._execute_close(
                    account, symbol, current_price, timestamp,
                    trigger_type, pool_name, triggered_signals, "Reverse position"
                )

            return self._execute_open(
                account, decision, current_price, timestamp,
                trigger_type, pool_name, triggered_signals
            )

        return None

    def _execute_add_position(
        self,
        account: VirtualAccount,
        decision: Any,
        current_price: float,
        timestamp: int,
        trigger_type: str,
        pool_name: Optional[str],
        triggered_signals: Optional[List[str]],
    ) -> Optional[BacktestTradeRecord]:
        """
        Execute adding to existing position (averaging entry price).
        
        执行向现有持仓加仓（加权平均开仓价格）。
        """
        operation = decision.operation.lower()
        symbol = decision.symbol
        side = "long" if operation == "buy" else "short"

        # Calculate execution price with slippage
        exec_price, slippage = self.calculate_execution_price(current_price, operation)

        # Calculate additional position size
        portion = getattr(decision, 'target_portion_of_balance', 0.5)
        leverage = getattr(decision, 'leverage', 1)
        available = account.balance * portion
        add_size = (available * leverage) / exec_price

        if add_size <= 0:
            return None

        # Calculate fee
        notional = add_size * exec_price
        fee = self.calculate_fee(notional)

        # Get TP/SL prices for this specific order
        tp_price = getattr(decision, 'take_profit_price', None)
        sl_price = getattr(decision, 'stop_loss_price', None)

        # Get position info before adding
        pos = account.get_position(symbol)
        old_size = pos.size
        old_entry = pos.entry_price

        # Add to position (no longer pass TP/SL to position itself)
        account.add_to_position(
            symbol=symbol,
            size=add_size,
            entry_price=exec_price,
            fee=fee,
        )

        # Create independent TP/SL orders for this portion
        close_side = "sell" if side == "long" else "buy"
        if tp_price:
            account.add_pending_order(
                symbol=symbol,
                side=close_side,
                order_type="take_profit",
                trigger_price=tp_price,
                size=add_size,
                entry_price=exec_price,
                timestamp=timestamp,
            )
        if sl_price:
            account.add_pending_order(
                symbol=symbol,
                side=close_side,
                order_type="stop_loss",
                trigger_price=sl_price,
                size=add_size,
                entry_price=exec_price,
                timestamp=timestamp,
            )

        # Get updated position info
        updated_pos = account.get_position(symbol)

        return BacktestTradeRecord(
            timestamp=timestamp,
            trigger_type=trigger_type,
            symbol=symbol,
            operation="add_position",
            side=side,
            entry_price=exec_price,
            size=add_size,
            leverage=leverage,
            fee=fee,
            reason=getattr(decision, 'reason', '') + f" (Added to position, avg entry: {updated_pos.entry_price:.2f})",
            pool_name=pool_name,
            triggered_signals=triggered_signals or [],
        )

    def _execute_open(
        self,
        account: VirtualAccount,
        decision: Any,
        current_price: float,
        timestamp: int,
        trigger_type: str,
        pool_name: Optional[str],
        triggered_signals: Optional[List[str]],
    ) -> Optional[BacktestTradeRecord]:
        """
        Execute position open.
        
        执行开仓操作。
        """
        operation = decision.operation.lower()
        symbol = decision.symbol
        side = "long" if operation == "buy" else "short"

        # Calculate execution price with slippage
        exec_price, slippage = self.calculate_execution_price(current_price, operation)

        # Calculate position size
        portion = getattr(decision, 'target_portion_of_balance', 0.5)
        leverage = getattr(decision, 'leverage', 1)
        available = account.balance * portion
        size = (available * leverage) / exec_price

        if size <= 0:
            return None

        # Calculate entry fee
        notional = size * exec_price
        fee = self.calculate_fee(notional)

        # Get TP/SL prices
        tp_price = getattr(decision, 'take_profit_price', None)
        sl_price = getattr(decision, 'stop_loss_price', None)

        # Open position (no longer pass TP/SL to position itself)
        account.open_position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=exec_price,
            leverage=leverage,
            timestamp=timestamp,
            fee=fee,
        )

        # Create independent TP/SL orders for this position
        close_side = "sell" if side == "long" else "buy"
        if tp_price:
            account.add_pending_order(
                symbol=symbol,
                side=close_side,
                order_type="take_profit",
                trigger_price=tp_price,
                size=size,
                entry_price=exec_price,
                timestamp=timestamp,
            )
        if sl_price:
            account.add_pending_order(
                symbol=symbol,
                side=close_side,
                order_type="stop_loss",
                trigger_price=sl_price,
                size=size,
                entry_price=exec_price,
                timestamp=timestamp,
            )

        return BacktestTradeRecord(
            timestamp=timestamp,
            trigger_type=trigger_type,
            symbol=symbol,
            operation=operation,
            side=side,
            entry_price=exec_price,
            size=size,
            leverage=leverage,
            fee=fee,
            reason=getattr(decision, 'reason', ''),
            pool_name=pool_name,
            triggered_signals=triggered_signals or [],
        )

    def _execute_close(
        self,
        account: VirtualAccount,
        symbol: str,
        current_price: float,
        timestamp: int,
        trigger_type: str,
        pool_name: Optional[str],
        triggered_signals: Optional[List[str]],
        reason: str = "",
    ) -> Optional[BacktestTradeRecord]:
        """
        Execute position close.
        
        执行平仓操作。
        """
        pos = account.get_position(symbol)
        if not pos:
            return None

        # Calculate execution price with slippage
        close_side = "sell" if pos.side == "long" else "buy"
        exec_price, _ = self.calculate_execution_price(current_price, close_side)

        # Calculate fee
        notional = pos.size * exec_price
        fee = self.calculate_fee(notional)

        # Store position info before closing
        entry_price = pos.entry_price
        size = pos.size
        leverage = pos.leverage
        side = pos.side
        entry_ts = pos.entry_timestamp

        # Close position
        pnl = account.close_position(symbol, exec_price, fee)

        # Calculate PnL percent
        entry_notional = size * entry_price
        pnl_percent = (pnl / entry_notional * 100) if entry_notional > 0 else 0

        return BacktestTradeRecord(
            timestamp=entry_ts,
            trigger_type=trigger_type,
            symbol=symbol,
            operation="close",
            side=side,
            entry_price=entry_price,
            size=size,
            leverage=leverage,
            exit_price=exec_price,
            exit_timestamp=timestamp,
            exit_reason="decision",
            pnl=pnl,
            pnl_percent=pnl_percent,
            fee=fee,
            reason=reason,
            pool_name=pool_name,
            triggered_signals=triggered_signals or [],
        )

