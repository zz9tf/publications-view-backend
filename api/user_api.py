from fastapi import APIRouter,Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import jwt
import logging
import requests
import json
from schemas import (
    LoginRequest, RegisterRequest, TokenVerifyRequest, ApiResponse
)
from config import settings
from utils.supabase_manager import supabase
from requests_oauthlib import OAuth1Session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google.auth.transport.requests import Request as AuthRequest
import urllib.parse
from passlib.context import CryptContext
import base64
import io

# Configure password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configure logger
logger = logging.getLogger(f"user_api {datetime.now()}")

# OAuth2 password bearer token setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="user/login")

# JWT configuration
JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = settings.JWT_ALGORITHM
JWT_EXPIRES_DAYS = settings.JWT_EXPIRES_DAYS

# 社交登录配置
GOOGLE_CLIENT_ID = settings.GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI = settings.GOOGLE_REDIRECT_URI

# 前端应用URL
FRONTEND_URL = settings.FRONTEND_URL

# Create router
router = APIRouter()

# Password hashing functions
def get_password_hash(password: str) -> str:
    """Generate a hashed password"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)

# Create JWT token
def create_access_token(user_id: str) -> str:
    expire = datetime.now() + timedelta(days=JWT_EXPIRES_DAYS)
    to_encode = {
        "sub": user_id,
        "exp": expire
    }
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

# Verify JWT token
def verify_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None

# 社交登录相关函数
async def process_social_user(user_data: Dict) -> Dict:
    """
    处理社交登录用户，如果用户不存在则创建新用户
    
    Args:
        user_data: 用户数据
    
    Returns:
        Dict: 用户信息和JWT令牌
    """
    try:
        # 查询是否存在关联的用户
        user_info_response = supabase.select(
            "user_info",
            filters={"email": user_data.get("email")}
        )
            
        if user_info_response.data and len(user_info_response.data) > 0:
        # 找到已存在的用户
            user = user_info_response.data[0]
        else:
            # 用户信息不存在，创建用户信息
            user_auth_response = supabase.insert("user_auth", {
                "email": user_data.get("email"),
                "password": "null"
            })
            user_id = user_auth_response.data[0]["user_id"]
            
            user_info_response = supabase.insert("user_info", {
                "user_id": user_id,
                "username": user_data.get("username"),
                "email": user_data.get("email"),
                "phone": user_data.get("phone"),
                "avatar": user_data.get("avatar"),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
            user = user_info_response.data[0]
        
        # 生成JWT令牌
        token = create_access_token(user["user_id"])
        
        return {
            "user": user,
            "token": token
        }
        
    except Exception as e:
        logger.error(f"处理社交登录用户出错: {str(e)}")
        raise e

# Auth endpoints
@router.post("/login", response_model=ApiResponse)
async def login(request: LoginRequest):
    try:
        # Get user by email
        auth_response = supabase.select("user_auth", filters={"email": request.email})
        
        if not auth_response.data or len(auth_response.data) == 0:
            return ApiResponse(success=False, error="Invalid email or password")
        
        user = auth_response.data[0]
        
        # Check for social login accounts
        if user["password"] == "null":
            return ApiResponse(success=False, error="Please login with social account and reset password for email login")
        
        # Verify password
        if not verify_password(request.password, user["password"]):
            return ApiResponse(success=False, error="Invalid email or password")
        
        user_id = user["user_id"]
        
        # Get user info
        info_response = supabase.select("user_info", filters={"user_id": user_id})
        if info_response.data and len(info_response.data) > 0:
            user_info = info_response.data[0]
            # Combine user auth and info data
            user.update(user_info)
        else:
            logger.warning(f"User info not found for user_id: {user_id}")
        
        # Generate JWT token
        token = create_access_token(user_id)
        
        return ApiResponse(
            success=True,
            data={"user": user, "token": token}
        )
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return ApiResponse(success=False, error=str(e))

@router.post("/register", response_model=ApiResponse)
async def register(request: RegisterRequest):
    try:
        logger.info(f"Register request: {request}")
        # Check if user already exists
        existing_user = supabase.select("user_auth", filters={"email": request.email})
        if len(existing_user.data) > 0:
            logger.info(f"Existing user: {existing_user}")
            return ApiResponse(success=False, error="Email already registered")
        
        # Hash the password
        hashed_password = get_password_hash(request.password)
        
        # Create new user in user_auth with hashed password
        auth_response = supabase.insert("user_auth", {
            "email": request.email,
            "password": hashed_password
        })
        user = auth_response.data[0]
        logger.info(f"User: {user}")
        
        # Create entry in user_info table
        user_info_response = supabase.insert("user_info", {
            "user_id": user["user_id"],
            "username": request.username,
            "email": request.email,
            "phone": request.phone,
            "medical_records_count": 0,
            "appointments_count": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        })
        logger.info(f"User info created: {user_info_response.data}")
        
        # Generate JWT token
        token = create_access_token(user["user_id"])

        user_info = user_info_response.data[0]

        user.update(user_info)
        
        return ApiResponse(
            success=True,
            data={"user": user, "token": token}
        )
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return ApiResponse(success=False, error=str(e))

@router.post("/logout", response_model=ApiResponse)
async def logout():
    # Since JWT tokens are stateless, we don't need to do anything server-side
    # The client will handle removing the token
    return ApiResponse(success=True)

@router.post("/verify-token", response_model=ApiResponse)
async def verify_token_endpoint(request: TokenVerifyRequest):
    try:
        # Verify token
        user_id = verify_token(request.token)

        if not user_id:
            return ApiResponse(success=False, error="Invalid token")
            
        # Get user from database
        user_info_response = supabase.select("user_info", filters={"user_id": user_id})
        if not user_info_response.data or len(user_info_response.data) == 0:
            return ApiResponse(success=False, error="User not found")
        user = user_info_response.data[0]
        
        return ApiResponse(
            success=True,
            data={"user": user}
        )
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return ApiResponse(success=False, error=str(e))

@router.get("/social-login/google", response_model=ApiResponse)
async def google_social_login(request: Request, code: str):
    """
    处理Google OAuth回调
    
    Args:
        request: 请求对象
        code: Google授权码
    
    Returns:
        重定向到前端，带有JWT令牌
    """
    logger.info(f"GET Google callback")
    logger.info(f"Google callback request: {request}")
    logger.info(f"Google callback code: {code}")
    
    try:
        # 使用代理管理器处理Google API请求
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        
        logger.info(f"开始请求Google token, URL: {token_url}")
        
        # 使用代理管理器发送请求
        try:
            session = requests.Session()
            logger.info(f"发送POST请求: {token_url}")
            token_response = session.request(method="POST", url=token_url, timeout=10000, data=token_data)
        except Exception as e:
            logger.error(f"请求错误: {str(e)}")
            return ApiResponse(success=False, error=f"请求错误: {str(e)}")
        
        logger.info(f"Google token请求状态码: {token_response.status_code}")
        
        if token_response.status_code != 200:
            error_text = token_response.text
            try:
                error_json = token_response.json()
                error_text = json.dumps(error_json, ensure_ascii=False)
            except:
                pass
                
            logger.error(f"Google token兑换失败: {error_text}")
            return ApiResponse(success=False, error=f"无法兑换Google授权码: {error_text}")
        
        # 获取令牌
        tokens = token_response.json()
        logger.info(f"成功获取Google tokens")
        
        # 提取 ID令牌
        id_token_str = tokens.get("id_token")
        if not id_token_str:
            logger.error("ID token不存在")
            return ApiResponse(success=False, error="无法获取用户信息")
            
        # 验证 ID令牌并获取用户信息
        user_data = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
    
        # 记录用户信息
        logger.info(f"获取到Google用户信息: {json.dumps(user_data, ensure_ascii=False)}")
        
        # 构建用户信息
        user_info = {
            "email": user_data.get("email"),
            "username": user_data.get("name"),
            "avatar": user_data.get("picture")
        }

        result = await process_social_user(user_info)
        
        # 将user信息序列化并编码
        user_json = json.dumps(result.get("user"))
        encoded_user = urllib.parse.quote(user_json)

        # 构建重定向URL
        redirect_url = f"{FRONTEND_URL}/auth/callback?token={result.get('token')}&user={encoded_user}&provider=google"

        # 使用RedirectResponse重定向到前端应用
        return RedirectResponse(url=redirect_url, status_code=302)
        
    except Exception as e:
        logger.error(f"Google回调处理错误: {str(e)}")
        logger.exception(e)  # 输出完整的堆栈跟踪
        return ApiResponse(success=False, error=f"Google回调处理错误: {str(e)}")

@router.post("/profile", response_model=ApiResponse)
async def update_profile(request: Request):
    try:
        # 获取请求体
        request_data = await request.json()
        logger.info(f"Profile update request: {request_data}")
        
        # 获取token和资料数据
        token = request_data.get("token")
        profile_data = request_data.get("profile", {})
        
        if not token:
            return ApiResponse(success=False, error="Token is required")
        
        # 验证token
        user_id = verify_token(token)
        if not user_id:
            return ApiResponse(success=False, error="Invalid token")
        
        # 检查用户
        user_info = supabase.select("user_info", filters={"user_id": user_id})
        if not user_info.data or len(user_info.data) == 0:
            return ApiResponse(success=False, error="User not found")
        
        # 更新字段
        update_data = {}
        allowed_fields = ["first_name", "last_name", "username", "phone", "bio", "role", "avatar"]
        
        for field in allowed_fields:
            if field in profile_data:
                update_data[field] = profile_data[field]
        
        if not update_data:
            return ApiResponse(success=False, error="No valid fields to update")
        
        # 添加更新时间
        update_data["updated_at"] = datetime.now().isoformat()
        
        # 执行更新
        update_response = supabase.update("user_info", update_data, {"user_id": user_id})
        
        if update_response.data and len(update_response.data) > 0:
            return ApiResponse(success=True, data={"user": update_response.data[0]})
        else:
            return ApiResponse(success=False, error="Failed to update profile")
            
    except Exception as e:
        logger.error(f"Profile update error: {str(e)}")
        return ApiResponse(success=False, error=str(e))

@router.post("/change-password", response_model=ApiResponse)
async def change_password(request: Request):
    try:
        # Get request body
        request_data = await request.json()
        logger.info(f"Change password request received")
        
        # Get token and password data
        token = request_data.get("token")
        current_password = request_data.get("currentPassword")
        new_password = request_data.get("newPassword")
        
        # Validation
        if not token:
            return ApiResponse(success=False, error="Token is required")
            
        if not current_password or not new_password:
            return ApiResponse(success=False, error="Current password and new password are required")
            
        # Verify token
        user_id = verify_token(token)
        if not user_id:
            return ApiResponse(success=False, error="Invalid token")
            
        # Get user auth data
        auth_response = supabase.select("user_auth", filters={"user_id": user_id})
        if not auth_response.data or len(auth_response.data) == 0:
            return ApiResponse(success=False, error="User not found")
            
        user_auth = auth_response.data[0]
        
        # Check for social login accounts
        if user_auth["password"] == "null":
            return ApiResponse(success=False, error="Social login accounts cannot change password directly")
        
        # Verify current password
        if not verify_password(current_password, user_auth["password"]):
            return ApiResponse(success=False, error="Current password is incorrect")
            
        # Hash the new password
        hashed_password = get_password_hash(new_password)
        
        # Update password
        update_response = supabase.update(
            "user_auth", 
            {"password": hashed_password},
            {"user_id": user_id}
        )
        
        if update_response.data and len(update_response.data) > 0:
            return ApiResponse(success=True, message="Password updated successfully")
        else:
            return ApiResponse(success=False, error="Failed to update password")
        
    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        return ApiResponse(success=False, error=str(e))
    
@router.post("/avatar", response_model=ApiResponse)
async def update_avatar(request: Request):
    """
    更新用户头像，将 Base64 编码的头像上传到 S3 并更新数据库中的头像 URL。

    Args:
        request: 包含 token 和 Base64 编码的图片数据。

    Returns:
        ApiResponse: 包含操作结果和更新后的用户信息。
    """
    try:
        request_data = await request.json()
        token = request_data.get("token")
        avatar_base64 = request_data.get("avatar")
        
        # 验证 token 和用户
        user_id = verify_token(token)
        if not user_id:
            return ApiResponse(success=False, error="Invalid token")

        # 解码 Base64 并上传到 S3（固定文件名以支持覆盖）
        with io.BytesIO(base64.b64decode(avatar_base64.split(",")[1])) as avatar_file:
            avatar_url = s3_manager.upload_file(
                file_obj=avatar_file,
                key=f"{user_id}.jpg",  # 固定文件名，确保覆盖
                folder="user_avatars",
                content_type="image/jpeg"
            )

        if not avatar_url:
            return ApiResponse(success=False, error="No avatar url")

        # 更新数据库（存储永久 URL）
        update_response = supabase.update("user_info", {"avatar": avatar_url}, {"user_id": user_id})
        
        if update_response.data and len(update_response.data) > 0:
            return ApiResponse(success=True, data={"user": update_response.data[0]})
        else:
            return ApiResponse(success=False, error="Failed to update profile")

    except Exception as e:
        logger.error(f"Update avatar error: {str(e)}")
        return ApiResponse(success=False, error=str(e))