"""
Sandbox executor for Program Trader.
Safely executes strategy code with restricted environment.
"""
"""
程序交易者沙箱执行器

在受限环境中安全地执行策略代码。沙箱机制防止恶意代码执行危险操作，
同时提供策略运行所需的基本功能。

安全机制：
1. 限制可用的内置函数 - 只允许安全的函数
2. 禁止危险模块导入 - 如os、sys、subprocess等
3. 执行超时控制 - 防止无限循环
4. 代码预验证 - 执行前检查代码安全性

执行流程：
1. 代码验证（validator.validate_strategy_code）
2. 在独立线程中执行代码
3. 超时监控
4. 返回执行结果
"""

import ast      # 抽象语法树模块，用于代码分析（此处未直接使用，可能在validator中使用）
import math     # 数学函数模块，提供sqrt、log等函数
from typing import Dict, Any, Optional, List  # 类型提示
from dataclasses import dataclass  # 数据类装饰器，简化类定义
import threading  # 多线程模块，用于超时控制
import ctypes    # C语言类型模块，用于强制中断线程
import traceback  # 异常追踪模块，用于获取详细错误信息

# 从本模块导入数据模型
from .models import Strategy, MarketData, Decision, ActionType
# 导入代码验证函数
from .validator import validate_strategy_code


@dataclass
class ExecutionResult:
    """Result of strategy execution."""
    """
    策略执行结果数据类

    封装策略执行后的所有返回信息，包括是否成功、决策结果、
    错误信息、执行时间和日志。
    """
    success: bool                    # 执行是否成功，True=成功，False=失败
    decision: Optional[Decision]     # 策略返回的决策对象，失败时为None
    error: Optional[str]            # 错误信息，成功时为None
    execution_time_ms: float        # 执行耗时（毫秒）
    logs: List[str] = None          # 策略执行过程中的日志输出

    def __post_init__(self):
        """数据类初始化后自动调用，确保logs不为None"""
        if self.logs is None:
            self.logs = []  # 初始化为空列表


class ExecutionTimeoutError(Exception):
    """Raised when execution times out."""
    """
    执行超时异常

    当策略代码执行时间超过限制时抛出此异常。
    用于强制中断长时间运行的代码。
    """
    pass  # 空实现，仅用于异常类型标识


# ========== 沙箱安全配置 ==========

# Safe built-ins for sandbox
# 沙箱中允许使用的Python内置函数和类型
# 只有在这个字典中的函数才能在策略代码中使用
SAFE_BUILTINS = {
    # === 类定义必需的内部函数 ===
    "__build_class__": __builtins__["__build_class__"] if isinstance(__builtins__, dict) else getattr(__builtins__, "__build_class__"),  # 用于class定义
    "__name__": "__main__",  # 模块名称

    # === 基础数学函数 ===
    "abs": abs,      # 绝对值函数，如 abs(-5) = 5
    "min": min,      # 最小值函数，如 min(1,2,3) = 1
    "max": max,      # 最大值函数，如 max(1,2,3) = 3
    "sum": sum,      # 求和函数，如 sum([1,2,3]) = 6
    "len": len,      # 长度函数，如 len([1,2,3]) = 3
    "round": round,  # 四舍五入函数，如 round(3.14159, 2) = 3.14

    # === 类型转换函数 ===
    "int": int,      # 转整数，如 int("123") = 123
    "float": float,  # 转浮点数，如 float("3.14") = 3.14
    "str": str,      # 转字符串，如 str(123) = "123"
    "bool": bool,    # 转布尔值，如 bool(1) = True

    # === 数据结构类型 ===
    "list": list,    # 列表类型，如 list((1,2,3)) = [1,2,3]
    "dict": dict,    # 字典类型，如 dict(a=1) = {"a": 1}
    "tuple": tuple,  # 元组类型，如 tuple([1,2]) = (1,2)
    "set": set,      # 集合类型，如 set([1,1,2]) = {1,2}

    # === 迭代工具函数 ===
    "range": range,        # 生成序列，如 range(3) = [0,1,2]
    "enumerate": enumerate, # 带索引遍历，如 enumerate(['a','b']) = [(0,'a'),(1,'b')]
    "zip": zip,            # 并行遍历，如 zip([1,2],['a','b']) = [(1,'a'),(2,'b')]
    "sorted": sorted,      # 排序函数，如 sorted([3,1,2]) = [1,2,3]
    "reversed": reversed,  # 反转函数，如 list(reversed([1,2,3])) = [3,2,1]

    # === 逻辑判断函数 ===
    "any": any,      # 任一为真则真，如 any([False, True]) = True
    "all": all,      # 全部为真则真，如 all([True, True]) = True
    "isinstance": isinstance,  # 类型检查，如 isinstance(1, int) = True
    "type": type,    # 获取类型，如 type(1) = <class 'int'>

    # === 常量 ===
    "True": True,    # 布尔真
    "False": False,  # 布尔假
    "None": None,    # 空值

    # === 调试用 ===
    "print": print,  # 打印函数，用于调试输出
}

# Safe math functions
# 沙箱中允许使用的数学函数
SAFE_MATH = {
    "sqrt": math.sqrt,    # 平方根，如 sqrt(4) = 2.0
    "log": math.log,      # 自然对数，如 log(2.718) ≈ 1.0
    "log10": math.log10,  # 10为底对数，如 log10(100) = 2.0
    "exp": math.exp,      # e的幂次，如 exp(1) ≈ 2.718
    "pow": math.pow,      # 幂运算，如 pow(2,3) = 8.0
    "floor": math.floor,  # 向下取整，如 floor(3.7) = 3
    "ceil": math.ceil,    # 向上取整，如 ceil(3.2) = 4
    "fabs": math.fabs,    # 浮点绝对值，如 fabs(-3.14) = 3.14
}


def _raise_timeout_in_thread(thread_id: int):
    """
    Raise ExecutionTimeoutError in the target thread using ctypes.
    在目标线程中强制抛出超时异常

    这是一个底层操作，使用Python C API强制在另一个线程中注入异常。
    用于中断执行时间过长的策略代码。

    Args:
        thread_id: 目标线程的ID
    """
    # 调用Python C API在指定线程中设置异步异常
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),          # 线程ID转换为C的unsigned long类型
        ctypes.py_object(ExecutionTimeoutError)  # 要抛出的异常类型
    )
    # 检查返回值
    if res == 0:
        pass  # 返回0表示线程已经结束，无需处理
    elif res > 1:
        # 返回>1表示多个线程受到影响，需要重置
        # 这是异常情况，需要清除设置
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), None)


class SandboxExecutor:
    """Executes strategy code in a restricted environment."""
    """
    沙箱执行器类

    在受限的命名空间中执行策略代码，确保安全性。
    主要功能：
    1. 代码验证 - 执行前检查代码安全性
    2. 超时控制 - 限制执行时间防止死循环
    3. 日志记录 - 收集策略执行过程中的输出
    4. 错误处理 - 捕获并报告执行错误
    """

    def __init__(self, timeout_seconds: int = 60):
        """
        初始化沙箱执行器

        Args:
            timeout_seconds: 执行超时时间（秒），默认60秒
        """
        self.timeout_seconds = timeout_seconds  # 保存超时设置
        self._execution_logs: list = []  # 初始化日志列表

    def execute(
        self,
        code: str,
        market_data: MarketData,
        params: Dict[str, Any] = None,
    ) -> ExecutionResult:
        """Execute strategy code and return decision."""
        import time
        start_time = time.time()

        # Validate code first
        validation = validate_strategy_code(code)
        if not validation.is_valid:
            return ExecutionResult(
                success=False,
                decision=None,
                error=f"Validation failed: {'; '.join(validation.errors)}",
                execution_time_ms=0,
            )

        # Use threading for timeout (works in any thread, unlike signal.SIGALRM)
        result_holder = {"decision": None, "error": None}
        execution_thread = None

        def run_sandbox():
            try:
                result_holder["decision"] = self._execute_in_sandbox(code, market_data, params or {})
            except ExecutionTimeoutError:
                result_holder["error"] = f"Execution timed out after {self.timeout_seconds}s"
            except Exception as e:
                result_holder["error"] = f"Execution error: {str(e)}\n{traceback.format_exc()}"

        execution_thread = threading.Thread(target=run_sandbox, daemon=True)
        execution_thread.start()
        execution_thread.join(timeout=self.timeout_seconds)

        execution_time = (time.time() - start_time) * 1000

        if execution_thread.is_alive():
            # Thread still running - try to interrupt it
            _raise_timeout_in_thread(execution_thread.ident)
            execution_thread.join(timeout=0.5)  # Give it a moment to clean up
            return ExecutionResult(
                success=False,
                decision=None,
                error=f"Execution timed out after {self.timeout_seconds}s",
                execution_time_ms=self.timeout_seconds * 1000,
                logs=self._execution_logs,
            )

        if result_holder["error"]:
            return ExecutionResult(
                success=False,
                decision=None,
                error=result_holder["error"],
                execution_time_ms=execution_time,
                logs=self._execution_logs,
            )

        return ExecutionResult(
            success=True,
            decision=result_holder["decision"],
            error=None,
            execution_time_ms=execution_time,
            logs=self._execution_logs,
        )

    def _execute_in_sandbox(
        self,
        code: str,
        market_data: MarketData,
        params: Dict[str, Any],
    ) -> Decision:
        """Execute code in restricted namespace."""
        self._execution_logs = []

        # Build restricted globals
        restricted_globals = {
            "__builtins__": SAFE_BUILTINS,
            "math": type("math", (), SAFE_MATH)(),
            "MarketData": MarketData,
            "Decision": Decision,
            "ActionType": ActionType,
            "log": self._log,
        }

        # Execute code to define the class
        exec(code, restricted_globals)

        # Find the strategy class
        strategy_class = None
        for name, obj in restricted_globals.items():
            if isinstance(obj, type) and name not in ("MarketData", "Decision", "ActionType"):
                # Check if it has should_trade method
                if hasattr(obj, "should_trade"):
                    strategy_class = obj
                    break

        if not strategy_class:
            raise ValueError("No valid strategy class found in code")

        # Instantiate and run
        strategy = strategy_class()
        if hasattr(strategy, "init"):
            strategy.init(params)

        decision = strategy.should_trade(market_data)

        # Ensure decision is valid
        if not isinstance(decision, Decision):
            raise ValueError(f"should_trade must return Decision, got {type(decision)}")

        return decision

    def _log(self, message: str):
        """Log function available to strategies."""
        self._execution_logs.append(str(message))

    def get_logs(self) -> list:
        """Get execution logs."""
        return self._execution_logs.copy()


def validate_decision(decision: Decision, positions: Dict[str, Any] = None) -> tuple:
    """
    Validate Decision object fields according to output_format rules.

    Returns:
        (is_valid: bool, errors: list[str])
    """
    errors = []
    op = decision.operation.lower() if decision.operation else ""

    # Check operation is valid
    if op not in ("buy", "sell", "hold", "close"):
        errors.append(f"Invalid operation: '{decision.operation}'. Must be buy/sell/hold/close")
        return False, errors

    # For hold, minimal validation
    if op == "hold":
        return True, []

    # For buy/sell/close, check required fields
    if decision.target_portion_of_balance < 0.1 or decision.target_portion_of_balance > 1.0:
        errors.append(f"target_portion_of_balance must be 0.1-1.0, got {decision.target_portion_of_balance}")

    if decision.leverage < 1 or decision.leverage > 50:
        errors.append(f"leverage must be 1-50, got {decision.leverage}")

    # Price requirements based on operation
    if op == "buy":
        if decision.max_price is None:
            errors.append("max_price is required for buy operations")
    elif op == "sell":
        if decision.min_price is None:
            errors.append("min_price is required for sell operations")
    elif op == "close":
        # For close, need to check position side
        pos = positions.get(decision.symbol) if positions else None
        if pos:
            if pos.get("side") == "long" and decision.min_price is None:
                errors.append("min_price is required for closing LONG positions")
            elif pos.get("side") == "short" and decision.max_price is None:
                errors.append("max_price is required for closing SHORT positions")

    # Validate time_in_force
    if decision.time_in_force not in ("Ioc", "Gtc", "Alo"):
        errors.append(f"time_in_force must be Ioc/Gtc/Alo, got {decision.time_in_force}")

    # Validate execution modes
    if decision.tp_execution not in ("market", "limit"):
        errors.append(f"tp_execution must be market/limit, got {decision.tp_execution}")
    if decision.sl_execution not in ("market", "limit"):
        errors.append(f"sl_execution must be market/limit, got {decision.sl_execution}")

    return len(errors) == 0, errors


def execute_strategy(
    code: str,
    market_data: MarketData,
    params: Dict[str, Any] = None,
    timeout_seconds: int = 60,
) -> ExecutionResult:
    """Convenience function to execute strategy code."""
    executor = SandboxExecutor(timeout_seconds=timeout_seconds)
    return executor.execute(code, market_data, params)
