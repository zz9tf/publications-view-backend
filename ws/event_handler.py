from schemas import BaseEvent
import logging
import traceback
from utils.socket_manager import socket_manager

logger = logging.getLogger("event_handler")

async def process_client_message(message: BaseEvent, client_id: str):
    """处理客户端消息"""
    logger.info(f"处理客户端消息: {message.event} 来自客户端 {client_id}")
    
    try:
        # 根据事件类型分发处理
        if False:
            pass
        else:
            logger.warning(f"未知事件类型: {message.event}")
            await socket_manager.send("error", {"message": f"Unknown event: {message.event}"}, client_id)
    
    except Exception as e:
        logger.error(f"处理消息时出错: {str(e)}")
        logger.error(traceback.format_exc())
        await socket_manager.send("error", {"message": f"Error processing message: {str(e)}"}, client_id)
