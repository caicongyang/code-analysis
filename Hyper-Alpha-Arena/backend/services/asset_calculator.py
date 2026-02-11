"""
Asset Value Calculator Service

Calculates total market value of account positions based on current prices.
"""
"""
资产价值计算服务

基于当前市场价格计算账户持仓的总市值。这是投资组合价值评估和
风险监控的基础组件，为资产曲线、盈亏计算等功能提供数据支持。

核心功能：
1. 持仓市值计算：遍历账户所有持仓，计算实时总市值
2. 多币种支持：自动获取各个持仓标的的最新价格
3. 容错处理：价格获取失败时优雅跳过，不中断整体计算

技术特点：
- 精确计算：使用Decimal类型避免浮点数精度问题
- 容错设计：单个标的价格获取失败不影响其他持仓计算
- 实时性：每次调用都获取最新市场价格
- 日志记录：价格获取失败时记录警告日志便于排查

应用场景：
- 账户总资产计算
- 资产快照记录
- 风险监控和预警
- 投资组合分析
"""

from decimal import Decimal
from sqlalchemy.orm import Session
from database.models import Position
from .market_data import get_last_price


def calc_positions_value(db: Session, account_id: int) -> float:
    """
    Calculate total market value of positions

    Args:
        db: Database session
        account_id: Account ID

    Returns:
        Total market value of positions, returns 0 if price cannot be obtained
    """
    """
    计算账户持仓的总市值

    遍历指定账户的所有持仓，获取每个持仓标的的当前价格，
    计算并汇总所有持仓的市场价值。

    Args:
        db: 数据库会话对象，用于查询持仓数据
        account_id: 账户ID，指定要计算的账户

    Returns:
        float: 持仓总市值（USD），价格获取失败的持仓被跳过

    计算公式：
    总市值 = Σ(持仓数量 × 当前价格)

    容错机制：
    - 单个标的价格获取失败时记录警告但继续计算
    - 返回能够计算的持仓价值总和
    - 不会因为部分失败而中断整个计算流程

    注意事项：
    - 使用Decimal确保精确计算
    - 最终结果转换为float返回
    - 日志记录失败情况便于问题排查
    """
    positions = db.query(Position).filter(Position.account_id == account_id).all()
    total = Decimal("0")
    
    for p in positions:
        try:
            price = Decimal(str(get_last_price(p.symbol, p.market)))
            total += price * Decimal(p.quantity)
        except Exception as e:
            # Log error but don't interrupt calculation, skip position if price cannot be obtained
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Cannot get price for {p.symbol}.{p.market}, skipping position value calculation: {e}")
            continue
    
    return float(total)
