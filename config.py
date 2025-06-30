import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

class Settings:
    # 基础配置
    ENV: str = os.getenv('ENV', 'development')
    
    # 安全配置
    JWT_SECRET: str = os.getenv('JWT_SECRET')
    if not JWT_SECRET:
        if ENV == 'production':
            raise ValueError("JWT_SECRET must be set in production environment")
        # 开发环境使用默认值（仅用于开发）
        JWT_SECRET = "dev_secret_key_change_in_production"
    
    # JWT配置
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_DAYS: int = int(os.getenv('JWT_EXPIRES_DAYS', '7'))
    
    # 社交登录配置
    # Google OAuth配置
    GOOGLE_CLIENT_ID: str = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET: str = os.getenv('GOOGLE_CLIENT_SECRET', '')
    GOOGLE_REDIRECT_URI: str = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/api/user/social-login/google')
    
    # 前端应用URL
    FRONTEND_URL: str = os.getenv('FRONTEND_URL', 'http://localhost:3000')

settings = Settings() 