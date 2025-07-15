from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from easydict import EasyDict
from enum import Enum

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
    
    # 获取Google Scholar信息
    "START_FETCH_A_GOOGLE_SCHOLAR_URL":"start_fetch_a_google_scholar_url",
    "STOP_FETCH_A_GOOGLE_SCHOLAR_URL":"stop_fetch_a_google_scholar_url",
    "FETCHED_GOOGLE_SCHOLAR_BASIC_INFO":"fetched_google_scholar_basic_info",
    "UPDATE_FETCH_A_GOOGLE_SCHOLAR_URL_PROCESS":"update_fetch_a_google_scholar_url_process",
    "FETCHED_COMPLETED_WITH_PAPERS_INFO":"fetched_completed_with_papers_info",
    "FAILED_FETCH_A_GOOGLE_SCHOLAR_URL":"failed_fetch_a_google_scholar_url"
}
WS_EVENTS_DICT=EasyDict(WS_EVENTS)

class GoogleSearchRequest(BaseModel):
    url: str
    searchId: str
    clientId: Optional[str] = None

# Paper models
class PaperBase(BaseModel):
    title: str
    authors: List[str]
    year: int
    date: str  # 格式: YYYY-MM-DD
    url: str # 论文url
    pdf_url: Optional[str] = None # 论文pdf url
    citations: Optional[int] = None
    publisher: Optional[str] = None
    paper_type: Optional[str] = None  # "Journal", "Conference", "Preprint"
    description: Optional[str] = None
    class Config:
        """Pydantic config"""
        orm_mode = True

class URLItemStatus(str, Enum):
    ERROR = "error"
    PENDING = "pending"
    COLLECTING_INFO = "collecting_info"
    COLLECTED_INFO = "collected_info"
    SEARCHING_PAPERS = "searching_papers"
    COMPLETED = "completed"

class URLItem(BaseModel):
    search_id: str
    client_id: str
    url: str
    author_name: str
    status: str
    progress: float
    fetched_paper_count: Optional[int] = None
    total_paper_count: Optional[int] = None
    papers_urls: List[str]
    papers: List[PaperBase]
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    thread_id: int
    class Config:
        """Pydantic config"""
        orm_mode = True


