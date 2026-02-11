"""
Backtest engine for Program Trader.
Simulates strategy execution on historical data.
"""
"""
程序交易者回测引擎

在历史数据上模拟策略执行，评估策略表现。
回测是策略开发的关键步骤，可以在不承担实际风险的情况下验证策略效果。

核心功能：
1. 历史数据模拟 - 按时间顺序回放历史K线数据
2. 策略执行 - 在每个时间点执行策略代码获取决策
3. 交易模拟 - 模拟开仓、平仓和手续费计算
4. 绩效统计 - 计算胜率、盈亏、最大回撤等指标

使用流程：
1. 准备历史K线数据
2. 编写策略代码
3. 调用BacktestEngine.run()运行回测
4. 分析BacktestResult中的绩效指标

注意事项：
- 回测结果仅供参考，实盘可能有滑点和流动性影响
- 建议使用足够长的历史数据（至少几百根K线）
- 手续费率默认0.06%（Taker费率）
"""

from typing import Dict, List, Any, Optional  # 类型提示
from dataclasses import dataclass, field  # 数据类装饰器
from datetime import datetime  # 日期时间处理
import time  # 时间函数

# 从本模块导入数据模型
from .models import MarketData, Decision, ActionType, Kline, Position, RegimeInfo


@dataclass
class BacktestTrade:
    """Record of a simulated trade."""
    """
    回测交易记录

    记录回测过程中模拟执行的每一笔交易，用于分析策略行为。
    """
    timestamp: int     # 交易时间戳（Unix秒数）
    symbol: str        # 交易标的符号，如"BTC"
    side: str          # 仓位方向："long"多头 或 "short"空头
    action: str        # 交易动作："open"开仓 或 "close"平仓
    price: float       # 成交价格
    size: float        # 交易数量（标的数量，非美元金额）
    pnl: float = 0.0   # 盈亏金额（仅平仓时有值）
    reason: str = ""   # 交易原因（来自策略的reason字段）


@dataclass
class BacktestResult:
    """Result of backtest run."""
    """
    回测运行结果

    包含回测的完整结果，包括是否成功、绩效指标、权益曲线和交易历史。
    """
    success: bool                  # 回测是否成功执行
    error: Optional[str] = None    # 错误信息（失败时）

    # === 绩效指标 Performance metrics ===
    total_trades: int = 0          # 总交易次数（平仓次数）
    winning_trades: int = 0        # 盈利交易次数
    losing_trades: int = 0         # 亏损交易次数
    win_rate: float = 0.0          # 胜率（盈利次数/总次数）

    total_pnl: float = 0.0         # 总盈亏金额（美元）
    max_drawdown: float = 0.0      # 最大回撤比例（0.1表示10%）
    sharpe_ratio: float = 0.0      # 夏普比率（风险调整收益）

    # === 权益曲线 Equity curve ===
    # 列表中每个元素: {"timestamp": 时间戳, "equity": 权益值}
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)

    # === 交易历史 Trade history ===
    trades: List[BacktestTrade] = field(default_factory=list)


class BacktestDataProvider:
    """Provides historical data for backtesting."""
    """
    回测数据提供器

    为回测模拟提供历史数据，模拟实盘中DataProvider的行为。
    关键区别是只能访问"当前时间点"之前的数据，避免未来数据泄露。
    """

    def __init__(self, klines: Dict[str, List[Kline]], indicators: Dict = None):
        """
        初始化回测数据提供器

        Args:
            klines: K线数据字典，格式为 {"BTC_5m": [Kline, ...]}
            indicators: 预计算的指标数据（可选）
        """
        self.klines = klines              # 存储K线数据
        self.indicators = indicators or {}  # 存储指标数据
        self.current_index = 0             # 当前时间索引（模拟时间推进）

    def get_klines(self, symbol: str, period: str, count: int = 50) -> List[Kline]:
        """
        获取K线数据

        只返回当前时间点之前的K线，模拟实盘只能看到历史数据。

        Args:
            symbol: 交易标的符号
            period: K线周期
            count: 请求的K线数量

        Returns:
            K线列表（最多count根，不包含未来数据）
        """
        key = f"{symbol}_{period}"  # 构建缓存键
        if key not in self.klines:
            return []  # 没有数据返回空列表
        # 计算可访问的数据范围（不超过当前索引）
        end_idx = min(self.current_index + 1, len(self.klines[key]))
        start_idx = max(0, end_idx - count)  # 确保不小于0
        return self.klines[key][start_idx:end_idx]  # 返回切片

    def get_indicator(self, symbol: str, indicator: str, period: str) -> Dict:
        """获取技术指标值"""
        key = f"{symbol}_{indicator}_{period}_{self.current_index}"
        return self.indicators.get(key, {})

    def get_flow(self, symbol: str, metric: str, period: str) -> Dict:
        """获取市场流量指标"""
        key = f"{symbol}_{metric}_{period}_{self.current_index}"
        return self.indicators.get(key, {})

    def get_regime(self, symbol: str, period: str) -> RegimeInfo:
        """获取市场制度分类"""
        key = f"{symbol}_regime_{period}_{self.current_index}"
        data = self.indicators.get(key, {})
        return RegimeInfo(
            regime=data.get("regime", "noise"),  # 默认noise
            conf=data.get("conf", 0.0),          # 默认置信度0
        )

    def get_price_change(self, symbol: str, period: str) -> Dict:
        """获取价格变化（回测中简化返回）"""
        return {"change_percent": 0.0, "change_usd": 0.0}


class BacktestEngine:
    """Runs backtest simulation on historical data."""
    """
    回测引擎类

    在历史数据上运行回测模拟，评估策略表现。
    模拟真实的交易流程，包括开仓、平仓、手续费计算和盈亏统计。
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,  # 初始资金（美元），默认1万
        fee_rate: float = 0.0006,           # 手续费率，0.0006 = 0.06%
    ):
        """
        初始化回测引擎

        Args:
            initial_balance: 初始资金（美元）
            fee_rate: 交易手续费率（Taker费率，默认0.06%）
        """
        self.initial_balance = initial_balance  # 保存初始资金
        self.fee_rate = fee_rate                # 保存手续费率

    def run(
        self,
        code: str,
        klines: Dict[str, List[Kline]],
        symbol: str,
        period: str = "5m",
        params: Dict[str, Any] = None,
    ) -> BacktestResult:
        """Run backtest on historical klines."""
        from .executor import SandboxExecutor

        if not klines or f"{symbol}_{period}" not in klines:
            return BacktestResult(success=False, error="No kline data provided")

        kline_data = klines[f"{symbol}_{period}"]
        if len(kline_data) < 10:
            return BacktestResult(success=False, error="Insufficient kline data")

        # Initialize state
        balance = self.initial_balance
        position: Optional[Position] = None
        trades: List[BacktestTrade] = []
        equity_curve: List[Dict] = []
        peak_equity = self.initial_balance
        max_drawdown = 0.0

        # Create data provider and executor
        data_provider = BacktestDataProvider(klines)
        executor = SandboxExecutor(timeout_seconds=2)

        # Iterate through klines
        for i in range(50, len(kline_data)):
            data_provider.current_index = i
            current_kline = kline_data[i]
            current_price = current_kline.close

            # Build market data
            market_data = MarketData(
                available_balance=balance,
                total_equity=balance + (self._calc_unrealized_pnl(position, current_price) if position else 0),
                trigger_symbol=symbol,
                trigger_type="signal",
                prices={symbol: current_price},
                positions={symbol: position} if position else {},
                _data_provider=data_provider,
            )

            # Execute strategy
            result = executor.execute(code, market_data, params or {})
            if not result.success:
                continue

            decision = result.decision
            if not decision:
                continue

            # Process decision
            if decision.action == ActionType.BUY and position is None:
                # Open long
                size = min(decision.size_usd, balance * 0.95) / current_price
                fee = size * current_price * self.fee_rate
                balance -= fee
                position = Position(
                    symbol=symbol, side="long", size=size,
                    entry_price=current_price, unrealized_pnl=0,
                    leverage=decision.leverage, liquidation_price=0,
                )
                trades.append(BacktestTrade(
                    timestamp=current_kline.timestamp, symbol=symbol,
                    side="long", action="open", price=current_price,
                    size=size, reason=decision.reason,
                ))

            elif decision.action == ActionType.SELL and position is None:
                # Open short
                size = min(decision.size_usd, balance * 0.95) / current_price
                fee = size * current_price * self.fee_rate
                balance -= fee
                position = Position(
                    symbol=symbol, side="short", size=size,
                    entry_price=current_price, unrealized_pnl=0,
                    leverage=decision.leverage, liquidation_price=0,
                )
                trades.append(BacktestTrade(
                    timestamp=current_kline.timestamp, symbol=symbol,
                    side="short", action="open", price=current_price,
                    size=size, reason=decision.reason,
                ))

            elif decision.action == ActionType.CLOSE and position is not None:
                # Close position
                pnl = self._calc_realized_pnl(position, current_price)
                fee = position.size * current_price * self.fee_rate
                balance += pnl - fee
                trades.append(BacktestTrade(
                    timestamp=current_kline.timestamp, symbol=symbol,
                    side=position.side, action="close", price=current_price,
                    size=position.size, pnl=pnl, reason=decision.reason,
                ))
                position = None

            # Record equity
            equity = balance + (self._calc_unrealized_pnl(position, current_price) if position else 0)
            equity_curve.append({"timestamp": current_kline.timestamp, "equity": equity})

            # Track drawdown
            if equity > peak_equity:
                peak_equity = equity
            drawdown = (peak_equity - equity) / peak_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Calculate final metrics
        return self._calculate_metrics(trades, equity_curve, max_drawdown)

    def _calc_unrealized_pnl(self, position: Position, current_price: float) -> float:
        if position.side == "long":
            return (current_price - position.entry_price) * position.size
        else:
            return (position.entry_price - current_price) * position.size

    def _calc_realized_pnl(self, position: Position, exit_price: float) -> float:
        return self._calc_unrealized_pnl(position, exit_price)

    def _calculate_metrics(
        self, trades: List[BacktestTrade], equity_curve: List[Dict], max_drawdown: float
    ) -> BacktestResult:
        close_trades = [t for t in trades if t.action == "close"]
        winning = [t for t in close_trades if t.pnl > 0]
        losing = [t for t in close_trades if t.pnl <= 0]

        total_pnl = sum(t.pnl for t in close_trades)
        win_rate = len(winning) / len(close_trades) if close_trades else 0.0

        return BacktestResult(
            success=True,
            total_trades=len(close_trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            total_pnl=total_pnl,
            max_drawdown=max_drawdown,
            equity_curve=equity_curve,
            trades=trades,
        )
