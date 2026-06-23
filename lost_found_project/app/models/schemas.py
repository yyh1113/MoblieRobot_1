from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional

class ReleaseRequest(BaseModel):
    """
    Schema for releasing a found item to its owner (recipient).
    """
    recipient_name: str = Field(..., min_length=1, max_length=50, description="수령인 이름")
    recipient_phone: str = Field(..., min_length=7, max_length=20, description="수령인 연락처")
    recipient_student_id: str = Field(..., min_length=5, max_length=20, description="수령인 학번")

class MatchConfirmRequest(BaseModel):
    """
    Schema for confirming an AI recommendation match.
    """
    lost_item_id: int = Field(..., description="매칭 확정할 습득물(lost_items)의 ID")

class FoundItemCreate(BaseModel):
    """
    Validation schema for new found items.
    """
    category: str
    sub_category: str
    item_name: str
    found_date: date
    found_location_building: str
    found_location_detail: str
    detail_memo: Optional[str] = None
    vlm_keywords: str

class AndroidSearchRequest(BaseModel):
    """
    Structured search query request sent by the Android Kiosk / User client.
    """
    phase: str
    category: str
    subCategory: Optional[str] = None
    lostStartDate: Optional[str] = None
    lostEndDate: Optional[str] = None
    lostLocation: Optional[str] = None
    detail: str
    imageSkipped: bool
