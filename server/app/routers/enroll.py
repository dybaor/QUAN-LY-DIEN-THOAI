"""Ghép đôi Agent (KT-2), xoay vòng token có danh sách thu hồi (F5-3) và gỡ cài đặt hợp pháp (F4-MR1)."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import Principal, client_ip, require_device, require_parent
from ..models import Child, Device, EnrollmentCode, Parent, RevokedToken
from ..security import create_token_pair, decode_token, new_token, verify_secret
from ..websocket_manager import manager
from .auth import create_pairing_code, enforce_rate_limit, lock_remaining, login_limiter

router = APIRouter(prefix="/enroll", tags=["Enrollment"])


class CreateCodeRequest(BaseModel):
    child_id: int


class EnrollAgentRequest(BaseModel):
    code: str = Field(..., min_length=8, max_length=8)
    fingerprint: str = Field(..., min_length=8, max_length=255)
    device_name: str = Field(default="Windows PC", max_length=100)


class RefreshRequest(BaseModel):
    refresh_token: str


class UninstallRequest(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=128)


def issue_tokens(device: Device) -> dict:
    tokens = create_token_pair(device.id)
    return {key: tokens[key] for key in ("access_token", "refresh_token", "token_type", "expires_in")}


@router.post("/generate-code")
def generate_enrollment_code(req: CreateCodeRequest, principal: Principal = Depends(require_parent),
                             db: Session = Depends(get_db)):
    return create_pairing_code(req.child_id, principal, db)


@router.post("/verify")
def verify_and_enroll(req: EnrollAgentRequest, request: Request, db: Session = Depends(get_db)):
    """Agent gửi mã 8 ký tự + fingerprint máy để nhận device_id, cặp token và khóa ký chính sách."""
    enforce_rate_limit(login_limiter, request)
    entry = db.query(EnrollmentCode).filter(EnrollmentCode.code == req.code.strip().upper(),
                                            EnrollmentCode.is_used.is_(False)).first()
    if not entry:
        raise HTTPException(status_code=400, detail="Mã ghép đôi không hợp lệ hoặc đã dùng")
    if datetime.utcnow() > entry.expires_at:
        raise HTTPException(status_code=400, detail="Mã ghép đôi đã hết hạn (quá 10 phút)")
    entry.is_used = True
    # Ghép lại cùng một máy thì vô hiệu hóa bản ghi cũ để token cũ không còn dùng được.
    db.query(Device).filter(Device.fingerprint == req.fingerprint, Device.is_active.is_(True)).update(
        {Device.is_active: False})
    device = Device(id=str(uuid.uuid4()), child_id=entry.child_id, fingerprint=req.fingerprint,
                    name=req.device_name.strip() or "Windows PC", policy_key=new_token(), is_active=True,
                    last_seen=datetime.utcnow())
    db.add(device)
    child = db.get(Child, entry.child_id)
    audit.record(db, Principal("device", child_id=child.id, device_id=device.id, name=device.name), "device_paired",
                 child_id=child.id, ip=client_ip(request), new={"device": device.name})
    db.commit()
    return {"status": "success", "device_id": device.id, "child_id": child.id, "child_name": child.name,
            "policy_key": device.policy_key, **issue_tokens(device)}


@router.post("/refresh")
def refresh_tokens(req: RefreshRequest, db: Session = Depends(get_db)):
    """Đổi refresh token lấy cặp token mới; refresh token cũ bị đưa vào danh sách thu hồi."""
    claims = decode_token(req.refresh_token, "refresh")
    if not claims or db.get(RevokedToken, claims["jti"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token không hợp lệ hoặc đã bị thu hồi")
    device = db.get(Device, claims["sub"])
    if not device or not device.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Thiết bị đã bị gỡ ghép đôi")
    db.add(RevokedToken(jti=claims["jti"], device_id=device.id, expires_at=datetime.utcfromtimestamp(claims["exp"])))
    db.commit()
    return issue_tokens(device)


@router.post("/uninstall-authorize")
async def authorize_uninstall(req: UninstallRequest, request: Request, principal: Principal = Depends(require_device),
                              db: Session = Depends(get_db)):
    """Chỉ cho phép gỡ Agent khi có mật khẩu của phụ huynh sở hữu trẻ; ghi audit log và hủy ghép đôi."""
    enforce_rate_limit(login_limiter, request)
    child = db.get(Child, principal.child_id)
    parent = db.query(Parent).filter(Parent.username == req.username.strip()).first()
    if not parent or lock_remaining(parent.locked_until) or parent.id != child.parent_id \
            or not verify_secret(parent.hashed_password, req.password)[0]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Thông tin phụ huynh không đúng")
    device = db.get(Device, principal.device_id)
    device.is_active = False
    audit.record(db, Principal(parent.role, parent_id=parent.id, name=parent.username), "agent_uninstalled",
                 child_id=child.id, ip=client_ip(request), old={"device": device.name})
    db.commit()
    await manager.send_to_parents({"cmd": "device_status", "child_id": child.id, "device_id": device.id,
                                   "status": "uninstalled"}, child.id)
    return {"status": "success", "message": "Phụ huynh đã cho phép gỡ cài đặt"}
