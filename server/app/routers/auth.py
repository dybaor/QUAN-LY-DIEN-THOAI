"""Tài khoản phụ huynh (F5-1, F5-2), quản lý nhiều trẻ (F4-1) và thiết bị đã ghép đôi."""

import re
import secrets
import string
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit, config
from ..categories import CATEGORIES, DEFAULT_CHILD_AGE, default_blocked_categories
from ..database import get_db
from ..deps import (
    Principal, authorize_child, client_ip, create_session, owned_child_ids, require_admin,
    require_parent, resolve_principal, revoke_session,
)
from ..models import (
    ROLE_ADMIN, ROLE_CHILD, ROLE_PARENT, AuthSession, Child, Device, EnrollmentCode, Parent, Policy,
)
from ..security import hash_secret, verify_secret
from ..services import get_or_create_policy
from ..websocket_manager import manager

router = APIRouter(tags=["Tài khoản & Hồ sơ trẻ"])

PIN_PATTERN = re.compile(r"^\d{4,6}$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{3,50}$")
PLACEHOLDER_PASSWORD = "hashed_dummy_password"


class RateLimiter:
    """Giới hạn số yêu cầu theo IP trong cửa sổ trượt 60 giây (một tiến trình máy chủ)."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit, self.window = limit, window
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()


login_limiter = RateLimiter(config.LOGIN_RATE_PER_MINUTE)
pin_limiter = RateLimiter(config.LOGIN_RATE_PER_MINUTE)


def enforce_rate_limit(limiter: RateLimiter, request: Request):
    if not limiter.allow(client_ip(request)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Quá nhiều yêu cầu. Vui lòng thử lại sau 1 phút.")


def validate_password(password: str):
    if len(password) < config.PASSWORD_MIN_LENGTH:
        raise HTTPException(422, f"Mật khẩu phải có ít nhất {config.PASSWORD_MIN_LENGTH} ký tự")


def validate_pin(pin: str):
    if not PIN_PATTERN.match(pin or ""):
        raise HTTPException(422, "Mã PIN mở khóa phải gồm 4 đến 6 chữ số")


def lock_remaining(locked_until: Optional[datetime]) -> int:
    if not locked_until:
        return 0
    return max(0, int((locked_until - datetime.utcnow()).total_seconds()))


def has_account(db: Session) -> bool:
    return db.query(Parent).filter(Parent.hashed_password.like("$argon2%")).first() is not None


def child_summary(db: Session, child: Child) -> dict:
    policy = db.query(Policy).filter(Policy.child_id == child.id).first()
    return {
        "id": child.id,
        "name": child.name or "",
        "age": child.age,
        "has_pin": bool(policy and policy.lock_password_hash),
        "devices": [
            {"id": d.id, "name": d.name, "last_seen": d.last_seen.isoformat() + "Z" if d.last_seen else None,
             "online": bool(manager.online_keys(f"agent_{d.id}")), "ui_present": bool(d.ui_present)}
            for d in child.devices if d.is_active
        ],
        "portal_online": bool(manager.online_keys("child_", child.id)),
    }


def account_payload(db: Session, principal: Principal) -> dict:
    ids = owned_child_ids(db, principal)
    children = db.query(Child).filter(Child.id.in_(ids)).order_by(Child.id).all() if ids else []
    return {
        "authenticated": True,
        "username": principal.name,
        "role": principal.role,
        "csrf_token": principal.session.csrf_token if principal.session else None,
        "children": [child_summary(db, child) for child in children],
        "categories": CATEGORIES,
    }


def set_child_pin(policy: Policy, pin: str):
    validate_pin(pin)
    policy.lock_password_hash = hash_secret(pin)
    policy.lock_pin = None
    policy.pin_failed_count = 0
    policy.pin_locked_until = None


# ---------- Schemas ----------
class RegisterSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., max_length=128)
    child_name: str = Field(..., min_length=1, max_length=100)
    child_age: int = Field(default=DEFAULT_CHILD_AGE, ge=3, le=17)
    pin: str


class LoginSchema(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=128)


class ChangePasswordSchema(BaseModel):
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., max_length=128)


class ChildCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    age: int = Field(default=DEFAULT_CHILD_AGE, ge=3, le=17)
    pin: str


class ChildUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    age: Optional[int] = Field(default=None, ge=3, le=17)
    pin: Optional[str] = None


# ---------- Tài khoản phụ huynh ----------
@router.get("/api/auth/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    principal = resolve_principal(db, request, {ROLE_PARENT, ROLE_ADMIN})
    if principal:
        return account_payload(db, principal)
    return {"authenticated": False, "has_account": has_account(db)}


@router.post("/api/auth/register")
def register(req: RegisterSchema, request: Request, response: Response, db: Session = Depends(get_db)):
    """Tạo tài khoản phụ huynh đầu tiên (vai trò admin) cùng hồ sơ trẻ đầu tiên."""
    enforce_rate_limit(login_limiter, request)
    if has_account(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Hệ thống đã có tài khoản phụ huynh. Vui lòng đăng nhập.")
    username = req.username.strip()
    if not USERNAME_PATTERN.match(username):
        raise HTTPException(422, "Tên đăng nhập chỉ gồm chữ, số và . _ @ - (3–50 ký tự)")
    validate_password(req.password)
    validate_pin(req.pin)

    # Nhận lại hồ sơ mẫu của phiên bản cũ (nếu có) để giữ dữ liệu trẻ đã ghi nhận.
    parent = db.query(Parent).filter(Parent.hashed_password == PLACEHOLDER_PASSWORD).first() or Parent()
    parent.username = username
    parent.hashed_password = hash_secret(req.password)
    parent.role = ROLE_ADMIN
    parent.failed_login_count = 0
    db.add(parent)
    db.flush()

    child = db.query(Child).filter(Child.parent_id == parent.id).order_by(Child.id).first()
    if not child:
        child = Child(parent_id=parent.id)
        db.add(child)
    child.name = req.child_name.strip()
    child.age = req.child_age
    db.flush()
    policy = db.query(Policy).filter(Policy.child_id == child.id).first() or Policy(child_id=child.id)
    policy.child_name = child.name
    policy.blocked_categories = default_blocked_categories(child.age)
    set_child_pin(policy, req.pin)
    db.add(policy)
    db.commit()

    session = create_session(db, response, request, role=ROLE_ADMIN, parent_id=parent.id)
    principal = Principal(ROLE_ADMIN, parent_id=parent.id, name=parent.username, session=session)
    audit.record(db, principal, "account_created", ip=client_ip(request), new={"username": username})
    audit.record(db, principal, "child_created", child_id=child.id, ip=client_ip(request),
                 new={"name": child.name, "age": child.age}, commit=True)
    return account_payload(db, principal)


@router.post("/api/auth/login")
def login(req: LoginSchema, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(login_limiter, request)
    parent = db.query(Parent).filter(Parent.username == req.username.strip()).first()
    if parent and lock_remaining(parent.locked_until):
        minutes = -(-lock_remaining(parent.locked_until) // 60)
        raise HTTPException(status.HTTP_423_LOCKED, f"Tài khoản tạm khóa do nhập sai nhiều lần. Thử lại sau {minutes} phút.")
    valid, rehash = verify_secret(parent.hashed_password if parent else None, req.password)
    if not parent or not valid:
        if parent:
            parent.failed_login_count = (parent.failed_login_count or 0) + 1
            if parent.failed_login_count >= config.MAX_FAILED_LOGINS:
                parent.failed_login_count = 0
                parent.locked_until = datetime.utcnow() + timedelta(minutes=config.LOCKOUT_MINUTES)
                audit.record(db, Principal(parent.role, parent_id=parent.id, name=parent.username),
                             "login_locked", ip=client_ip(request))
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tên đăng nhập hoặc mật khẩu không đúng")
    parent.failed_login_count = 0
    parent.locked_until = None
    if rehash:
        parent.hashed_password = hash_secret(req.password)
    db.commit()
    session = create_session(db, response, request, role=parent.role, parent_id=parent.id)
    return account_payload(db, Principal(parent.role, parent_id=parent.id, name=parent.username, session=session))


@router.post("/api/auth/logout")
def logout(response: Response, principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    revoke_session(db, principal.session)
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return {"status": "success"}


@router.get("/api/auth/me")
def me(principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    return account_payload(db, principal)


@router.post("/api/auth/change-password")
def change_password(req: ChangePasswordSchema, request: Request, response: Response,
                    principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    parent = db.get(Parent, principal.parent_id)
    if not verify_secret(parent.hashed_password, req.current_password)[0]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Mật khẩu hiện tại không đúng")
    validate_password(req.new_password)
    parent.hashed_password = hash_secret(req.new_password)
    # Hủy mọi phiên khác của tài khoản
    db.query(AuthSession).filter(AuthSession.parent_id == parent.id, AuthSession.revoked_at.is_(None)).update(
        {AuthSession.revoked_at: datetime.utcnow()})
    audit.record(db, principal, "password_changed", ip=client_ip(request))
    db.commit()
    session = create_session(db, response, request, role=parent.role, parent_id=parent.id)
    return account_payload(db, Principal(parent.role, parent_id=parent.id, name=parent.username, session=session))


# ---------- Hồ sơ trẻ ----------
@router.get("/api/children")
def list_children(principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    return account_payload(db, principal)["children"]


@router.post("/api/children")
async def create_child(req: ChildCreateSchema, request: Request, principal: Principal = Depends(require_parent),
                       db: Session = Depends(get_db)):
    child = Child(parent_id=principal.parent_id, name=req.name.strip(), age=req.age)
    db.add(child)
    db.flush()
    policy = Policy(child_id=child.id, child_name=child.name, blocked_categories=default_blocked_categories(req.age))
    set_child_pin(policy, req.pin)
    db.add(policy)
    audit.record(db, principal, "child_created", child_id=child.id, ip=client_ip(request),
                 new={"name": child.name, "age": child.age})
    db.commit()
    manager.update_scope(f"parent_{principal.parent_id}_", owned_child_ids(db, principal))
    return child_summary(db, child)


@router.put("/api/children/{child_id}")
async def update_child(child_id: int, req: ChildUpdateSchema, request: Request,
                       principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    policy = get_or_create_policy(db, child)
    before = {"name": child.name, "age": child.age}
    if req.name is not None:
        child.name = policy.child_name = req.name.strip()
    if req.age is not None:
        child.age = req.age
    after = {"name": child.name, "age": child.age}
    if before != after:
        old, new = audit.diff(before, after)
        audit.record(db, principal, "child_updated", child_id=child.id, ip=client_ip(request), old=old, new=new)
    if req.pin:
        set_child_pin(policy, req.pin)
        audit.record(db, principal, "pin_changed", child_id=child.id, ip=client_ip(request))
    policy.version += 1
    policy.updated_at = datetime.utcnow()
    db.commit()
    await manager.notify_child({"cmd": "settings_updated", "child_id": child.id, "child_name": child.name,
                                "version": policy.version}, child.id)
    return child_summary(db, child)


@router.post("/api/children/{child_id}/pairing-code")
def create_pairing_code(child_id: int, principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    """Sinh mã ghép đôi 8 ký tự, hạn 10 phút, dùng cho Agent (KT-2) hoặc cổng học tập của trẻ."""
    child = authorize_child(db, principal, child_id)
    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    expires = datetime.utcnow() + timedelta(minutes=10)
    db.add(EnrollmentCode(code=code, child_id=child.id, expires_at=expires, is_used=False))
    db.commit()
    return {"code": code, "child_id": child.id, "expires_at": expires.isoformat() + "Z", "expires_in": 600}


@router.post("/api/children/{child_id}/local-session")
def open_local_child_session(child_id: int, request: Request, response: Response,
                             principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    """Mở cổng học tập của trẻ trên chính trình duyệt này (dùng khi demo trên một máy)."""
    child = authorize_child(db, principal, child_id)
    create_session(db, response, request, role=ROLE_CHILD, child_id=child.id)
    audit.record(db, principal, "portal_paired", child_id=child.id, ip=client_ip(request),
                 new={"method": "Phiên trên trình duyệt của phụ huynh"}, commit=True)
    return {"status": "success", "child_id": child.id}


@router.delete("/api/children/{child_id}/devices/{device_id}")
async def remove_device(child_id: int, device_id: str, request: Request,
                        principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    device = db.get(Device, device_id)
    if not device or device.child_id != child.id:
        raise HTTPException(404, "Không tìm thấy thiết bị")
    device.is_active = False  # Mọi access/refresh token của thiết bị bị từ chối từ thời điểm này
    audit.record(db, principal, "device_removed", child_id=child.id, ip=client_ip(request), old={"device": device.name})
    db.commit()
    await manager.send_command(f"agent_{device.id}", {"cmd": "device_removed"})
    return {"status": "success"}


@router.post("/api/children/{child_id}/portal-logout")
async def revoke_portal_sessions(child_id: int, principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    """Hủy mọi phiên cổng học tập của trẻ (bắt buộc ghép đôi lại)."""
    child = authorize_child(db, principal, child_id)
    db.query(AuthSession).filter(AuthSession.child_id == child.id, AuthSession.revoked_at.is_(None)).update(
        {AuthSession.revoked_at: datetime.utcnow()})
    db.commit()
    await manager.send_to_children({"cmd": "session_revoked", "child_id": child.id}, child.id)
    return {"status": "success"}


@router.get("/api/admin/parents")
def list_parents(principal: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return [{"id": p.id, "username": p.username, "role": p.role, "children": len(p.children)}
            for p in db.query(Parent).filter(Parent.hashed_password.like("$argon2%")).all()]
