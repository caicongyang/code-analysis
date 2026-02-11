"""
Program Trader Module
Provides programmatic trading strategies with backtesting and sandbox execution
"""
"""
程序交易者模块

提供基于Python代码的程序化交易策略框架，支持策略开发、回测和
沙箱执行。与AI交易者互补，为高级用户提供完全代码控制的交易方式。

核心组件：
1. models - 数据模型
   - Strategy: 策略基类，用户继承实现交易逻辑
   - MarketData: 市场数据输入，包含账户、持仓、行情信息
   - Decision: 决策输出，包含交易指令和参数
   - Position/Trade/Order: 持仓、交易、订单数据结构
   - Kline/RegimeInfo: K线和市场制度信息

2. validator - 代码验证
   - CodeValidator: 安全检查和语法验证
   - ValidationResult: 验证结果
   - validate_strategy_code: 验证策略代码

3. executor - 策略执行
   - SandboxExecutor: 安全沙箱执行环境
   - ExecutionResult: 执行结果
   - execute_strategy: 执行策略函数

4. backtest - 回测引擎
   - BacktestEngine: 历史数据回测引擎
   - BacktestResult: 回测结果统计
   - BacktestTrade: 回测交易记录

5. data_provider - 数据提供
   - DataProvider: 统一的市场数据访问接口

使用流程：
1. 用户编写继承Strategy的策略类
2. 代码通过validator验证安全性
3. 策略在沙箱环境中执行
4. 可选：在回测引擎中验证策略效果
5. 部署到实盘环境自动执行

安全特性：
- 沙箱隔离：策略代码在受限环境执行
- 代码审查：禁止危险操作和导入
- 资源限制：执行时间和内存限制
"""

from .models import Strategy, MarketData, Decision, Position, Trade, Order, Kline, RegimeInfo, ActionType
from .validator import CodeValidator, ValidationResult, validate_strategy_code
from .executor import SandboxExecutor, ExecutionResult, execute_strategy
from .backtest import BacktestEngine, BacktestResult, BacktestTrade
from .data_provider import DataProvider

__all__ = [
    # Models
    'Strategy',
    'MarketData',
    'Decision',
    'Position',
    'Trade',
    'Order',
    'Kline',
    'RegimeInfo',
    'ActionType',
    # Validator
    'CodeValidator',
    'ValidationResult',
    'validate_strategy_code',
    # Executor
    'SandboxExecutor',
    'ExecutionResult',
    'execute_strategy',
    # Backtest
    'BacktestEngine',
    'BacktestResult',
    'BacktestTrade',
    # Data
    'DataProvider',
]
