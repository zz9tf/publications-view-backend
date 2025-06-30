from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from easydict import EasyDict

# 模型定义
class ApiResponse(BaseModel):
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    message: Optional[str] = None

class User(BaseModel):
    user_id: str
    username: str
    email: str
    phone: Optional[str] = None
    avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime

# Auth request models
class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    user: User
    token: str

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    phone: Optional[str] = None

class RegisterResponse(BaseModel):
    user: User
    token: str

class TokenVerifyRequest(BaseModel):
    token: str

class TokenVerifyResponse(BaseModel):
    user: User

class BaseEvent(BaseModel):
    event: str
    data: Optional[Dict[str, Any]] = None

API_PATHS={
    "LOGIN":"/user/login",
    "REGISTER":"/user/register",
    "LOGOUT":"/user/logout",
    "VERIFY_TOKEN":"/user/verify-token",
    "UPDATE_AVATAR":"/user/avatar",
    "SOCIAL_LOGIN":{"GOOGLE": "/user/social-login/google"},
    "FETCH_URL_ITEM":"/url-item/fetch"
}
API_PATHS_DICT=EasyDict(API_PATHS)

WS_EVENTS={
    "CLIENT_CONNECTED":"client_connected",
    "UPDATE_URL_ITEM_FETCHING_PROCESS":"update_url_item_fetching_process"
}
WS_EVENTS_DICT=EasyDict(WS_EVENTS)

class GoogleSearchRequest(BaseModel):
    url: str
    searchId: str
    clientId: Optional[str] = None

class URLItem(BaseModel):
    search_id: str
    url: str
    short_description: str
    progress: int
    status: str
    fetched_paper_count: int
    total_paper_count: int
    class Config:
        """Pydantic config"""
        orm_mode = True

# Paper models
class PaperBase(BaseModel):
    title: str
    authors: List[str]
    year: int
    date: str  # 格式: YYYY-MM-DD
    citations: Optional[int] = None
    publisher: Optional[str] = None
    paper_type: Optional[str] = None  # "Journal", "Conference", "Preprint"
    description: Optional[str] = None
