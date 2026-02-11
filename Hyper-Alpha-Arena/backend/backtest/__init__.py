"""
回测引擎模块 (Backtest Engine Module)

提供基于事件驱动的回测基础设施，用于：
- 程序化交易策略 (Program Trader strategies)
- AI 提示策略 (未来支持)

核心组件：
- BacktestConfig: 回测配置类，包含回测所需的所有参数设置
- TriggerEvent: 统一的触发事件格式，支持信号触发和定时触发
- BacktestResult: 回测结果和统计数据，包含盈亏、胜率、最大回撤等指标
- VirtualAccount: 虚拟账户状态管理，模拟账户余额、持仓和订单
- ExecutionSimulator: 订单执行模拟器，处理滑点、手续费和止盈止损
- HistoricalDataProvider: 历史数据提供器，从数据库读取历史K线和技术指标
- ProgramBacktestEngine: 主回测引擎，协调整个回测流程
"""

from .models import (
    BacktestConfig,
    TriggerEvent,
    BacktestResult,
    BacktestTradeRecord,
    TriggerExecutionResult,
)
from .virtual_account import VirtualAccount
from .execution_simulator import ExecutionSimulator
from .historical_data_provider import HistoricalDataProvider
from .engine import ProgramBacktestEngine

__all__ = [
    "BacktestConfig",
    "TriggerEvent",
    "BacktestResult",
    "BacktestTradeRecord",
    "TriggerExecutionResult",
    "VirtualAccount",
    "ExecutionSimulator",
    "HistoricalDataProvider",
    "ProgramBacktestEngine",
]
