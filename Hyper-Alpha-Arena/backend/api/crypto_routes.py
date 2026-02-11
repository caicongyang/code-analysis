"""
Crypto-specific API routes
"""
"""
加密货币专用API路由

提供加密货币市场数据查询的专用接口，包括交易对列表、
实时价格、市场状态等基础市场信息。

API端点：
- GET /api/crypto/symbols: 获取所有可交易的加密货币对
- GET /api/crypto/price/{symbol}: 获取指定币种的当前价格
- GET /api/crypto/status/{symbol}: 获取指定币种的市场状态
- GET /api/crypto/popular: 获取热门加密货币及其价格

核心功能：
1. 交易对查询：列出系统支持的所有加密货币交易对
2. 实时价格：获取指定币种的最新市场价格
3. 市场状态：查询交易对的交易状态和基本信息
4. 热门币种：提供常用币种的快速访问

数据来源：
- 通过market_data服务获取实时市场数据
- 支持多交易所数据聚合
- 使用缓存优化响应速度

热门币种列表：
BTC, ETH, SOL, DOGE, BNB, XRP
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging

from services.market_data import get_all_symbols, get_last_price, get_market_status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crypto", tags=["crypto"])


@router.get("/symbols")
async def get_crypto_symbols() -> List[str]:
    """Get all available crypto trading pairs"""
    try:
        symbols = get_all_symbols()
        return symbols
    except Exception as e:
        logger.error(f"Error getting crypto symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price/{symbol}")
async def get_crypto_price(symbol: str) -> Dict[str, Any]:
    """Get current price for a crypto symbol"""
    try:
        price = get_last_price(symbol, "CRYPTO")
        return {
            "symbol": symbol,
            "price": price,
            "market": "CRYPTO"
        }
    except Exception as e:
        logger.error(f"Error getting price for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{symbol}")
async def get_crypto_market_status(symbol: str) -> Dict[str, Any]:
    """Get market status for a crypto symbol"""
    try:
        status = get_market_status(symbol, "CRYPTO")
        return status
    except Exception as e:
        logger.error(f"Error getting market status for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/popular")
async def get_popular_cryptos() -> List[Dict[str, Any]]:
    """Get popular crypto trading pairs with current prices"""
    popular_symbols = ["BTC", "ETH", "SOL", "DOGE", "BNB", "XRP"]
    
    results = []
    for symbol in popular_symbols:
        try:
            price = get_last_price(symbol, "CRYPTO")
            results.append({
                "symbol": symbol,
                "name": symbol.split("/")[0],  # Extract base currency
                "price": price,
                "market": "CRYPTO"
            })
        except Exception as e:
            logger.warning(f"Could not get price for {symbol}: {e}")
            continue
    
    return results