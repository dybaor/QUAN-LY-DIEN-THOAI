"""Ghi nhật ký kiểm toán NT5: ai thay đổi, lúc nào, từ IP nào, giá trị cũ → mới."""

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from .deps import Principal
from .models import AuditLog

ACTION_LABELS = {
    "account_created": "Tạo tài khoản phụ huynh",
    "password_changed": "Đổi mật khẩu phụ huynh",
    "login_locked": "Khóa đăng nhập 15 phút do nhập sai nhiều lần",
    "child_created": "Thêm hồ sơ trẻ",
    "child_updated": "Cập nhật hồ sơ trẻ",
    "pin_changed": "Đổi mã PIN mở khóa",
    "policy_updated": "Thay đổi chính sách thời gian / chặn",
    "time_extended": "Cộng thêm thời gian",
    "time_deducted": "Trừ bớt thời gian",
    "request_approved": "Duyệt yêu cầu xin thêm giờ",
    "request_rejected": "Từ chối yêu cầu xin thêm giờ",
    "window_locked": "Khóa máy từ xa",
    "window_unlocked": "Mở khóa máy từ xa",
    "unlocked_by_pin": "Mở khóa bằng mã PIN phụ huynh",
    "pin_locked": "Khóa nhập PIN 15 phút do nhập sai nhiều lần",
    "parent_pause_started": "Bật chế độ tạm nghỉ của phụ huynh",
    "parent_pause_ended": "Tắt chế độ tạm nghỉ của phụ huynh",
    "device_paired": "Ghép đôi thiết bị mới",
    "device_removed": "Gỡ ghép đôi thiết bị",
    "portal_paired": "Ghép đôi cổng học tập của trẻ",
    "agent_uninstalled": "Gỡ cài đặt Agent (đã xác thực phụ huynh)",
    "agent_ui_missing": "Agent tạm dừng giám sát do không thấy giao diện khay hệ thống",
    "agent_ui_restored": "Agent tiếp tục giám sát khi giao diện khay hệ thống hoạt động lại",
    "clock_tamper": "Phát hiện chỉnh đồng hồ hệ thống",
    "data_purged": "Xóa toàn bộ dữ liệu hoạt động của trẻ",
    "screen_view_requested": "Yêu cầu xem màn hình (cần trẻ đồng ý)",
}


def _dump(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def record(db: Session, principal: Optional[Principal], action: str, *, child_id: Optional[int] = None,
           old: Any = None, new: Any = None, ip: Optional[str] = None, commit: bool = False) -> AuditLog:
    entry = AuditLog(
        child_id=child_id,
        actor_role=principal.role if principal else "system",
        actor_id=principal.actor_id if principal else None,
        actor_name=(principal.name if principal else None) or None,
        client_ip=ip,
        action=action,
        old_value=_dump(old),
        new_value=_dump(new),
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def diff(before: dict, after: dict) -> tuple:
    changed = [key for key in after if before.get(key) != after.get(key)]
    return {key: before.get(key) for key in changed}, {key: after.get(key) for key in changed}


def serialize(entry: AuditLog) -> dict:
    return {
        "id": entry.id,
        "ts": entry.ts.isoformat() + "Z" if entry.ts else None,
        "child_id": entry.child_id,
        "actor_role": entry.actor_role,
        "actor_name": entry.actor_name,
        "client_ip": entry.client_ip,
        "action": entry.action,
        "action_label": ACTION_LABELS.get(entry.action, entry.action),
        "old_value": entry.old_value,
        "new_value": entry.new_value,
    }
