from schemas import BaseEvent
import logging
import traceback
from utils.socket_manager import socket_manager
from schemas import WS_EVENTS, GoogleSearchRequest
from utils.scholar_crawler import scholar_crawler

logger = logging.getLogger("event_handler")

async def process_client_message(message: BaseEvent, client_id: str):
    """处理客户端消息"""
    logger.info(f"处理客户端消息: {message.event} 来自客户端 {client_id}")
    
    try:
        # 根据事件类型分发处理
        if message.event == WS_EVENTS["START_FETCH_A_GOOGLE_SCHOLAR_URL"]:
            handle_start_fetch_a_google_scholar_url(message, client_id)
        else:
            logger.warning(f"未知事件类型: {message.event}")
            await socket_manager.send("error", {"message": f"Unknown event: {message.event}"}, client_id)
    
    except Exception as e:
        logger.error(f"处理消息时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await socket_manager.send("error", {"message": f"Error processing message: {str(e)}"}, client_id)

def handle_start_fetch_a_google_scholar_url(message: BaseEvent, client_id: str):
    """处理开始获取Google Scholar信息"""
    logger.info(f"处理开始获取Google Scholar信息: {message.event} 来自客户端 {client_id}")
    request = GoogleSearchRequest(**message.data)
    url = request.url
    search_id = request.searchId
    client_id = request.clientId
        
    logger.info(f"收到获取URL条目请求: url={url}, searchId={search_id}, clientId={client_id}")
    scholar_crawler.scholar_info(url, client_id, search_id)