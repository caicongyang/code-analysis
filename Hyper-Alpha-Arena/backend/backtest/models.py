"""
回测数据模型 (Backtest Data Models)

定义回测引擎使用的核心数据结构，包括配置、事件、交易记录和结果统计。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional


@dataclass
class BacktestConfig:
    """
    回测配置类 (Backtest Configuration)
    
    包含回测所需的所有配置参数，用于初始化回测引擎和模拟交易环境。
    """
    code: str                              # 策略代码，Python类定义字符串
    signal_pool_ids: List[int]             # 使用的信号池ID列表，用于生成信号触发事件
    symbols: List[str]                     # 交易标的列表，例如 ["BTC", "ETH"]
    start_time_ms: int                     # 回测开始时间（UTC毫秒时间戳）
    end_time_ms: int                       # 回测结束时间（UTC毫秒时间戳）

    # 定时触发配置（可选）
    scheduled_interval: Optional[str] = None  # 定时触发间隔："1h", "4h", "1d", None表示不启用

    # 资金和风险设置
    initial_balance: float = 10000.0       # 初始账户余额（美元）
    slippage_percent: float = 0.05         # 默认滑点百分比（0.05%），买入时价格上浮，卖出时价格下浮
    fee_rate: float = 0.035                # 交易手续费率（0.035%），Hyperliquid的taker费率

    # 执行假设
    execution_price: str = "close"         # 执行价格类型："close"（收盘价）、"open"（开盘价）、"vwap"（成交量加权平均价）

    @property
    def start_time(self) -> datetime:
        """将开始时间转换为datetime对象（UTC时区）"""
        return datetime.utcfromtimestamp(self.start_time_ms / 1000)

    @property
    def end_time(self) -> datetime:
        """将结束时间转换为datetime对象（UTC时区）"""
        return datetime.utcfromtimestamp(self.end_time_ms / 1000)


@dataclass
class TriggerEvent:
    """
    统一的触发事件类 (Unified Trigger Event)
    
    表示回测过程中的一个触发事件，可以是信号触发或定时触发。
    每个触发事件都会执行一次策略代码，生成交易决策。
    """
    timestamp: int                         # 触发时间戳（毫秒）
    trigger_type: str                      # 触发类型："signal"（信号触发）或 "scheduled"（定时触发）
    symbol: str                            # 触发标的（定时触发时为空字符串）

    # 信号触发专用字段
    pool_id: Optional[int] = None          # 信号池ID
    pool_name: Optional[str] = None        # 信号池名称
    pool_logic: Optional[str] = None       # 信号池逻辑："AND"（所有信号）或 "OR"（任一信号）
    triggered_signals: Optional[List[Dict[str, Any]]] = None  # 触发的信号详情列表，包含信号名称、指标值等
    market_regime: Optional[Dict[str, Any]] = None  # 触发时的市场状态（突破/吸收/陷阱等）

    def __post_init__(self):
        if self.triggered_signals is None:
            self.triggered_signals = []


@dataclass
class BacktestTradeRecord:
    """
    回测交易记录类 (Backtest Trade Record)
    
    记录回测过程中的每一笔交易，包括开仓、加仓、平仓等操作。
    用于统计回测结果和生成交易历史。
    """
    timestamp: int                         # 交易时间戳（毫秒），开仓时间
    trigger_type: str                      # 触发类型："signal"（信号触发）或 "scheduled"（定时触发）
    symbol: str                            # 交易标的
    operation: str                         # 操作类型："buy"（买入）、"sell"（卖出）、"close"（平仓）、"add_position"（加仓）
    side: str                              # 持仓方向："long"（做多）或 "short"（做空）
    entry_price: float                     # 开仓价格
    size: float                            # 交易数量（标的单位）
    leverage: int = 1                      # 杠杆倍数

    # 平仓信息（仅在平仓时填充）
    exit_price: Optional[float] = None    # 平仓价格
    exit_timestamp: Optional[int] = None   # 平仓时间戳（毫秒）
    exit_reason: Optional[str] = None     # 平仓原因："decision"（策略决策）、"tp"（止盈）、"sl"（止损）、"liquidation"（强平）

    # 盈亏信息（仅在平仓时填充）
    pnl: float = 0.0                       # 盈亏金额（美元）
    pnl_percent: float = 0.0                # 盈亏百分比
    fee: float = 0.0                       # 手续费（美元）

    # 交易后账户权益（用于止盈止损追踪）
    equity_after: float = 0.0              # 交易完成后的账户权益

    # 交易上下文信息
    reason: str = ""                       # 策略决策原因说明
    pool_name: Optional[str] = None        # 信号池名称（如果是信号触发）
    triggered_signals: Optional[List[str]] = None  # 触发的信号名称列表

    def __post_init__(self):
        if self.triggered_signals is None:
            self.triggered_signals = []


@dataclass
class TriggerExecutionResult:
    """
    触发执行结果类 (Trigger Execution Result)
    
    记录单个触发事件的执行结果，包括策略执行、交易生成和账户状态变化。
    用于流式回测和详细日志记录。
    """
    trigger: TriggerEvent                   # 触发事件对象
    trigger_symbol: str                    # 触发标的
    prices: Dict[str, float]               # 当前所有标的的价格字典

    # 策略执行结果
    executor_result: Any                   # SandboxExecutor的执行结果，包含决策和错误信息
    trade: Optional[BacktestTradeRecord]   # 本次触发产生的交易记录（如果有）
    tp_sl_trades: List[BacktestTradeRecord]  # 本次触发触发的止盈止损交易列表

    # 账户状态
    equity_before: float                   # 执行前的账户权益
    equity_after: float                    # 执行后的账户权益
    equity_after_tp_sl: float = 0.0        # 止盈止损执行后、策略执行前的账户权益
    unrealized_pnl: float = 0.0            # 当前未实现盈亏总额

    # 数据查询记录（用于调试和日志）
    data_queries: List[Dict[str, Any]] = field(default_factory=list)  # 策略执行期间的数据查询记录


@dataclass
class BacktestResult:
    """
    回测结果类 (Backtest Result)
    
    包含回测执行的所有统计数据和详细记录，用于评估策略表现。
    """
    success: bool                          # 回测是否成功执行
    error: Optional[str] = None            # 错误信息（如果失败）

    # 核心指标
    total_pnl: float = 0.0                 # 总盈亏金额（美元）
    total_pnl_percent: float = 0.0         # 总盈亏百分比
    max_drawdown: float = 0.0              # 最大回撤金额（美元）
    max_drawdown_percent: float = 0.0      # 最大回撤百分比
    sharpe_ratio: float = 0.0              # 夏普比率（年化）

    # 交易统计
    total_trades: int = 0                  # 总交易次数（已平仓）
    winning_trades: int = 0                # 盈利交易次数
    losing_trades: int = 0                 # 亏损交易次数
    win_rate: float = 0.0                 # 胜率（百分比）
    profit_factor: float = 0.0             # 盈亏比（总盈利 / 总亏损）
    avg_win: float = 0.0                   # 平均盈利金额
    avg_loss: float = 0.0                  # 平均亏损金额
    largest_win: float = 0.0               # 最大单笔盈利
    largest_loss: float = 0.0              # 最大单笔亏损

    # 触发统计
    total_triggers: int = 0                # 总触发次数
    signal_triggers: int = 0               # 信号触发次数
    scheduled_triggers: int = 0             # 定时触发次数

    # 详细数据
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)  # 权益曲线数据，每个触发点的权益变化
    trades: List[BacktestTradeRecord] = field(default_factory=list)     # 所有交易记录列表
    trigger_log: List[TriggerEvent] = field(default_factory=list)       # 所有触发事件日志

    # 执行信息
    execution_time_ms: float = 0.0        # 回测执行耗时（毫秒）
    start_time: Optional[datetime] = None # 回测开始时间
    end_time: Optional[datetime] = None   # 回测结束时间
