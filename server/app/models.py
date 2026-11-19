import datetime
from sqlalchemy import Column, String, Integer, DateTime, Date, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .database import Base

class Parent(Base):
    __tablename__ = "parents"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)  # Argon2id
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    children = relationship("Child", back_populates="parent")

class Child(Base):
    __tablename__ = "children"
    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("parents.id"), nullable=False)
    name = Column(String(100), default=None, nullable=True)  # Tên trẻ (mặc định NULL)
    age = Column(Integer, nullable=False, default=10)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    parent = relationship("Parent", back_populates="children")
    devices = relationship("Device", back_populates="child")

class Device(Base):
    __tablename__ = "devices"
    id = Column(String(64), primary_key=True)  # device_id dạng UUID
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    fingerprint = Column(String(255), nullable=False)
    name = Column(String(100), default="Windows PC")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    child = relationship("Child", back_populates="devices")

class EnrollmentCode(Base):
    __tablename__ = "enrollment_codes"
    code = Column(String(8), primary_key=True, index=True)  # Mã 8 ký tự
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)          # Hạn 10 phút
    is_used = Column(Boolean, default=False)

    # Thêm vào cuối file app/models.py:

class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    child_name = Column(String(100), default=None, nullable=True)           # Tên của trẻ (mặc định NULL)
    lock_pin = Column(String(50), default=None, nullable=True)               # Mật khẩu / mã PIN khóa máy (mặc định NULL)
    lock_password_hash = Column(String(255), default=None, nullable=True)   # Mã băm SHA-256 mật khẩu bảo vệ (mặc định NULL)
    version = Column(Integer, default=1)  # Đánh số phiên bản chính sách
    daily_quota_weekday_min = Column(Integer, default=120)
    daily_quota_weekend_min = Column(Integer, default=180)
    schedule_matrix = Column(String, default="1"*336)       # Ma trận 7x48 = 336 ký tự (1: cho phép, 0: khóa)
    blocked_apps = Column(String, default="")              # Danh sách SHA-256 / tên app cấm
    blocked_domains = Column(String, default="")           # Danh sách domain cấm
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

class DeviceEvent(Base):
    __tablename__ = "device_events"
    id = Column(Integer, primary_key=True, index=True)
    
    # 7 trường dữ liệu bắt buộc theo đề cương:
    ts = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=False)
    child_id = Column(Integer, ForeignKey("children.id"), nullable=False)
    type = Column(String(50), nullable=False) # app_start, app_stop, locked, blocked_domain, ...
    subject = Column(String(255), nullable=False) # Tên app hoặc Domain cấp 2 (không lưu URL đầy đủ)
    duration_sec = Column(Integer, default=0)
    policy_id = Column(Integer, nullable=True)


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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class MonitoringSession(Base):
    __tablename__ = "monitoring_sessions"
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, default=1)
    device_id = Column(String(64), default="CHILD-PC")
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_sec = Column(Integer, default=0)
    status = Column(String(50), default="Đang theo dõi")  # "Đang theo dõi", "Đã kết thúc"


class AccessHistoryLog(Base):
    __tablename__ = "access_history_logs"
    id = Column(Integer, primary_key=True, index=True)
    child_id = Column(Integer, default=1)
    device_id = Column(String(64), default="CHILD-PC")
    ts = Column(DateTime, default=datetime.datetime.utcnow)
    target_name = Column(String(255), nullable=False)
    target_type = Column(String(50), default="Trang web")  # "Ứng dụng", "Trang web", "Tìm kiếm"
    status = Column(String(50), default="allowed")  # "allowed", "blocked"

