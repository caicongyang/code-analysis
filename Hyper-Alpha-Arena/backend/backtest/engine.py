"""
Program Backtest Engine

Event-driven backtest engine for Program Trader strategies.
Orchestrates trigger generation, strategy execution, and result calculation.
"""
"""
程序交易回测引擎

基于事件驱动的程序交易策略回测引擎。
负责协调触发事件生成、策略执行和结果计算。
该引擎模拟真实交易环境，支持信号触发和定时触发两种模式，
可以准确评估策略在历史数据上的表现。
"""

import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from .models import BacktestConfig, TriggerEvent, BacktestResult, BacktestTradeRecord, TriggerExecutionResult
from .virtual_account import VirtualAccount
from .execution_simulator import ExecutionSimulator
from .historical_data_provider import HistoricalDataProvider

logger = logging.getLogger(__name__)

# Interval to milliseconds mapping
# 时间间隔到毫秒数的映射表，用于处理定时触发器的时间计算
INTERVAL_MS = {
    "1m": 60 * 1000,             # 1分钟 = 60,000毫秒
    "5m": 5 * 60 * 1000,         # 5分钟 = 300,000毫秒
    "15m": 15 * 60 * 1000,       # 15分钟 = 900,000毫秒
    "30m": 30 * 60 * 1000,       # 30分钟 = 1,800,000毫秒
    "1h": 60 * 60 * 1000,        # 1小时 = 3,600,000毫秒
    "4h": 4 * 60 * 60 * 1000,    # 4小时 = 14,400,000毫秒
    "1d": 24 * 60 * 60 * 1000,   # 1天 = 86,400,000毫秒
}


class ProgramBacktestEngine:
    """
    Event-driven backtest engine for Program Trader.

    Flow:
    1. Generate trigger events (signal + scheduled)
    2. Sort events by timestamp
    3. For each event:
       - Set historical data provider time
       - Check TP/SL triggers
       - Build MarketData
       - Execute strategy code
       - Simulate order execution
       - Update virtual account
    4. Calculate statistics
    """
    """
    程序交易者的事件驱动回测引擎。

    工作流程：
    1. 生成触发事件（信号触发 + 定时触发）
       - 信号触发：根据市场流量信号（如CVD、OI变化等）产生的交易信号
       - 定时触发：按固定时间间隔（如每小时）检查交易条件
    2. 按时间戳排序事件，确保时间顺序的正确性
    3. 对于每个事件：
       - 设置历史数据提供器的时间点，模拟当时的市场环境
       - 检查止盈止损触发器，处理已有仓位的自动平仓
       - 构建市场数据对象，包含价格、指标、流量数据等
       - 执行策略代码，获取交易决策
       - 模拟订单执行，考虑滑点、手续费等真实成本
       - 更新虚拟账户状态，记录权益变化
    4. 计算统计数据，包括收益率、胜率、最大回撤等关键指标

    该引擎设计用于准确模拟程序化交易策略的实际表现，
    为策略优化提供可靠的量化分析基础。
    """

    def __init__(self, db: Session):
        """初始化程序回测引擎

        Args:
            db: 数据库会话对象，用于访问历史数据、信号配置等
        """
        self.db = db  # 数据库连接，用于获取历史K线数据、信号池配置、市场制度分类等

    def run(self, config: BacktestConfig) -> BacktestResult:
        """
        Run backtest with given configuration.

        Args:
            config: Backtest configuration

        Returns:
            BacktestResult with statistics and trade history
        """
        """
        执行回测的主方法

        Args:
            config: 回测配置对象，包含以下关键参数：
                   - 起止时间：定义回测的时间范围
                   - 交易标的：如BTC、ETH等加密货币符号列表
                   - 策略代码：用户编写的Python策略代码
                   - 信号池ID：触发交易的市场信号配置
                   - 定时触发间隔：如1h、4h等固定检查频率
                   - 初始资金：回测起始资金量
                   - 滑点和手续费：模拟真实交易成本

        Returns:
            BacktestResult: 回测结果对象，包含详细的性能统计和交易记录
                          - 总收益和收益率
                          - 胜率、盈亏比等交易统计
                          - 最大回撤和夏普比率
                          - 完整的交易明细和权益曲线
        """
        start_time = time.time()  # 记录开始时间，用于计算回测执行耗时

        try:
            # 1. Generate signal trigger events (scheduled triggers are dynamic)
            # 1. 生成信号触发事件（定时触发事件是动态生成的）
            signal_triggers = self._generate_trigger_events(config)

            # Allow backtest even with no signal triggers if scheduled triggers are enabled
            # 即使没有信号触发器，如果启用了定时触发器也允许回测
            if not signal_triggers and not config.scheduled_interval:
                return BacktestResult(
                    success=False,
                    error="No trigger events generated. Check signal pools and time range."
                )

            # 2. Initialize components
            # 2. 初始化核心组件
            # 创建虚拟账户，模拟真实交易账户的资金和仓位管理
            account = VirtualAccount(initial_balance=config.initial_balance)
            # 创建执行模拟器，处理订单执行、滑点、手续费计算
            simulator = ExecutionSimulator(
                slippage_percent=config.slippage_percent,  # 滑点百分比，模拟市场冲击成本
                fee_rate=config.fee_rate,                 # 手续费率，模拟交易所收费
            )
            # 创建历史数据提供器，负责获取指定时间点的市场数据
            data_provider = HistoricalDataProvider(
                db=self.db,                               # 数据库连接
                symbols=config.symbols,                   # 交易标的列表
                start_time_ms=config.start_time_ms,       # 回测开始时间（毫秒时间戳）
                end_time_ms=config.end_time_ms,           # 回测结束时间（毫秒时间戳）
            )

            # 3. Run event loop (returns all triggers including dynamic scheduled ones)
            # 3. 运行事件循环（返回所有触发器，包括动态生成的定时触发器）
            trades, equity_curve, all_triggers = self._run_event_loop(
                config, signal_triggers, account, simulator, data_provider
            )

            # 4. Calculate statistics
            # 4. 计算回测统计数据，包括各种性能指标和风险指标
            result = self._calculate_result(
                trades=trades,                           # 所有交易记录
                equity_curve=equity_curve,               # 权益曲线数据点
                triggers=all_triggers,                   # 所有触发事件记录
                account=account,                         # 最终账户状态
                config=config,                           # 回测配置参数
            )
            result.execution_time_ms = (time.time() - start_time) * 1000  # 设置执行时间

            return result

        except Exception as e:
            # 捕获并记录回测过程中的任何错误，确保系统稳定性
            logger.error(f"Backtest failed: {e}", exc_info=True)
            return BacktestResult(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _generate_trigger_events(self, config: BacktestConfig) -> List[TriggerEvent]:
        """Generate signal trigger events only. Scheduled triggers are handled dynamically."""
        """
        生成信号触发事件，定时触发事件会在事件循环中动态处理

        该方法负责：
        1. 遍历配置中的所有信号池
        2. 对每个信号池和交易标的组合进行回测
        3. 提取满足条件的触发时间点
        4. 获取触发时刻的市场制度分类信息
        5. 构建完整的触发事件对象

        Returns:
            List[TriggerEvent]: 按时间排序的信号触发事件列表
        """
        from services.signal_backtest_service import signal_backtest_service
        from services.market_regime_service import get_market_regime

        events = []  # 存储所有信号触发事件

        # Generate signal triggers
        # 为每个信号池和交易标的生成信号触发事件
        for pool_id in config.signal_pool_ids:
            for symbol in config.symbols:
                try:
                    # 调用信号回测服务，获取该信号池在指定时间范围内的触发记录
                    pool_result = signal_backtest_service.backtest_pool(
                        self.db, pool_id, symbol,
                        config.start_time_ms, config.end_time_ms
                    )

                    if "error" in pool_result:
                        logger.warning(f"Signal backtest error for pool {pool_id}: {pool_result['error']}")
                        continue

                    # 处理每个触发时间点
                    for t in pool_result.get("triggers", []):
                        # Get market regime at trigger time
                        # 获取触发时刻的市场制度分类信息（如突破、吸收、陷阱等）
                        regime_data = None
                        try:
                            regime_result = get_market_regime(
                                self.db, symbol, "5m",          # 使用5分钟时间框架
                                use_realtime=True,              # 使用实时模式
                                timestamp_ms=t["timestamp"]     # 指定时间点
                            )
                            if regime_result:
                                # 构建市场制度数据字典
                                regime_data = {
                                    "regime": regime_result.get("regime", "noise"),           # 制度类型
                                    "conf": regime_result.get("confidence", 0.0),            # 置信度
                                    "direction": regime_result.get("direction", "neutral"),  # 方向
                                    "reason": regime_result.get("reason", ""),               # 判断理由
                                    "indicators": regime_result.get("indicators", {}),       # 指标数据
                                }
                        except Exception as e:
                            logger.debug(f"Failed to get regime at {t['timestamp']}: {e}")

                        # 创建触发事件对象，包含完整的上下文信息
                        events.append(TriggerEvent(
                            timestamp=t["timestamp"],                           # 触发时间戳
                            trigger_type="signal",                              # 触发类型：信号触发
                            symbol=symbol,                                      # 交易标的
                            pool_id=pool_id,                                    # 信号池ID
                            pool_name=pool_result.get("pool_name"),             # 信号池名称
                            pool_logic=pool_result.get("logic"),                # 信号池逻辑（AND/OR）
                            triggered_signals=t.get("triggered_signals", []),  # 触发的具体信号列表
                            market_regime=regime_data,                          # 市场制度分类信息
                        ))
                except Exception as e:
                    logger.error(f"Failed to get signal triggers for pool {pool_id}: {e}")

        # Sort by timestamp
        # 按时间戳排序，确保事件按时间顺序处理
        events.sort(key=lambda e: e.timestamp)

        # Log signal triggers count (scheduled triggers are dynamic)
        # 记录生成的信号触发事件数量（定时触发事件是动态生成的）
        logger.info(f"Generated {len(events)} signal trigger events")

        return events

    def _run_event_loop(
        self,
        config: BacktestConfig,
        signal_triggers: List[TriggerEvent],
        account: VirtualAccount,
        simulator: ExecutionSimulator,
        data_provider: HistoricalDataProvider,
    ) -> tuple:
        """
        Run the main event loop with dynamic scheduled trigger generation.

        Signal triggers have higher priority. Each trigger (signal or scheduled)
        resets the scheduled trigger timer, matching real-time execution behavior.
        """
        """
        运行主事件循环，动态生成定时触发器

        该方法是回测引擎的核心，实现了事件驱动的交易模拟：

        触发器优先级策略：
        - 信号触发具有更高优先级，会立即处理
        - 每个触发器（信号或定时）都会重置定时触发器计时器
        - 这种设计匹配真实时间的执行行为

        事件循环逻辑：
        1. 处理预生成的信号触发器
        2. 在信号触发间隙插入定时触发器
        3. 每个触发器执行时：
           - 设置数据提供器时间
           - 检查止盈止损条件
           - 构建市场数据对象
           - 执行策略代码
           - 处理交易决策
           - 更新账户状态

        Returns:
            tuple: (交易记录列表, 权益曲线, 所有触发器列表)
        """
        from program_trader.executor import SandboxExecutor

        executor = SandboxExecutor(timeout_seconds=5)
        trades: List[BacktestTradeRecord] = []
        equity_curve: List[Dict[str, Any]] = []
        all_triggers: List[TriggerEvent] = []  # Track all triggers for logging

        # Scheduled trigger state
        scheduled_interval_ms = None
        if config.scheduled_interval and config.scheduled_interval in INTERVAL_MS:
            scheduled_interval_ms = INTERVAL_MS[config.scheduled_interval]

        # Initialize: next scheduled trigger is start_time + interval
        last_trigger_time = config.start_time_ms

        def execute_trigger(trigger: TriggerEvent) -> int:
            """Execute a single trigger and return the trigger timestamp."""
            nonlocal last_trigger_time

            all_triggers.append(trigger)

            # Set current time
            data_provider.set_current_time(trigger.timestamp)

            # Get current prices
            prices = data_provider.get_current_prices(config.symbols)
            if not prices:
                return trigger.timestamp

            # Check TP/SL triggers first
            tp_sl_trades = simulator.check_tp_sl_triggers(account, prices, trigger.timestamp)
            trades.extend(tp_sl_trades)

            # Update equity after TP/SL
            account.update_equity(prices)

            # Determine trigger symbol
            trigger_symbol = trigger.symbol if trigger.symbol else config.symbols[0]

            # Build MarketData for strategy
            market_data = self._build_market_data(
                account, data_provider, trigger, trigger_symbol
            )

            # Execute strategy
            result = executor.execute(config.code, market_data, {})

            if result.success and result.decision:
                decision = result.decision
                symbol = decision.symbol or trigger_symbol
                current_price = prices.get(symbol, 0)

                if current_price > 0:
                    # Get signal names for logging
                    signal_names = [
                        s.get("signal_name", "") for s in (trigger.triggered_signals or [])
                    ]

                    trade = simulator.execute_decision(
                        decision=decision,
                        account=account,
                        current_price=current_price,
                        timestamp=trigger.timestamp,
                        trigger_type=trigger.trigger_type,
                        pool_name=trigger.pool_name,
                        triggered_signals=signal_names,
                    )
                    if trade:
                        trades.append(trade)

            # Update equity and record
            account.update_equity(prices)
            equity_curve.append({
                "timestamp": trigger.timestamp,
                "equity": account.equity,
                "balance": account.balance,
                "drawdown": account.max_drawdown,
            })

            return trigger.timestamp

        # Process signal triggers with dynamic scheduled triggers
        for signal_trigger in signal_triggers:
            # Before processing this signal, check if scheduled triggers should fire
            if scheduled_interval_ms:
                next_scheduled_time = last_trigger_time + scheduled_interval_ms
                while next_scheduled_time < signal_trigger.timestamp:
                    # Fire scheduled trigger
                    scheduled_trigger = TriggerEvent(
                        timestamp=next_scheduled_time,
                        trigger_type="scheduled",
                        symbol="",
                    )
                    last_trigger_time = execute_trigger(scheduled_trigger)
                    next_scheduled_time = last_trigger_time + scheduled_interval_ms

            # Process signal trigger (resets scheduled timer)
            last_trigger_time = execute_trigger(signal_trigger)

        # After all signal triggers, continue with remaining scheduled triggers until end_time
        if scheduled_interval_ms:
            next_scheduled_time = last_trigger_time + scheduled_interval_ms
            while next_scheduled_time <= config.end_time_ms:
                scheduled_trigger = TriggerEvent(
                    timestamp=next_scheduled_time,
                    trigger_type="scheduled",
                    symbol="",
                )
                last_trigger_time = execute_trigger(scheduled_trigger)
                next_scheduled_time = last_trigger_time + scheduled_interval_ms

        # Log final trigger counts
        signal_count = sum(1 for t in all_triggers if t.trigger_type == "signal")
        scheduled_count = sum(1 for t in all_triggers if t.trigger_type == "scheduled")
        logger.info(f"Executed {len(all_triggers)} triggers "
                   f"({signal_count} signal, {scheduled_count} scheduled)")

        return trades, equity_curve, all_triggers

    def estimate_total_triggers(
        self,
        config: BacktestConfig,
        signal_triggers: List[TriggerEvent],
    ) -> int:
        """
        Estimate total trigger count including dynamic scheduled triggers.
        Uses same algorithm as run_event_loop_generator but only counts.
        """
        if not config.scheduled_interval or config.scheduled_interval not in INTERVAL_MS:
            return len(signal_triggers)

        scheduled_interval_ms = INTERVAL_MS[config.scheduled_interval]
        total = 0
        last_trigger_time = config.start_time_ms

        for signal_trigger in signal_triggers:
            # Count scheduled triggers before this signal
            next_scheduled_time = last_trigger_time + scheduled_interval_ms
            while next_scheduled_time < signal_trigger.timestamp:
                total += 1
                last_trigger_time = next_scheduled_time
                next_scheduled_time = last_trigger_time + scheduled_interval_ms
            # Count signal trigger
            total += 1
            last_trigger_time = signal_trigger.timestamp

        # Count remaining scheduled triggers
        next_scheduled_time = last_trigger_time + scheduled_interval_ms
        while next_scheduled_time <= config.end_time_ms:
            total += 1
            last_trigger_time = next_scheduled_time
            next_scheduled_time = last_trigger_time + scheduled_interval_ms

        return total

    def run_event_loop_generator(
        self,
        config: BacktestConfig,
        signal_triggers: List[TriggerEvent],
        account: VirtualAccount,
        simulator: ExecutionSimulator,
        data_provider: HistoricalDataProvider,
    ):
        """
        Generator version of event loop for streaming progress.

        Yields TriggerExecutionResult for each trigger (signal or scheduled).
        Handles dynamic scheduled trigger generation with timer reset.
        """
        from program_trader.executor import SandboxExecutor

        executor = SandboxExecutor(timeout_seconds=5)

        # Scheduled trigger state
        scheduled_interval_ms = None
        if config.scheduled_interval and config.scheduled_interval in INTERVAL_MS:
            scheduled_interval_ms = INTERVAL_MS[config.scheduled_interval]

        last_trigger_time = config.start_time_ms

        def check_tp_sl_between_triggers(
            last_time_ms: int,
            current_time_ms: int,
        ) -> List[BacktestTradeRecord]:
            """Check TP/SL using kline high/low between two trigger points."""
            all_tp_sl_trades = []

            # Get klines between triggers for each symbol with positions
            for symbol in config.symbols:
                pos = account.get_position(symbol)
                if not pos:
                    continue

                # Get 5m klines between triggers
                klines = data_provider.get_klines_between(
                    symbol, last_time_ms, current_time_ms, "5m"
                )

                if klines:
                    trades = simulator.check_tp_sl_with_klines(
                        account, klines, pos.side, data_provider
                    )
                    all_tp_sl_trades.extend(trades)

            # Sort by exit timestamp
            all_tp_sl_trades.sort(key=lambda t: t.exit_timestamp or 0)
            return all_tp_sl_trades

        def execute_single_trigger(
            trigger: TriggerEvent,
            prev_trigger_time: int,
        ) -> TriggerExecutionResult:
            """Execute a single trigger and return result."""
            equity_before = account.equity

            # Set current time and clear query log
            data_provider.set_current_time(trigger.timestamp)
            data_provider.clear_query_log()

            # Get current prices
            prices = data_provider.get_current_prices(config.symbols)
            if not prices:
                return TriggerExecutionResult(
                    trigger=trigger,
                    trigger_symbol=config.symbols[0] if config.symbols else "",
                    prices={},
                    executor_result=None,
                    trade=None,
                    tp_sl_trades=[],
                    equity_before=equity_before,
                    equity_after=equity_before,
                    equity_after_tp_sl=equity_before,
                    unrealized_pnl=0,
                    data_queries=[],
                )

            # Check TP/SL using kline high/low between triggers (more accurate)
            tp_sl_trades = check_tp_sl_between_triggers(prev_trigger_time, trigger.timestamp)

            # Update equity after TP/SL and record it
            account.update_equity(prices)
            equity_after_tp_sl = account.equity

            # Determine trigger symbol
            trigger_symbol = trigger.symbol if trigger.symbol else config.symbols[0]

            # Build MarketData for strategy
            market_data = self._build_market_data(
                account, data_provider, trigger, trigger_symbol
            )

            # Execute strategy
            result = executor.execute(config.code, market_data, {})

            trade = None
            if result.success and result.decision:
                decision = result.decision
                symbol = decision.symbol or trigger_symbol
                current_price = prices.get(symbol, 0)

                if current_price > 0 and decision.operation != "hold":
                    signal_names = [
                        s.get("signal_name", "") for s in (trigger.triggered_signals or [])
                    ]
                    trade = simulator.execute_decision(
                        decision=decision,
                        account=account,
                        current_price=current_price,
                        timestamp=trigger.timestamp,
                        trigger_type=trigger.trigger_type,
                        pool_name=trigger.pool_name,
                        triggered_signals=signal_names,
                    )

            # Update equity
            account.update_equity(prices)

            return TriggerExecutionResult(
                trigger=trigger,
                trigger_symbol=trigger_symbol,
                prices=prices,
                executor_result=result,
                trade=trade,
                tp_sl_trades=tp_sl_trades,
                equity_before=equity_before,
                equity_after=account.equity,
                equity_after_tp_sl=equity_after_tp_sl,
                unrealized_pnl=account.unrealized_pnl_total,
                data_queries=data_provider.get_query_log(),
            )

        # Process signal triggers with dynamic scheduled triggers
        for signal_trigger in signal_triggers:
            # Before processing this signal, fire any pending scheduled triggers
            if scheduled_interval_ms:
                next_scheduled_time = last_trigger_time + scheduled_interval_ms
                while next_scheduled_time < signal_trigger.timestamp:
                    scheduled_trigger = TriggerEvent(
                        timestamp=next_scheduled_time,
                        trigger_type="scheduled",
                        symbol="",
                    )
                    exec_result = execute_single_trigger(scheduled_trigger, last_trigger_time)
                    last_trigger_time = scheduled_trigger.timestamp
                    yield exec_result
                    next_scheduled_time = last_trigger_time + scheduled_interval_ms

            # Process signal trigger (resets scheduled timer)
            exec_result = execute_single_trigger(signal_trigger, last_trigger_time)
            last_trigger_time = signal_trigger.timestamp
            yield exec_result

        # After all signal triggers, continue with remaining scheduled triggers
        if scheduled_interval_ms:
            next_scheduled_time = last_trigger_time + scheduled_interval_ms
            while next_scheduled_time <= config.end_time_ms:
                scheduled_trigger = TriggerEvent(
                    timestamp=next_scheduled_time,
                    trigger_type="scheduled",
                    symbol="",
                )
                exec_result = execute_single_trigger(scheduled_trigger, last_trigger_time)
                last_trigger_time = scheduled_trigger.timestamp
                yield exec_result
                next_scheduled_time = last_trigger_time + scheduled_interval_ms

    def _build_market_data(
        self,
        account: VirtualAccount,
        data_provider: HistoricalDataProvider,
        trigger: TriggerEvent,
        trigger_symbol: str,
    ) -> Any:
        """Build MarketData object for strategy execution."""
        from program_trader.models import MarketData, Position

        # Convert virtual positions to Position objects
        positions = {}
        for symbol, vpos in account.positions.items():
            positions[symbol] = Position(
                symbol=symbol,
                side=vpos.side,
                size=vpos.size,
                entry_price=vpos.entry_price,
                unrealized_pnl=vpos.unrealized_pnl,
                leverage=vpos.leverage,
                liquidation_price=0,
            )

        # Build triggered signals info - pass through ALL fields from backtest service
        # Strategy code needs: metric, current_value, direction, ratio, threshold, etc.
        triggered_signals = []
        if trigger.triggered_signals:
            for sig in trigger.triggered_signals:
                # Pass through all signal data as-is
                signal_data = dict(sig)  # Copy all fields
                # Ensure current_value is set (backtest service uses 'value')
                if "current_value" not in signal_data and "value" in signal_data:
                    signal_data["current_value"] = signal_data["value"]
                triggered_signals.append(signal_data)

        # Build trigger_market_regime from trigger.market_regime
        trigger_market_regime = None
        if trigger.market_regime:
            from program_trader.models import RegimeInfo
            mr = trigger.market_regime
            trigger_market_regime = RegimeInfo(
                regime=mr.get("regime", "noise"),
                conf=mr.get("conf", 0.0),
                direction=mr.get("direction", "neutral"),
                reason=mr.get("reason", ""),
                indicators=mr.get("indicators", {}),
            )

        return MarketData(
            available_balance=account.balance,
            total_equity=account.equity,
            trigger_symbol=trigger_symbol,
            trigger_type=trigger.trigger_type,
            positions=positions,
            # Trigger context (detailed)
            signal_pool_name=trigger.pool_name or "",
            pool_logic=trigger.pool_logic or "OR",
            triggered_signals=triggered_signals,
            trigger_market_regime=trigger_market_regime,
            _data_provider=data_provider,
        )

    def _calculate_result(
        self,
        trades: List[BacktestTradeRecord],
        equity_curve: List[Dict[str, Any]],
        triggers: List[TriggerEvent],
        account: VirtualAccount,
        config: BacktestConfig,
    ) -> BacktestResult:
        """Calculate backtest statistics."""
        # Filter closed trades (with exit_price)
        closed_trades = [t for t in trades if t.exit_price is not None]

        # Basic counts
        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if t.pnl > 0]
        losing_trades = [t for t in closed_trades if t.pnl <= 0]

        # PnL calculations
        total_pnl = sum(t.pnl for t in closed_trades)
        total_pnl_percent = (total_pnl / config.initial_balance * 100) if config.initial_balance > 0 else 0

        # Win rate
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

        # Profit factor
        total_profit = sum(t.pnl for t in winning_trades)
        total_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = (total_profit / total_loss) if total_loss > 0 else float('inf') if total_profit > 0 else 0

        # Average win/loss
        avg_win = (total_profit / len(winning_trades)) if winning_trades else 0
        avg_loss = (total_loss / len(losing_trades)) if losing_trades else 0

        # Largest win/loss
        largest_win = max((t.pnl for t in winning_trades), default=0)
        largest_loss = min((t.pnl for t in losing_trades), default=0)

        # Trigger counts
        signal_triggers = sum(1 for t in triggers if t.trigger_type == "signal")
        scheduled_triggers = sum(1 for t in triggers if t.trigger_type == "scheduled")

        # Sharpe ratio (simplified - annualized)
        sharpe_ratio = 0.0
        if equity_curve and len(equity_curve) > 1:
            returns = []
            for i in range(1, len(equity_curve)):
                prev_eq = equity_curve[i-1]["equity"]
                curr_eq = equity_curve[i]["equity"]
                if prev_eq > 0:
                    returns.append((curr_eq - prev_eq) / prev_eq)

            if returns:
                import statistics
                mean_return = statistics.mean(returns)
                std_return = statistics.stdev(returns) if len(returns) > 1 else 0
                if std_return > 0:
                    # Annualize (assume daily returns, 252 trading days)
                    sharpe_ratio = (mean_return / std_return) * (252 ** 0.5)

        return BacktestResult(
            success=True,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,
            max_drawdown=account.max_drawdown,
            max_drawdown_percent=account.max_drawdown_percent * 100,
            sharpe_ratio=sharpe_ratio,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            total_triggers=len(triggers),
            signal_triggers=signal_triggers,
            scheduled_triggers=scheduled_triggers,
            equity_curve=equity_curve,
            trades=trades,
            trigger_log=triggers,
            start_time=config.start_time,
            end_time=config.end_time,
        )


