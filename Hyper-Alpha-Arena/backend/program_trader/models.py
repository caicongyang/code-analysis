"""
Core data models for Program Trader.
Defines Strategy template, MarketData input, and Decision output structures.
"""
"""
程序交易者核心数据模型

定义了程序交易系统中的关键数据结构：
- 策略模板：用户编写策略的标准接口
- 市场数据输入：策略执行时可用的市场信息
- 决策输出：策略生成的交易指令

这些模型确保了策略代码与交易引擎之间的标准化通信，
支持回测和实盘交易的一致性体验。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from abc import ABC, abstractmethod
from enum import Enum


class ActionType(str, Enum):
    """Trading action types."""
    """
    交易操作类型枚举

    定义程序交易者可执行的所有交易操作类型：
    - BUY: 买入操作，建立多头仓位
    - SELL: 卖出操作，建立空头仓位
    - CLOSE: 平仓操作，关闭现有仓位
    - HOLD: 持有操作，不执行任何交易

    这个枚举确保了策略代码中交易指令的标准化和类型安全。
    """
    BUY = "buy"      # 买入，开多仓
    SELL = "sell"    # 卖出，开空仓
    CLOSE = "close"  # 平仓，关闭现有仓位
    HOLD = "hold"    # 持有，不采取行动


@dataclass
class Kline:
    """K-line (candlestick) data."""
    """
    K线（蜡烛图）数据结构

    K线是技术分析中最基础的价格数据表示形式，包含了某个时间段内
    的开盘价、最高价、最低价、收盘价和成交量信息。

    字段说明：
    - timestamp: Unix时间戳（秒），标识K线的时间点
    - open: 开盘价，该时间段的第一个交易价格
    - high: 最高价，该时间段的最高交易价格
    - low: 最低价，该时间段的最低交易价格
    - close: 收盘价，该时间段的最后交易价格
    - volume: 成交量，该时间段的总交易数量

    用途：
    - 技术指标计算（如移动平均、RSI等）
    - 价格走势分析
    - 支撑阻力位识别
    - 交易信号生成
    """
    timestamp: int    # 时间戳（Unix秒数）
    open: float      # 开盘价
    high: float      # 最高价
    low: float       # 最低价
    close: float     # 收盘价
    volume: float    # 成交量


@dataclass
class Position:
    """Current position information."""
    """
    当前持仓信息

    描述交易者在特定标的上的持仓状态，包含仓位方向、规模、
    成本价格、未实现盈亏等关键信息。这些数据是风险管理和
    交易决策的重要依据。

    字段详解：
    - symbol: 交易标的符号（如"BTC"、"ETH"）
    - side: 仓位方向，"long"表示多头，"short"表示空头
    - size: 仓位大小，正数表示持仓数量
    - entry_price: 平均开仓价格，用于计算盈亏
    - unrealized_pnl: 未实现盈亏（美元），当前价格与开仓价的差额
    - leverage: 使用的杠杆倍数（1-50倍）
    - liquidation_price: 强制平仓价格，价格触及此水平时仓位被强平

    风险管理用途：
    - 计算仓位价值和风险敞口
    - 设定止损止盈价格
    - 监控强平风险
    - 评估投资组合风险
    """
    symbol: str              # 交易标的符号
    side: str               # 仓位方向："long"多头 或 "short"空头
    size: float             # 仓位大小
    entry_price: float      # 平均开仓价格
    unrealized_pnl: float   # 未实现盈亏（USD）
    leverage: int           # 杠杆倍数
    liquidation_price: float  # 强制平仓价格


@dataclass
class Trade:
    """Historical trade record."""
    """
    历史交易记录

    记录已完成的交易信息，用于性能分析和策略评估。
    每条记录代表一次完整的开仓到平仓过程。

    字段说明：
    - symbol: 交易标的符号
    - side: 交易方向，"Long"表示多头交易，"Short"表示空头交易
    - size: 交易数量
    - price: 平仓价格
    - timestamp: 平仓时间戳（毫秒）
    - pnl: 已实现盈亏（考虑手续费后的净收益）
    - close_time: 平仓时间的可读格式（UTC时间字符串）

    用途：
    - 计算交易统计（胜率、盈亏比等）
    - 生成交易报告
    - 策略性能评估
    - 风险分析
    """
    symbol: str              # 交易标的
    side: str               # 交易方向："Long"多头 或 "Short"空头
    size: float             # 交易数量
    price: float            # 平仓价格
    timestamp: int          # 平仓时间戳（毫秒）
    pnl: float             # 已实现盈亏
    close_time: str = ""   # 平仓时间（UTC字符串格式）


@dataclass
class Order:
    """Open order information."""
    """
    开放订单信息

    描述当前挂单的详细信息，包括限价单、止损单、止盈单等类型。
    这些订单会在特定条件下自动执行。

    字段详解：
    - order_id: 订单唯一标识符，用于查询和撤销
    - symbol: 交易标的符号
    - side: 订单方向，"Buy"买入或"Sell"卖出
    - direction: 具体操作类型，如"Open Long"开多、"Close Short"平空
    - order_type: 订单类型
      * "Limit": 限价单，指定价格执行
      * "Stop Limit": 止损限价单，价格突破后按限价执行
      * "Take Profit Limit": 止盈限价单，达到盈利目标后执行
    - size: 订单数量
    - price: 限价价格
    - trigger_price: 触发价格（用于止损止盈单）
    - reduce_only: 是否仅减仓，true表示只能减少现有仓位
    - timestamp: 订单创建时间戳（毫秒）

    订单管理用途：
    - 自动化交易执行
    - 风险控制（止损止盈）
    - 订单状态跟踪
    - 交易策略实现
    """
    order_id: int                        # 订单ID
    symbol: str                          # 交易标的
    side: str                           # 订单方向："Buy"买入 或 "Sell"卖出
    direction: str                      # 操作类型："Open Long"开多等
    order_type: str                     # 订单类型："Limit"限价单等
    size: float                         # 订单数量
    price: float                        # 限价价格
    trigger_price: Optional[float] = None  # 触发价格（止损止盈用）
    reduce_only: bool = False           # 是否仅减仓
    timestamp: int = 0                  # 创建时间戳（毫秒）


@dataclass
class RegimeInfo:
    """Market regime classification result.

    Attributes:
        regime: Market regime type (breakout/absorption/stop_hunt/exhaustion/trap/continuation/noise)
        conf: Confidence score 0.0-1.0
        direction: Market direction (bullish/bearish/neutral)
        reason: Human-readable explanation of the regime classification
        indicators: Dict of indicator values used for classification
            - cvd_ratio: CVD / total notional
    """
    """
    市场制度分类结果

    基于多维市场数据分析，将当前市场状态分类为7种制度类型之一。
    这种分类帮助交易者理解市场微观结构，优化交易时机选择。

    制度类型详解：
    - breakout: 突破行情，强方向性移动伴随成交量确认
    - absorption: 吸收行情，大单被吸收而价格影响有限，潜在反转信号
    - stop_hunt: 猎杀止损，价格突破区间后快速反转，流动性猎杀行为
    - exhaustion: 趋势疲竭，极值RSI配合CVD背离，趋势力量减弱
    - trap: 陷阱行情，价格突破但CVD/OI背离，虚假突破
    - continuation: 趋势延续，各指标协调一致，趋势持续信号
    - noise: 噪音行情，无明确方向，低置信度

    字段说明：
    - regime: 市场制度类型（7种之一）
    - conf: 分类置信度（0.0-1.0），越高表示分类越可靠
    - direction: 市场方向偏向（bullish/bearish/neutral）
    - reason: 分类理由的人类可读解释
    - indicators: 用于分类的技术指标数值
      * cvd_ratio: CVD与总成交额比值，衡量买卖压力
      * oi_delta: 持仓量变化百分比
      * taker_ratio: 主动买卖比率
      * price_atr: 价格变化与ATR比值
      * rsi: 相对强弱指标

    应用价值：
    - 优化交易入场时机
    - 调整仓位管理策略
    - 识别市场转折点
    - 提高胜率和盈亏比
    """
            - oi_delta: Open interest change %
            - taker_ratio: Taker buy/sell ratio
            - price_atr: Price change / ATR
            - rsi: RSI(14) value
    """
    regime: str
    conf: float
    direction: str = "neutral"
    reason: str = ""
    indicators: Dict[str, float] = field(default_factory=dict)


@dataclass
class Decision:
    """
    Strategy decision output - aligned with AI Trader output_format.

    Required fields:
    - operation: "buy" | "sell" | "hold" | "close"
    - symbol: Trading symbol (e.g., "BTC")
    - reason: Explanation of the decision
    - trading_strategy: Entry thesis, risk controls, exit plan

    Required for buy/sell/close:
    - target_portion_of_balance: float 0.1-1.0
    - leverage: int 1-50
    - max_price: required for "buy" or closing SHORT
    - min_price: required for "sell" or closing LONG

    Optional with defaults:
    - time_in_force: "Ioc" | "Gtc" | "Alo" (default: "Ioc")
    - take_profit_price: trigger price for profit taking
    - stop_loss_price: trigger price for loss protection
    - tp_execution: "market" | "limit" (default: "limit")
    - sl_execution: "market" | "limit" (default: "limit")
    """
    # Always required
    operation: str  # "buy" | "sell" | "hold" | "close"
    symbol: str
    reason: str = ""
    trading_strategy: str = ""

    # Required for buy/sell/close
    target_portion_of_balance: float = 0.0  # 0.1-1.0
    leverage: int = 10  # 1-50
    max_price: Optional[float] = None  # required for buy / close short
    min_price: Optional[float] = None  # required for sell / close long

    # Optional with defaults
    time_in_force: str = "Ioc"  # "Ioc" | "Gtc" | "Alo"
    take_profit_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    tp_execution: str = "limit"  # "market" | "limit"
    sl_execution: str = "limit"  # "market" | "limit"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "symbol": self.symbol,
            "target_portion_of_balance": self.target_portion_of_balance,
            "leverage": self.leverage,
            "max_price": self.max_price,
            "min_price": self.min_price,
            "time_in_force": self.time_in_force,
            "take_profit_price": self.take_profit_price,
            "stop_loss_price": self.stop_loss_price,
            "tp_execution": self.tp_execution,
            "sl_execution": self.sl_execution,
            "reason": self.reason,
            "trading_strategy": self.trading_strategy,
        }


# Keep ActionType for backward compatibility (used in existing code)
# New code should use Decision.operation string directly


@dataclass
class MarketData:
    """
    Input data structure passed to strategy scripts.
    Provides access to account info, positions, and market data.

    Fields are aligned with AI Trader's prompt context variables to ensure
    Programs have access to the same information as AI Trader.
    """
    # Account info
    available_balance: float = 0.0
    total_equity: float = 0.0
    used_margin: float = 0.0
    margin_usage_percent: float = 0.0
    maintenance_margin: float = 0.0

    # Positions and trades
    positions: Dict[str, Position] = field(default_factory=dict)
    recent_trades: List[Trade] = field(default_factory=list)
    open_orders: List[Order] = field(default_factory=list)

    # Trigger info (basic)
    trigger_symbol: str = ""  # Symbol that triggered (empty string for scheduled triggers)
    trigger_type: str = "signal"  # "signal" or "scheduled"

    # Trigger context (detailed) - matches AI Trader's {trigger_context} variable
    signal_pool_name: str = ""  # Name of the signal pool that triggered
    pool_logic: str = "OR"  # "OR" or "AND" - how signals are combined
    triggered_signals: List[Dict] = field(default_factory=list)  # Full signal details

    # Trigger market regime snapshot - matches AI Trader's {trigger_market_regime}
    trigger_market_regime: Optional[RegimeInfo] = None  # Market regime at trigger time

    # Environment info - matches AI Trader's environment variables
    environment: str = "mainnet"  # "mainnet" or "testnet"
    max_leverage: int = 10  # Maximum allowed leverage
    default_leverage: int = 3  # Default leverage setting

    # Data provider (injected at runtime)
    _data_provider: Any = field(default=None, repr=False)

    def get_price(self, symbol: str) -> float:
        """Get current price for symbol."""
        if self._data_provider:
            # Try get_current_prices first (for backtest)
            if hasattr(self._data_provider, 'get_current_prices'):
                prices = self._data_provider.get_current_prices([symbol])
                if prices and symbol in prices:
                    return prices[symbol]
            # Fallback to get_market_data
            data = self._data_provider.get_market_data(symbol)
            if data and 'price' in data:
                return data['price']
        return 0.0

    def get_price_change(self, symbol: str, period: str) -> Dict[str, float]:
        """Get price change for symbol over period."""
        if self._data_provider:
            return self._data_provider.get_price_change(symbol, period)
        return {"change_percent": 0.0, "change_usd": 0.0}

    def get_klines(self, symbol: str, period: str, count: int = 50) -> List[Kline]:
        """Get K-line data."""
        if self._data_provider:
            return self._data_provider.get_klines(symbol, period, count)
        return []

    def get_indicator(self, symbol: str, indicator: str, period: str) -> Dict[str, Any]:
        """Get technical indicator values."""
        if self._data_provider:
            return self._data_provider.get_indicator(symbol, indicator, period)
        return {}

    def get_flow(self, symbol: str, metric: str, period: str) -> Dict[str, Any]:
        """Get market flow metrics."""
        if self._data_provider:
            return self._data_provider.get_flow(symbol, metric, period)
        return {}

    def get_regime(self, symbol: str, period: str) -> RegimeInfo:
        """Get market regime classification."""
        if self._data_provider:
            return self._data_provider.get_regime(symbol, period)
        return RegimeInfo(regime="noise", conf=0.0)

    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """Get complete market data (price, volume, OI, funding rate).

        Returns dict with fields: symbol, price, oracle_price, change24h,
        percentage24h, volume24h, open_interest, funding_rate.
        """
        if self._data_provider:
            return self._data_provider.get_market_data(symbol)
        return {}


class Strategy(ABC):
    """
    Base class for all trading strategies.
    AI generates code that extends this class.
    """

    def __init__(self):
        self.params: Dict[str, Any] = {}

    def init(self, params: Dict[str, Any]) -> None:
        """
        Initialize strategy parameters.
        Override this method to set up strategy-specific parameters.
        """
        self.params = params

    @abstractmethod
    def should_trade(self, data: MarketData) -> Decision:
        """
        Main decision logic. Called each time signal triggers.

        Args:
            data: MarketData object with all market info

        Returns:
            Decision object with action and parameters
        """
        pass
