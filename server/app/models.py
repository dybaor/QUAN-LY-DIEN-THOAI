import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .categories import DEFAULT_CHILD_AGE, default_blocked_categories
from .database import Base
from .security import EncryptedString

utcnow = datetime.datetime.utcnow

ROLE_PARENT = "parent"
ROLE_ADMIN = "admin"
ROLE_CHILD = "child-view"
ROLE_DEVICE = "device"


class Parent(Base):
    __tablename__ = "parents"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)  # Argon2id
    role = Column(String(20), default=ROLE_PARENT, nullable=False)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    children = relationship("Child", back_populates="parent")

    @property
    def has_password(self) -> bool:
        return bool(self.hashed_password and self.hashed_password.startswith("$argon2"))


class Child(Base):
    __tablename__ = "children"
    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("parents.id"), nullable=False)
    name = Column(EncryptedString(255), default=None, nullable=True)
    age = Column(Integer, nullable=False, default=DEFAULT_CHILD_AGE)
    created_at = Column(DateTime, default=utcnow)

    parent = relationship("Parent", back_populates="children")
    devices = relationship("Device", back_populates="child")


class Device(Base):
    __tablename__ = "devices"
    id = Column(String(64), primary_key=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    fingerprint = Column(String(255), nullable=False)
    name = Column(String(100), default="Windows PC")
    policy_key = Column(EncryptedString(255), nullable=True)  # Khóa HMAC ký chính sách riêng từng thiết bị
    is_active = Column(Boolean, default=True)
    ui_present = Column(Boolean, default=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    child = relationship("Child", back_populates="devices")


class EnrollmentCode(Base):
    __tablename__ = "enrollment_codes"
    code = Column(String(8), primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)


class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False, unique=True)
    child_name = Column(EncryptedString(255), default=None, nullable=True)
    lock_pin = Column(String(50), default=None, nullable=True)  # Không còn sử dụng; giữ cột để nâng cấp DB cũ
    lock_password_hash = Column(String(255), default=None, nullable=True)  # Argon2id của mã PIN mở khóa
    pin_failed_count = Column(Integer, default=0, nullable=False)
    pin_locked_until = Column(DateTime, nullable=True)
    version = Column(Integer, default=1)
    daily_quota_weekday_min = Column(Integer, default=120)
    daily_quota_weekend_min = Column(Integer, default=180)
    schedule_matrix = Column(String, default="1" * 336)  # 7 ngày x 48 khung 30 phút
    blocked_apps = Column(String, default="")
    blocked_domains = Column(String, default="")
    blocked_categories = Column(String(255), default=default_blocked_categories(DEFAULT_CHILD_AGE))
    paused_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utcnow)


class DeviceEvent(Base):
    __tablename__ = "device_events"
    id = Column(Integer, primary_key=True, index=True)
    ts = Column(DateTime, nullable=False, default=utcnow)
    device_id = Column(String(64), nullable=False)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    type = Column(String(50), nullable=False)
    subject = Column(String(255), nullable=False)
    duration_sec = Column(Integer, default=0)
    policy_id = Column(Integer, nullable=True)
    idempotency_key = Column(String(64), nullable=True)  # Duy nhất (index tạo trong database.run_migrations)


class WebDailyUsage(Base):
    __tablename__ = "web_daily_usage"
    child_id = Column(Integer, ForeignKey("children.id"), primary_key=True)
    day = Column(Date, primary_key=True)
    used_seconds = Column(Float, nullable=False)
    last_seen = Column(Float, nullable=False)


class AgentDailyUsage(Base):
    __tablename__ = "agent_daily_usage"
    child_id = Column(Integer, ForeignKey("children.id"), primary_key=True)
    day = Column(Date, primary_key=True)
    device_id = Column(String(64), primary_key=True)
    used_seconds = Column(Integer, nullable=False)


class ChildWindowLock(Base):
    __tablename__ = "child_window_locks"
    child_id = Column(Integer, ForeignKey("children.id"), primary_key=True)
    reason = Column(String(255), nullable=False)


class DailyTimeAdjustment(Base):
    __tablename__ = "daily_time_adjustments"
    child_id = Column(Integer, ForeignKey("children.id"), primary_key=True)
    day = Column(Date, primary_key=True)
    minutes = Column(Integer, nullable=False)


class TimeRequest(Base):
    __tablename__ = "time_requests"
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    device_id = Column(String(64), nullable=True)
    requested_minutes = Column(Integer, default=15)
    reason = Column(String(255), default="Xin thêm thời gian")
    status = Column(String(20), default="pending")  # pending, approved, rejected
    granted_minutes = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    resolved_at = Column(DateTime, nullable=True)


class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, nullable=False)
    device_id = Column(String(64), default="web-portal")
    start_time = Column(DateTime, default=utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_sec = Column(Integer, default=0)
    status = Column(String(50), default="Đang theo dõi")


class AccessHistoryLog(Base):
    __tablename__ = "access_history_logs"
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, nullable=False)
    device_id = Column(String(64), default="web-portal")
    ts = Column(DateTime, default=utcnow)
    target_name = Column(String(255), nullable=False)
    target_type = Column(String(50), default="Trang web")  # "Ứng dụng", "Trang web", "Tìm kiếm"
    status = Column(String(50), default="allowed")  # "allowed", "blocked"


class AuthSession(Base):
    """Phiên đăng nhập phía máy chủ (phụ huynh hoặc cổng trẻ) để hủy được khi đăng xuất."""

    __tablename__ = "auth_sessions"
    token_hash = Column(String(64), primary_key=True)
    role = Column(String(20), nullable=False)
    parent_id = Column(Integer, ForeignKey("parents.id"), nullable=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=True)
    csrf_token = Column(String(64), nullable=False)
    client_ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class RevokedToken(Base):
    """Danh sách thu hồi JWT của Agent (refresh token đã xoay vòng hoặc thiết bị bị gỡ)."""

    __tablename__ = "revoked_tokens"
    jti = Column(String(64), primary_key=True)
    device_id = Column(String(64), nullable=True)
    expires_at = Column(DateTime, nullable=False)


class AuditLog(Base):
    """Nhật ký kiểm toán (NT5): ai thay đổi gì, lúc nào, từ đâu. Trẻ được xem nhật ký của mình."""

    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    ts = Column(DateTime, default=utcnow, index=True)
    child_id = Column(Integer, nullable=True, index=True)
    actor_role = Column(String(20), nullable=False)
    actor_id = Column(String(64), nullable=True)
    actor_name = Column(String(100), nullable=True)
    client_ip = Column(String(64), nullable=True)
    action = Column(String(64), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
