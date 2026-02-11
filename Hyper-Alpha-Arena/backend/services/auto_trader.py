"""
Auto Trading Service - Main entry point for automated crypto trading
This file maintains backward compatibility while delegating to split services
"""
"""
自动交易服务 - 自动化加密货币交易的主入口点

这是一个向后兼容的适配器文件，为了保持API稳定性而保留。
实际的功能实现已经迁移到专门的拆分服务中，提高了代码的模块化程度。

架构演进：
- **旧架构**：所有交易相关功能都在auto_trader.py中
- **新架构**：功能拆分为专门的服务模块
  * ai_decision_service.py - AI决策相关功能
  * trading_commands.py - 交易命令执行功能
  * 其他专门服务 - 各司其职的模块化设计

设计原则：
1. **向后兼容**：保持现有API接口不变，避免破坏性更改
2. **透明代理**：将调用转发给新的服务模块
3. **渐进迁移**：支持代码逐步迁移到新架构
4. **功能完整性**：确保所有原有功能都能正常工作

重构价值：
- **代码组织**：按功能领域明确分工，提高可维护性
- **测试隔离**：每个模块可以独立测试，提高测试覆盖率
- **职责单一**：每个服务专注于特定领域，符合单一职责原则
- **扩展性**：新功能可以在专门的模块中添加

使用建议：
- 新代码：直接使用拆分后的专门服务
- 现有代码：可以继续使用此文件，也可以逐步迁移
- 接口稳定：此文件的接口将长期保持稳定

注意事项：
此文件主要作为适配层存在，实际的业务逻辑和新功能开发
建议直接在对应的专门服务中进行，以保持架构的清晰性。
"""
import logging

# Import from the new split services
# 从新的拆分服务中导入功能
from services.ai_decision_service import (
    call_ai_for_decision as _call_ai_for_decision,  # AI决策调用函数
    save_ai_decision as _save_ai_decision,          # AI决策保存函数
    get_active_ai_accounts as _choose_account,      # 获取活跃AI账户
    _get_portfolio_data,                            # 获取投资组合数据
    _is_default_api_key,                           # 检查是否为默认API密钥
    SUPPORTED_SYMBOLS                               # 支持的交易标的
)

from services.trading_commands import (
    place_ai_driven_crypto_order,    # 执行AI驱动的加密货币订单
    place_random_crypto_order,       # 执行随机加密货币订单（测试用）
    _get_market_prices,              # 获取市场价格
    _select_side,                    # 选择交易方向
    AUTO_TRADE_JOB_ID,              # 自动交易任务ID
    AI_TRADE_JOB_ID,                # AI交易任务ID
    AI_TRADING_SYMBOLS              # AI交易支持的标的列表
)


logger = logging.getLogger(__name__)


# Backward compatibility - re-export main functions
# 向后兼容 - 重新导出主要函数
# All the actual implementation is now in the split service files
# 所有实际实现现在都在拆分的服务文件中

# These constants are kept for backward compatibility
# 这些常量为了向后兼容而保留
AUTO_TRADE_JOB_ID = AI_TRADE_JOB_ID  # 统一任务ID标识
AI_TRADE_JOB_ID = AI_TRADE_JOB_ID    # AI交易任务标识

# 常量说明：
# - AUTO_TRADE_JOB_ID: 历史遗留的自动交易任务标识
# - AI_TRADE_JOB_ID: 当前使用的AI交易任务标识
# - 为了兼容性，两个常量指向同一个值
# - 在调度系统中用于识别和管理AI交易任务
