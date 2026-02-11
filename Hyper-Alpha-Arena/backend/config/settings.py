from pydantic import BaseModel
from typing import Dict
import os


class MarketConfig(BaseModel):
    """
    市场交易配置模型

    定义不同市场的交易参数和费率结构，确保交易成本计算准确性。
    支持多市场配置，方便扩展到不同资产类型。

    字段说明：
    - market: 市场标识符（如"CRYPTO"表示加密货币市场）
    - min_commission: 最低手续费金额（美元），防止小额交易手续费过低
    - commission_rate: 手续费率（0.001 = 0.1%），基于交易额的百分比
    - exchange_rate: 汇率（相对于美元），用于多币种支持
    - min_order_quantity: 最小下单数量，防止过小订单
    - lot_size: 交易单位大小，定义最小交易增量

    应用场景：
    - 交易成本计算
    - 订单验证
    - 风险控制
    - 多市场支持
    """
    market: str                    # 市场类型标识
    min_commission: float          # 最低手续费（USD）
    commission_rate: float         # 手续费率（小数形式）
    exchange_rate: float           # 汇率（相对USD）
    min_order_quantity: int = 1    # 最小下单数量
    lot_size: int = 1             # 交易单位大小


class HyperliquidBuilderConfig(BaseModel):
    """Hyperliquid Builder Fee Configuration"""
    """
    Hyperliquid构建者费用配置

    Hyperliquid交易所支持构建者费用模式，允许应用开发者
    从用户交易中获得分润，用于支持应用开发和运营。

    字段详解：
    - builder_address: 构建者钱包地址，接收费用分润的以太坊地址
    - builder_fee: 构建者费用（十分之一基点为单位）
      * 30 = 0.03% = 3个基点
      * 1个基点(bp) = 0.01%
      * 计算公式：实际费用 = builder_fee / 1000 %

    费用机制：
    - 用户交易时，Hyperliquid会将指定比例的手续费分配给构建者
    - 这为DeFi应用提供了可持续的收入模式
    - 费用从交易所手续费中扣除，不额外向用户收取
    """
    builder_address: str     # 构建者钱包地址（以太坊地址格式）
    builder_fee: int        # 构建者费用（十分之一基点，30 = 0.03%）


#  default configs for CRYPTO markets
# 加密货币市场的默认配置
DEFAULT_TRADING_CONFIGS: Dict[str, MarketConfig] = {
    "CRYPTO": MarketConfig(
        market="CRYPTO",                # 市场类型：加密货币
        min_commission=0.1,            # 最低手续费$0.1，适合加密货币小额交易
        commission_rate=0.001,         # 手续费率0.1%，符合主流加密货币交易所标准
        exchange_rate=1.0,             # 汇率1.0，以USD为基准货币
        min_order_quantity=1,          # 最小下单数量1，支持小数交易
        lot_size=1,                    # 交易单位1，允许精确到小数点的交易
    ),
}
# 默认交易配置说明：
# - 针对加密货币永续合约交易优化
# - 手续费率符合Hyperliquid等主流交易所标准
# - 支持小额交易，最低手续费仅$0.1
# - 灵活的交易单位，适应各种交易策略

# Hyperliquid Builder Fee Configuration
# Hyperliquid构建者费用配置
HYPERLIQUID_BUILDER_CONFIG = HyperliquidBuilderConfig(
    builder_address=os.getenv(
        "HYPERLIQUID_BUILDER_ADDRESS",                           # 环境变量：构建者地址
        "0x012E82f81e506b8f0EF69FF719a6AC65822b5924"            # 默认构建者钱包地址
    ),
    builder_fee=int(os.getenv("HYPERLIQUID_BUILDER_FEE", "30"))  # 环境变量：构建者费用，默认30(0.03%)
)
# Hyperliquid构建者配置详解：
# - 构建者地址：接收费用分润的以太坊钱包地址
# - 构建者费用：30个十分之一基点 = 0.03% = 3个基点
# - 环境变量优先：支持通过环境变量动态配置
# - 收入来源：用户交易手续费的一定比例分成
# - 用途：支持Hyper Alpha Arena平台的持续发展和维护
