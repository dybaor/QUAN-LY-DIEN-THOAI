import secrets
import string
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..database import get_db
from ..models import EnrollmentCode, Device, Child
from ..auth import create_token_pair

router = APIRouter(prefix="/enroll", tags=["Enrollment"])

class CreateCodeRequest(BaseModel):
    child_id: int

class EnrollAgentRequest(BaseModel):
    code: str
    fingerprint: str
    device_name: str = "Child-PC"

# 1. Phụ huynh sinh mã 8 ký tự trên Dashboard (Hạn 10 phút)
@router.post("/generate-code")
def generate_enrollment_code(req: CreateCodeRequest, db: Session = Depends(get_db)):
    # Sinh mã 8 ký tự chữ và số ngẫu nhiên
    code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    expires = datetime.utcnow() + timedelta(minutes=10)
    
    enroll_entry = EnrollmentCode(
        code=code,
        child_id=req.child_id,
        expires_at=expires,
        is_used=False
    )
    db.add(enroll_entry)
    db.commit()
    return {"code": code, "expires_at": expires}

# 2. Agent máy con gửi mã và fingerprint lên để ghép đôi
@router.post("/verify")
def verify_and_enroll(req: EnrollAgentRequest, db: Session = Depends(get_db)):
    enroll_entry = db.query(EnrollmentCode).filter(
        EnrollmentCode.code == req.code,
        EnrollmentCode.is_used == False
    ).first()

    if not enroll_entry:
        raise HTTPException(status_code=400, detail="Mã ghép đôi không hợp lệ hoặc đã dùng")
    
    if datetime.utcnow() > enroll_entry.expires_at:
        raise HTTPException(status_code=400, detail="Mã ghép đôi đã hết hạn (quá 10 phút)")

    # Đánh dấu mã đã dùng
    enroll_entry.is_used = True
    
    # Tạo thiết bị mới
    device_id = str(uuid.uuid4())
    new_device = Device(
        id=device_id,
        child_id=enroll_entry.child_id,
        fingerprint=req.fingerprint,
        name=req.device_name,
        is_active=True
    )
    db.add(new_device)
    db.commit()

    # Tạo cặp Access Token (ngắn hạn: 15p) và Refresh Token (dài hạn)
    tokens = create_token_pair(device_id=device_id)

    return {
        "status": "success",
        "device_id": device_id,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer"
    }