from sqlalchemy import Column, String, Boolean, DateTime, func
from apps.api.database.models.base import BaseModel

class SystemSetting(BaseModel):
    __tablename__ = "system_settings"

    category = Column(String(50), nullable=False, index=True) # 예: auth, llm, map
    key_name = Column(String(100), nullable=False, unique=True, index=True) # 예: KAKAO_CLIENT_SECRET
    key_value = Column(String, nullable=False) # 암호화된 값 저장
    is_encrypted = Column(Boolean, default=True, nullable=False)
    description = Column(String(255), nullable=True)
    updated_by = Column(String(100), nullable=True) # 수정한 관리자 ID 또는 이메일
    
    # BaseModel에 id, created_at, updated_at이 포함되어 있다고 가정함
