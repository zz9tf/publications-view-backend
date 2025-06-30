from fastapi import APIRouter
from schemas import ApiResponse, GoogleSearchRequest, URLItem
import logging
from datetime import datetime
import json
import random

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
        
        # 创建符合URLItem模式的模拟数据
        fetched_papers = 0
        total_papers = random.randint(fetched_papers, 100)
        progress = int((fetched_papers / total_papers) * 100) if total_papers > 0 else 100
        
        mock_data = URLItem(
            search_id=search_id,
            url=url,
            short_description=f"Junzhou Huang",
            progress=progress,
            status="completed" if progress == 100 else "processing",
            fetched_paper_count=fetched_papers,
            total_paper_count=total_papers
        )
        
        logger.info(f"返回模拟数据: {mock_data}")
        
        return ApiResponse(
            success=True,
            data=mock_data.model_dump()
        )
        
    except Exception as e:
        logger.error(f"处理URL条目请求时出错: {str(e)}")
        return ApiResponse(success=False, error=f"处理请求失败: {str(e)}")
