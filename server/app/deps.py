"""Xác thực & phân quyền 3 vai trò (parent / child-view / admin) cùng token thiết bị, chống IDOR và CSRF."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response, WebSocket, status
from sqlalchemy.orm import Session

from . import config
from .database import get_db
from .models import (
    ROLE_ADMIN, ROLE_CHILD, ROLE_DEVICE, ROLE_PARENT,
    AuthSession, Child, Device, Parent, RevokedToken,
)
from .security import constant_equals, decode_token, new_token, token_digest

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class Principal:
    role: str
    parent_id: Optional[int] = None
    child_id: Optional[int] = None
    device_id: Optional[str] = None
    name: Optional[str] = None
    session: Optional[AuthSession] = None

    @property
    def is_parent(self) -> bool:
        return self.role in (ROLE_PARENT, ROLE_ADMIN)

    @property
    def actor_id(self) -> str:
        return str(self.device_id or self.parent_id or self.child_id or "")


def client_ip(request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- Phiên cookie ----------
def create_session(db: Session, response: Response, request: Request, *, role: str,
                   parent_id: Optional[int] = None, child_id: Optional[int] = None) -> AuthSession:
    token = new_token()
    lifetime = timedelta(hours=config.SESSION_HOURS) if role != ROLE_CHILD else timedelta(days=config.CHILD_SESSION_DAYS)
    session = AuthSession(
        token_hash=token_digest(token), role=role, parent_id=parent_id, child_id=child_id,
        csrf_token=new_token(), client_ip=client_ip(request), expires_at=datetime.utcnow() + lifetime,
    )
    db.add(session)
    db.commit()
    cookie = config.CHILD_SESSION_COOKIE if role == ROLE_CHILD else config.SESSION_COOKIE
    response.set_cookie(
        cookie, token, max_age=int(lifetime.total_seconds()), httponly=True,
        secure=config.COOKIE_SECURE or request.url.scheme == "https", samesite="strict", path="/",
    )
    return session


def revoke_session(db: Session, session: Optional[AuthSession]):
    if session and not session.revoked_at:
        session.revoked_at = datetime.utcnow()
        db.commit()


def _load_session(db: Session, token: Optional[str], role_filter: Iterable[str]) -> Optional[AuthSession]:
    if not token:
        return None
    session = db.get(AuthSession, token_digest(token))
    if not session or session.revoked_at or session.expires_at < datetime.utcnow() or session.role not in role_filter:
        return None
    return session


def _same_origin(request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    return urlsplit(origin).netloc == request.headers.get("host")


def _principal_from_session(db: Session, session: AuthSession) -> Optional[Principal]:
    if session.role == ROLE_CHILD:
        child = db.get(Child, session.child_id)
        return Principal(ROLE_CHILD, child_id=child.id, name=child.name, session=session) if child else None
    parent = db.get(Parent, session.parent_id)
    if not parent:
        return None
    return Principal(parent.role, parent_id=parent.id, name=parent.username, session=session)


def _check_csrf(request: Request, session: AuthSession):
    if request.method in UNSAFE_METHODS:
        if not _same_origin(request) or not constant_equals(request.headers.get("x-csrf-token"), session.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Thiếu hoặc sai mã chống giả mạo yêu cầu (CSRF)")


def _device_principal(db: Session, request) -> Optional[Principal]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    claims = decode_token(header[7:].strip(), "access")
    if not claims or db.get(RevokedToken, claims["jti"]):
        return None
    device = db.get(Device, claims["sub"])
    if not device or not device.is_active:
        return None
    return Principal(ROLE_DEVICE, child_id=device.child_id, device_id=device.id, name=device.name)


def resolve_principal(db: Session, request: Request, roles: Iterable[str]) -> Optional[Principal]:
    roles = set(roles)
    if ROLE_DEVICE in roles:
        device = _device_principal(db, request)
        if device:
            return device
    parent_roles = roles & {ROLE_PARENT, ROLE_ADMIN}
    if parent_roles:
        session = _load_session(db, request.cookies.get(config.SESSION_COOKIE), parent_roles)
        principal = session and _principal_from_session(db, session)
        if principal and principal.role in roles:
            _check_csrf(request, session)
            return principal
    if ROLE_CHILD in roles:
        session = _load_session(db, request.cookies.get(config.CHILD_SESSION_COOKIE), {ROLE_CHILD})
        principal = session and _principal_from_session(db, session)
        if principal:
            _check_csrf(request, session)
            return principal
    return None


def require(*roles: str):
    """Dependency yêu cầu một trong các vai trò; quản trị viên luôn có quyền của phụ huynh."""
    accepted = set(roles)
    if ROLE_PARENT in accepted:
        accepted.add(ROLE_ADMIN)

    def dependency(request: Request, db: Session = Depends(get_db)) -> Principal:
        principal = resolve_principal(db, request, accepted)
        if not principal:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Vui lòng đăng nhập")
        return principal

    return dependency


require_parent = require(ROLE_PARENT)
require_admin = require(ROLE_ADMIN)
require_child = require(ROLE_CHILD)
require_device = require(ROLE_DEVICE)
require_parent_or_child = require(ROLE_PARENT, ROLE_CHILD)
require_child_or_device = require(ROLE_CHILD, ROLE_DEVICE)


def authorize_child(db: Session, principal: Principal, child_id: Optional[int]) -> Child:
    """Chống IDOR: chỉ cho phép truy cập trẻ thuộc quyền sở hữu của người gọi."""
    if principal.role in (ROLE_CHILD, ROLE_DEVICE):
        if child_id is not None and child_id != principal.child_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy hồ sơ trẻ")
        child_id = principal.child_id
    child = db.get(Child, child_id) if child_id is not None else None
    # Quản trị viên chỉ có thêm quyền quản trị hệ thống, không được xem dữ liệu trẻ của gia đình khác.
    if not child or (principal.is_parent and child.parent_id != principal.parent_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy hồ sơ trẻ")
    return child


def owned_child_ids(db: Session, principal: Principal) -> list:
    if principal.is_parent:
        return [row[0] for row in db.query(Child.id).filter(Child.parent_id == principal.parent_id).all()]
    return [principal.child_id] if principal.child_id else []


# ---------- WebSocket ----------
def websocket_principal(db: Session, websocket: WebSocket, roles: Iterable[str]) -> Optional[Principal]:
    """Xác thực WebSocket: cookie (kèm kiểm tra Origin chống CSWSH) hoặc Bearer token của Agent."""
    roles = set(roles)
    if ROLE_DEVICE in roles:
        device = _device_principal(db, websocket)
        if device:
            return device
    if not _same_origin(websocket):
        return None
    parent_roles = roles & {ROLE_PARENT, ROLE_ADMIN}
    if parent_roles:
        session = _load_session(db, websocket.cookies.get(config.SESSION_COOKIE), parent_roles)
        if session:
            return _principal_from_session(db, session)
    if ROLE_CHILD in roles:
        session = _load_session(db, websocket.cookies.get(config.CHILD_SESSION_COOKIE), {ROLE_CHILD})
        if session:
            return _principal_from_session(db, session)
    return None
