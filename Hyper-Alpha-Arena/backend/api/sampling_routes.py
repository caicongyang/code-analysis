"""
Sampling Pool API Routes
"""
"""
采样池API路由

提供价格采样池状态查询功能，用于监控系统的价格数据采集状态
和计算价格变化趋势。

API端点：
- GET /api/sampling/pool-status: 获取采样池状态摘要
- GET /api/sampling/pool-details: 获取采样池详细数据

采样池功能：
1. 定期采集各交易对的价格数据
2. 维护固定深度的价格样本队列
3. 计算价格变化百分比
4. 为AI交易策略提供价格趋势信息

状态信息：
- 各交易对的样本数量
- 最新价格和时间戳
- 价格变化百分比

详细数据：
- 完整的价格样本列表（按时间排序）
- 每个样本的价格和采样时间
- 计算得出的价格变化率

应用场景：
- 监控数据采集系统运行状态
- 调试价格数据相关问题
- 验证采样配置效果
"""

from fastapi import APIRouter
from typing import Dict, Any
from services.sampling_pool import sampling_pool

router = APIRouter(prefix="/api/sampling", tags=["sampling"])


@router.get("/pool-status")
async def get_sampling_pool_status() -> Dict[str, Any]:
    """Get current sampling pool status with detailed sample data"""
    return sampling_pool.get_pool_status()


@router.get("/pool-details")
async def get_sampling_pool_details() -> Dict[str, Any]:
    """Get detailed sampling pool data including all samples"""
    details = {}
    for symbol, pool in sampling_pool.pools.items():
        if pool:
            # Sort samples from oldest to newest (chronological order)
            sorted_samples = sorted(pool, key=lambda x: x['timestamp'])
            details[symbol] = {
                'samples': [
                    {
                        'price': sample['price'],
                        'timestamp': sample['timestamp'],
                        'datetime': sample['datetime'].isoformat()
                    }
                    for sample in sorted_samples
                ],
                'sample_count': len(sorted_samples),
                'price_change_percent': sampling_pool.get_price_change_percent(symbol)
            }
    return details