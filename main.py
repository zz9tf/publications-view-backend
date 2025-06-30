from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from utils.socket_manager import socket_manager
from ws.event_handler import process_client_message
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
from config import settings
logging.basicConfig(level=logging.INFO)

# 加载环境变量
load_dotenv()

# 导入路由模块
from api import user_api, url_item_api
# 创建FastAPI应用
app = FastAPI(
    title="Publications View API",
    description="API for managing and viewing academic publications",
    version="0.1.0",
)

logger = logging.getLogger("main")

# Configure CORS
origins = [
    settings.FRONTEND_URL,  # Frontend development server
    "http://localhost:8000",  # Backend development server
    "*"
]


# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由器
app.include_router(user_api.router, prefix="/api/user", tags=["Authentication"])
app.include_router(url_item_api.router, prefix="/api/url-item", tags=["URL Items"])

@app.get("/")
def read_root():
    return {"message": "Paper View API is working!"}

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Record parameters from request
    parameters = {
    }
    
    # Connect client and store parameters
    client_id = await socket_manager.connect(websocket, **parameters)
    logger.info(f"Client {client_id} connected")
    
    try:
        logger.info(f"Starting WebSocket listening for client {client_id}")
        await socket_manager.start_listening(process_client_message, client_id)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: client_id={client_id}")
    except Exception as e:
        logger.error(f"Error in WebSocket communication: {type(e).__name__}: {e}")
    finally:
        # Client-specific tasks will be automatically cleaned up when disconnected
        if socket_manager.is_connected(client_id):
            logger.info(f"Disconnecting client: client_id={client_id}")
            await socket_manager.disconnect(client_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 