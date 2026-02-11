"""
虚拟账户模块 (Virtual Account for Backtest)

管理回测过程中的虚拟账户状态，包括：
- 余额和权益追踪：跟踪账户余额、权益、已实现盈亏、未实现盈亏和手续费
- 持仓管理：开仓、平仓、加仓、部分平仓等操作
- 挂单管理：止盈止损订单的创建、触发和移除

账户权益计算方式（匹配Hyperliquid的Account Value风格）：
equity = initial_balance + realized_pnl_total + unrealized_pnl - total_fees

这种方式确保保证金被锁定但不减少权益，只有实际的盈亏和手续费影响权益。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from copy import deepcopy


@dataclass
class VirtualPosition:
    """
    虚拟持仓类 (Virtual Position)
    
    表示回测过程中的一个持仓，包含持仓的所有关键信息。
    注意：TP/SL现在通过独立的VirtualOrder管理，不再存储在持仓中。
    """
    symbol: str                            # 交易标的
    side: str                              # 持仓方向："long"（做多）或 "short"（做空）
    size: float                            # 持仓数量（标的单位，如BTC数量）
    entry_price: float                     # 开仓价格（加权平均价格，如果多次加仓）
    leverage: int = 1                      # 杠杆倍数
    entry_timestamp: int = 0               # 开仓时间戳（毫秒）

    # TP/SL设置（已废弃，现在通过VirtualOrder管理）
    take_profit_price: Optional[float] = None  # 止盈价格（已废弃）
    stop_loss_price: Optional[float] = None    # 止损价格（已废弃）

    # 追踪信息
    unrealized_pnl: float = 0.0           # 未实现盈亏（美元）
    margin_used: float = 0.0               # 已使用保证金（美元）

    def update_pnl(self, current_price: float) -> float:
        """
        更新并返回未实现盈亏
        
        Args:
            current_price: 当前市场价格
            
        Returns:
            未实现盈亏金额（美元）
        """
        if self.side == "long":
            # 做多：盈亏 = (当前价格 - 开仓价格) * 持仓数量
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:
            # 做空：盈亏 = (开仓价格 - 当前价格) * 持仓数量
            self.unrealized_pnl = (self.entry_price - current_price) * self.size
        return self.unrealized_pnl

    def get_notional_value(self, current_price: float) -> float:
        """
        获取持仓的名义价值（持仓数量 * 当前价格）
        
        Args:
            current_price: 当前市场价格
            
        Returns:
            名义价值（美元）
        """
        return self.size * current_price


@dataclass
class VirtualOrder:
    """
    虚拟挂单类 (Virtual Pending Order)
    
    表示一个止盈或止损挂单。每个订单都是独立的（类似Hyperliquid），
    当触发时只平掉该订单控制的持仓部分，不影响其他订单。
    
    这种设计允许：
    - 多次开仓时，每次开仓可以设置独立的TP/SL
    - 部分平仓时，只移除对应的订单
    - 更精确地追踪每笔交易的盈亏
    """
    order_id: int                          # 订单唯一ID
    symbol: str                            # 交易标的
    side: str                              # 平仓方向："buy"（平空）或 "sell"（平多）
    order_type: str                        # 订单类型："take_profit"（止盈）或 "stop_loss"（止损）
    trigger_price: float                   # 触发价格
    size: float                            # 该订单控制的持仓数量（独立于其他订单）
    entry_price: float = 0.0               # 创建订单时的开仓价格（用于准确计算盈亏）
    reduce_only: bool = True               # 是否只减仓（始终为True）
    created_at: int = 0                    # 订单创建时间戳（毫秒）


class VirtualAccount:
    """
    Virtual account state manager for backtesting.

    Tracks balance, positions, and pending orders throughout
    the backtest simulation.

    Equity calculation (Account Value style):
    equity = initial_balance + realized_pnl_total + unrealized_pnl - total_fees

    This matches how Hyperliquid displays Account Value - margin is locked
    but doesn't reduce equity, only actual PnL and fees affect equity.

    虚拟账户状态管理器，用于回测过程中的账户状态管理。

    在整个回测模拟过程中跟踪余额、持仓和挂单。

    权益计算方式（账户价值风格）：
    equity = initial_balance + realized_pnl_total + unrealized_pnl - total_fees

    这与Hyperliquid显示账户价值的方式一致 - 保证金被锁定但不减少权益，
    只有实际的盈亏和手续费影响权益。
    """

    def __init__(self, initial_balance: float = 10000.0):
        """
        初始化虚拟账户
        
        Args:
            initial_balance: 初始账户余额（美元）
        """
        self.initial_balance = initial_balance
        self.balance = initial_balance     # Available balance (for margin calculation) 可用余额（用于保证金计算）
        self.equity = initial_balance      # Account Value 账户价值
        self.positions: Dict[str, VirtualPosition] = {}  # 持仓字典 {标的: 持仓对象}
        self.pending_orders: List[VirtualOrder] = []     # 挂单列表
        self._order_id_counter = 0          # 订单ID计数器

        # PnL tracking (Account Value style) 盈亏追踪（账户价值风格）
        self.realized_pnl_total = 0.0      # Cumulative realized PnL 累计已实现盈亏
        self.unrealized_pnl_total = 0.0    # Current unrealized PnL 当前未实现盈亏
        self.total_fees = 0.0              # Cumulative fees paid 累计支付的手续费

        # Drawdown tracking 回撤追踪
        self.peak_equity = initial_balance  # 峰值权益
        self.max_drawdown = 0.0            # 最大回撤金额
        self.max_drawdown_percent = 0.0    # 最大回撤百分比

    def reset(self):
        """
        Reset account to initial state.
        
        重置账户到初始状态，清空所有持仓、挂单和统计数据。
        """
        self.balance = self.initial_balance
        self.equity = self.initial_balance
        self.positions = {}
        self.pending_orders = []
        self._order_id_counter = 0
        self.realized_pnl_total = 0.0
        self.unrealized_pnl_total = 0.0
        self.total_fees = 0.0
        self.peak_equity = self.initial_balance
        self.max_drawdown = 0.0
        self.max_drawdown_percent = 0.0

    def update_equity(self, prices: Dict[str, float]):
        """
        Update equity based on current prices (Account Value style).
        
        根据当前价格更新账户权益（账户价值风格）。
        
        Args:
            prices: 当前价格字典 {标的: 价格}
        """
        self.unrealized_pnl_total = 0.0
        for symbol, pos in self.positions.items():
            if symbol in prices:
                self.unrealized_pnl_total += pos.update_pnl(prices[symbol])

        # Account Value = initial + realized + unrealized - fees
        # 账户价值 = 初始余额 + 已实现盈亏 + 未实现盈亏 - 手续费
        self.equity = self.initial_balance + self.realized_pnl_total + self.unrealized_pnl_total - self.total_fees

        # Track drawdown 追踪回撤
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        if self.peak_equity > 0:
            current_drawdown = self.peak_equity - self.equity
            current_drawdown_pct = current_drawdown / self.peak_equity
            if current_drawdown > self.max_drawdown:
                self.max_drawdown = current_drawdown
                self.max_drawdown_percent = current_drawdown_pct

    def open_position(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        leverage: int = 1,
        timestamp: int = 0,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        fee: float = 0.0,
    ) -> VirtualPosition:
        """
        Open a new position.
        
        开立新持仓。
        
        Args:
            symbol: 交易标的
            side: 持仓方向 "long"（做多）或 "short"（做空）
            size: 持仓数量（标的单位）
            entry_price: 开仓价格
            leverage: 杠杆倍数
            timestamp: 开仓时间戳（毫秒）
            take_profit: 止盈价格（已废弃，现在通过VirtualOrder管理）
            stop_loss: 止损价格（已废弃，现在通过VirtualOrder管理）
            fee: 开仓手续费
            
        Returns:
            创建的VirtualPosition对象
        """
        # Calculate margin required 计算所需保证金
        notional = size * entry_price  # 名义价值 = 数量 * 价格
        margin_required = notional / leverage  # 所需保证金 = 名义价值 / 杠杆

        position = VirtualPosition(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            leverage=leverage,
            entry_timestamp=timestamp,
            take_profit_price=take_profit,
            stop_loss_price=stop_loss,
            margin_used=margin_required,
        )

        self.positions[symbol] = position
        self.balance -= margin_required

        # Track fee (affects equity via total_fees)
        self.total_fees += fee

        return position

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        fee: float = 0.0,
    ) -> Optional[float]:
        """
        Close position and return realized PnL (before fee deduction).
        
        平仓并返回已实现盈亏（扣除手续费前）。
        
        Args:
            symbol: 交易标的
            exit_price: 平仓价格
            fee: 平仓手续费
            
        Returns:
            已实现盈亏金额（扣除手续费前），如果标的无持仓则返回None
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        pos.update_pnl(exit_price)
        realized_pnl = pos.unrealized_pnl  # PnL before fee 手续费前的盈亏

        # Update cumulative tracking 更新累计追踪
        self.realized_pnl_total += realized_pnl
        self.total_fees += fee

        # Return margin to available balance 将保证金返还到可用余额
        self.balance += pos.margin_used

        # Remove position and related orders 移除持仓和相关订单
        del self.positions[symbol]
        self.pending_orders = [o for o in self.pending_orders if o.symbol != symbol]

        return realized_pnl

    def add_to_position(
        self,
        symbol: str,
        size: float,
        entry_price: float,
        fee: float = 0.0,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
    ) -> Optional[VirtualPosition]:
        """
        Add to existing position (averaging entry price).

        Returns updated position or None if no existing position.
        
        向现有持仓加仓（加权平均开仓价格）。
        
        Args:
            symbol: 交易标的
            size: 加仓数量
            entry_price: 加仓价格
            fee: 加仓手续费
            take_profit: 止盈价格（已废弃）
            stop_loss: 止损价格（已废弃）
            
        Returns:
            更新后的持仓对象，如果标的无持仓则返回None
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Calculate weighted average entry price
        old_notional = pos.size * pos.entry_price
        new_notional = size * entry_price
        total_size = pos.size + size
        avg_entry_price = (old_notional + new_notional) / total_size

        # Calculate additional margin required
        additional_margin = (size * entry_price) / pos.leverage

        # Update position
        pos.size = total_size
        pos.entry_price = avg_entry_price
        pos.margin_used += additional_margin

        # Update TP/SL if provided (override old values)
        if take_profit is not None:
            pos.take_profit_price = take_profit
        if stop_loss is not None:
            pos.stop_loss_price = stop_loss

        # Update balance and fees
        self.balance -= additional_margin
        self.total_fees += fee

        return pos

    def has_position(self, symbol: str) -> bool:
        """
        Check if position exists for symbol.
        
        检查指定标的是否存在持仓。
        
        Args:
            symbol: 交易标的
            
        Returns:
            如果存在持仓返回True，否则返回False
        """
        return symbol in self.positions

    def get_position(self, symbol: str) -> Optional[VirtualPosition]:
        """
        Get position for symbol.
        
        获取指定标的的持仓对象。
        
        Args:
            symbol: 交易标的
            
        Returns:
            持仓对象，如果不存在则返回None
        """
        return self.positions.get(symbol)

    def add_pending_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        trigger_price: float,
        size: float,
        entry_price: float = 0.0,
        timestamp: int = 0,
    ) -> VirtualOrder:
        """
        Add a pending order (TP/SL) - each order is independent.
        
        添加挂单（止盈/止损）- 每个订单都是独立的。
        
        Args:
            symbol: 交易标的
            side: 平仓方向 "buy"（平空）或 "sell"（平多）
            order_type: 订单类型 "take_profit"（止盈）或 "stop_loss"（止损）
            trigger_price: 触发价格
            size: 订单控制的持仓数量
            entry_price: 开仓价格（用于准确计算盈亏）
            timestamp: 订单创建时间戳（毫秒）
            
        Returns:
            创建的VirtualOrder对象
        """
        self._order_id_counter += 1
        order = VirtualOrder(
            order_id=self._order_id_counter,
            symbol=symbol,
            side=side,
            order_type=order_type,
            trigger_price=trigger_price,
            size=size,
            entry_price=entry_price,
            created_at=timestamp,
        )
        self.pending_orders.append(order)
        return order

    def remove_pending_order(self, order_id: int):
        """
        Remove a pending order by ID.
        
        根据订单ID移除挂单。
        
        Args:
            order_id: 订单ID
        """
        self.pending_orders = [o for o in self.pending_orders if o.order_id != order_id]

    def partial_close_position(
        self,
        symbol: str,
        size: float,
        exit_price: float,
        fee: float = 0.0,
        entry_price: float = 0.0,
    ) -> Optional[float]:
        """
        Partially close a position and return realized PnL for the closed portion.

        部分平仓并返回已平仓部分的已实现盈亏。
        
        用于止盈止损订单的部分平仓，每个订单独立控制一部分持仓。

        Args:
            symbol: 交易标的
            size: 要平仓的数量（必须 <= 持仓数量）
            exit_price: 平仓价格
            fee: 交易手续费
            entry_price: 该部分的开仓价格（用于准确计算盈亏，如果为0则使用持仓的平均开仓价）

        Returns:
            已平仓部分的已实现盈亏，如果标的无持仓则返回None
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Ensure we don't close more than we have 确保不会平仓超过持仓数量
        close_size = min(size, pos.size)
        if close_size <= 0:
            return None

        # Calculate PnL for this portion using the specific entry price
        # 使用特定的开仓价格计算该部分的盈亏
        actual_entry = entry_price if entry_price > 0 else pos.entry_price
        if pos.side == "long":
            realized_pnl = (exit_price - actual_entry) * close_size
        else:
            realized_pnl = (actual_entry - exit_price) * close_size

        # Update cumulative tracking 更新累计追踪
        self.realized_pnl_total += realized_pnl
        self.total_fees += fee

        # Calculate margin to return (proportional to size closed)
        # 计算要返还的保证金（按平仓比例）
        margin_to_return = (close_size / pos.size) * pos.margin_used

        # Update position 更新持仓
        remaining_size = pos.size - close_size
        if remaining_size <= 0.0001:  # Effectively zero, close entire position 接近零，完全平仓
            self.balance += pos.margin_used
            del self.positions[symbol]
            # Remove all pending orders for this symbol 移除该标的的所有挂单
            self.pending_orders = [o for o in self.pending_orders if o.symbol != symbol]
        else:
            # Update position with remaining size 更新剩余持仓
            pos.margin_used -= margin_to_return
            pos.size = remaining_size
            self.balance += margin_to_return

        return realized_pnl

    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        Get current account state as dict.
        
        获取当前账户状态的字典快照。
        
        Returns:
            包含账户余额、权益、持仓、挂单数量和回撤信息的字典
        """
        return {
            "balance": self.balance,
            "equity": self.equity,
            "positions": {
                s: {
                    "side": p.side,
                    "size": p.size,
                    "entry_price": p.entry_price,
                    "unrealized_pnl": p.unrealized_pnl,
                }
                for s, p in self.positions.items()
            },
            "pending_orders": len(self.pending_orders),
            "max_drawdown": self.max_drawdown,
            "max_drawdown_percent": self.max_drawdown_percent,
        }

