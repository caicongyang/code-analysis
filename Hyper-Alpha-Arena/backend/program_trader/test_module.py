#!/usr/bin/env python3
"""
Test script for Program Trader module.
Run from backend directory: python3 -m program_trader.test_module
"""
"""
程序交易者模块测试脚本

用于验证程序交易者模块各组件的功能是否正常工作。
包含代码验证器、沙箱执行器和超时处理的测试用例。

运行方式：
从backend目录运行: python3 -m program_trader.test_module

测试内容：
1. test_validator() - 测试代码验证器
   - 有效代码应该通过验证
   - 语法错误应该被检测
   - 禁止的导入应该被阻止
   - 缺少必要方法应该报错

2. test_executor() - 测试沙箱执行器
   - 策略代码应该能正确执行
   - 返回正确的Decision对象

3. test_timeout() - 测试超时机制
   - 无限循环应该被超时中断
"""

import sys  # 系统模块，用于路径操作和退出
# 将backend目录添加到Python路径，确保能找到模块
sys.path.insert(0, '/home/wwwroot/hyper-alpha-arena-prod/backend')

# 从program_trader模块导入需要测试的组件
from program_trader import (
    validate_strategy_code,  # 代码验证函数
    execute_strategy,        # 策略执行函数
    MarketData,             # 市场数据模型
    Decision,               # 决策模型
    ActionType,             # 动作类型枚举
)


def test_validator():
    """
    Test code validator.
    测试代码验证器

    验证CodeValidator能正确识别：
    - 有效的策略代码
    - 语法错误
    - 禁止的导入
    - 缺少必要方法
    """
    print("\n=== Testing Code Validator ===")

    # Valid code
    valid_code = '''
class MyStrategy:
    def init(self, params):
        self.threshold = params.get("threshold", 30)

    def should_trade(self, data):
        rsi = data.get_indicator(data.trigger_symbol, "RSI14", "5m")
        if rsi.get("value", 50) < self.threshold:
            return Decision(
                action=ActionType.BUY,
                symbol=data.trigger_symbol,
                size_usd=1000,
                leverage=10,
                reason="RSI oversold"
            )
        return Decision(action=ActionType.HOLD, symbol=data.trigger_symbol)
'''
    result = validate_strategy_code(valid_code)
    print(f"Valid code test: is_valid={result.is_valid}, errors={result.errors}")
    assert result.is_valid, f"Valid code should pass: {result.errors}"

    # Invalid code - syntax error
    invalid_syntax = '''
class MyStrategy:
    def should_trade(self, data)
        return Decision(action=ActionType.HOLD)
'''
    result = validate_strategy_code(invalid_syntax)
    print(f"Syntax error test: is_valid={result.is_valid}, errors={result.errors}")
    assert not result.is_valid, "Syntax error should fail"

    # Invalid code - forbidden import
    forbidden_import = '''
import os
class MyStrategy:
    def should_trade(self, data):
        os.system("rm -rf /")
        return Decision(action=ActionType.HOLD, symbol="BTC")
'''
    result = validate_strategy_code(forbidden_import)
    print(f"Forbidden import test: is_valid={result.is_valid}, errors={result.errors}")
    assert not result.is_valid, "Forbidden import should fail"

    # Invalid code - missing should_trade
    missing_method = '''
class MyStrategy:
    def init(self, params):
        pass
'''
    result = validate_strategy_code(missing_method)
    print(f"Missing method test: is_valid={result.is_valid}, errors={result.errors}")
    assert not result.is_valid, "Missing should_trade should fail"

    print("All validator tests passed!")


def test_executor():
    """Test sandbox executor."""
    print("\n=== Testing Sandbox Executor ===")

    code = '''
class SimpleStrategy:
    def init(self, params):
        self.buy_threshold = params.get("buy_threshold", 30)

    def should_trade(self, data):
        # Simple strategy: always hold
        log(f"Processing {data.trigger_symbol}")
        return Decision(
            action=ActionType.HOLD,
            symbol=data.trigger_symbol,
            reason="Test strategy - always hold"
        )
'''

    # Create mock market data
    market_data = MarketData(
        available_balance=10000.0,
        total_equity=10000.0,
        trigger_symbol="BTC",
        trigger_type="signal",
        prices={"BTC": 42000.0},
    )

    result = execute_strategy(code, market_data, {"buy_threshold": 25})
    print(f"Execution result: success={result.success}, error={result.error}")
    print(f"Decision: {result.decision}")
    print(f"Execution time: {result.execution_time_ms:.2f}ms")

    assert result.success, f"Execution should succeed: {result.error}"
    assert result.decision.action == ActionType.HOLD
    print("Executor test passed!")


def test_timeout():
    """Test execution timeout."""
    print("\n=== Testing Timeout ===")

    infinite_loop = '''
class BadStrategy:
    def should_trade(self, data):
        while True:
            pass
        return Decision(action=ActionType.HOLD, symbol="BTC")
'''

    market_data = MarketData(trigger_symbol="BTC")
    result = execute_strategy(infinite_loop, market_data, timeout_seconds=2)
    print(f"Timeout test: success={result.success}, error={result.error}")
    assert not result.success, "Infinite loop should timeout"
    assert "timed out" in result.error.lower() or "timeout" in result.error.lower(), f"Error should mention timeout: {result.error}"
    print("Timeout test passed!")


if __name__ == "__main__":
    try:
        test_validator()
        test_executor()
        test_timeout()
        print("\n=== All tests passed! ===")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
