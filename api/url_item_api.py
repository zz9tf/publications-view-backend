from fastapi import APIRouter
from schemas import ApiResponse, GoogleSearchRequest, URLItem
import logging
from datetime import datetime
import json
import random
from utils.scholar_crawler import scholar_crawler

# 配置日志记录器
logger = logging.getLogger(f"url_item_api {datetime.now()}")

# 创建路由器
router = APIRouter()

@router.post("/fetch", response_model=ApiResponse)
async def fetch_url_item(request: GoogleSearchRequest):
    """
    获取URL条目的假响应
    
    Args:
        request: 包含url、search_id和client_id的请求
    
    Returns:
        ApiResponse: 包含模拟数据的响应
    """
    try:
        # 获取请求数据
        url = request.url
        search_id = request.searchId
        client_id = request.clientId
        
        logger.info(f"收到获取URL条目请求: url={url}, searchId={search_id}, clientId={client_id}")
        
        scholar_crawler.init_basic_scholar_info(url, client_id, search_id)
        search_info = scholar_crawler.google_scholar_search_dict[client_id][search_id]
        
        data = URLItem(
            search_id=search_info["search_id"],
            url=search_info["url"],
            short_description=search_info["author_name"],
            progress=search_info["progress"],
            status=search_info["status"],
            fetched_paper_count=search_info["fetched_paper_count"],
            total_paper_count=search_info["total_paper_count"]
        )
        
        logger.info(f"返回模拟数据: {data}")
        
        return ApiResponse(
            success=True,
            data=data.model_dump()
        )
        
    except Exception as e:
        logger.error(f"处理URL条目请求时出错: {str(e)}")
        return ApiResponse(success=False, error=f"处理请求失败: {str(e)}")
