"""Báo cáo cho phụ huynh (F3-2, F3-MR1), nhật ký kiểm toán (F4-3) và màn hình minh bạch cho trẻ (F3-3)."""

import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import Principal, authorize_child, require_parent
from ..models import AuditLog, DeviceEvent, TimeRequest
from ..services import daily_usage_seconds, time_snapshot

router = APIRouter(prefix="/reports", tags=["Báo cáo"])


def utc_range(days: int):
    """Khoảng thời gian UTC tương ứng `days` ngày gần nhất theo giờ địa phương (tính cả hôm nay)."""
    start_local = datetime.combine(datetime.now().date() - timedelta(days=days - 1), datetime.min.time())
    return datetime.utcfromtimestamp(start_local.timestamp()), datetime.utcnow() + timedelta(minutes=1)


def top_apps(db: Session, child_id: int, days: int, limit: int = 10) -> list:
    start, end = utc_range(days)
    seconds = func.sum(case((DeviceEvent.type == "app_stop", DeviceEvent.duration_sec), else_=0))
    opens = func.sum(case((DeviceEvent.type == "app_start", 1), else_=0))
    blocked = func.sum(case((DeviceEvent.type == "blocked_app", 1), else_=0))
    rows = (db.query(DeviceEvent.subject, seconds, opens, blocked)
            .filter(DeviceEvent.child_id == child_id, DeviceEvent.ts >= start, DeviceEvent.ts < end,
                    DeviceEvent.type.in_(("app_start", "app_stop", "blocked_app")))
            .group_by(DeviceEvent.subject)
            .order_by(seconds.desc(), opens.desc())
            .limit(limit).all())
    return [{"name": name, "minutes": round((secs or 0) / 60, 1), "opens": int(count or 0), "blocked": int(blk or 0)}
            for name, secs, count, blk in rows]


def top_domains(db: Session, child_id: int, days: int, limit: int = 10) -> list:
    start, end = utc_range(days)
    visits = func.count(DeviceEvent.id)
    blocked = func.sum(case((DeviceEvent.type == "blocked_domain", 1), else_=0))
    rows = (db.query(DeviceEvent.subject, visits, blocked)
            .filter(DeviceEvent.child_id == child_id, DeviceEvent.ts >= start, DeviceEvent.ts < end,
                    DeviceEvent.type.in_(("domain_query", "blocked_domain")))
            .group_by(DeviceEvent.subject)
            .order_by(visits.desc())
            .limit(limit).all())
    return [{"domain": domain, "visits": int(count), "blocked": int(blk or 0)} for domain, count, blk in rows]


def counters(db: Session, child_id: int, days: int) -> dict:
    start, end = utc_range(days)
    by_type = dict(db.query(DeviceEvent.type, func.count(DeviceEvent.id))
                   .filter(DeviceEvent.child_id == child_id, DeviceEvent.ts >= start, DeviceEvent.ts < end)
                   .group_by(DeviceEvent.type).all())
    by_status = dict(db.query(TimeRequest.status, func.count(TimeRequest.id))
                     .filter(TimeRequest.child_id == child_id, TimeRequest.created_at >= start)
                     .group_by(TimeRequest.status).all())
    return {
        "blocked_apps": by_type.get("blocked_app", 0),
        "blocked_domains": by_type.get("blocked_domain", 0),
        "blocked_total": by_type.get("blocked_app", 0) + by_type.get("blocked_domain", 0),
        "locks": by_type.get("locked", 0),
        "quota_warnings": by_type.get("quota_warning", 0),
        "requests_total": sum(by_status.values()),
        "requests_pending": by_status.get("pending", 0),
        "requests_approved": by_status.get("approved", 0),
        "requests_rejected": by_status.get("rejected", 0),
    }


def today_activity(db: Session, child_id: int) -> dict:
    snapshot = time_snapshot(child_id, datetime.now().date(), db)
    return {
        "date": datetime.now().date().isoformat(),
        "used_minutes": snapshot["today_minutes"],
        "quota_minutes": snapshot["quota_minutes"],
        "remaining_minutes": snapshot["remaining_seconds"] // 60,
        "apps": top_apps(db, child_id, 1, limit=20),
        "websites": top_domains(db, child_id, 1, limit=20),
        "counters": counters(db, child_id, 1),
    }


@router.get("/summary/{child_id}")
def report_summary(child_id: int, days: int = Query(default=7, ge=1, le=90),
                   principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    return {
        "child_id": child.id, "days": days,
        "top_apps": top_apps(db, child.id, days),
        "top_domains": top_domains(db, child.id, days),
        "counters": counters(db, child.id, days),
    }


@router.get("/top-apps/{child_id}")
def report_top_apps(child_id: int, days: int = Query(default=7, ge=1, le=90),
                    principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    return top_apps(db, authorize_child(db, principal, child_id).id, days)


@router.get("/top-domains/{child_id}")
def report_top_domains(child_id: int, days: int = Query(default=7, ge=1, le=90),
                       principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    return top_domains(db, authorize_child(db, principal, child_id).id, days)


@router.get("/audit-log/{child_id}")
def report_audit_log(child_id: int, limit: int = Query(default=100, ge=1, le=500),
                     principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    child = authorize_child(db, principal, child_id)
    own_account = (AuditLog.child_id.is_(None) & AuditLog.actor_role.in_(("parent", "admin"))
                   & (AuditLog.actor_id == str(principal.parent_id)))
    entries = (db.query(AuditLog).filter((AuditLog.child_id == child.id) | own_account)
               .order_by(AuditLog.ts.desc()).limit(limit).all())
    return [audit.serialize(entry) for entry in entries]


def _csv_safe(value) -> str:
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text  # Chống CSV injection khi mở bằng Excel


@router.get("/export/{child_id}.csv")
def export_weekly_csv(child_id: int, days: int = Query(default=7, ge=1, le=90),
                      principal: Principal = Depends(require_parent), db: Session = Depends(get_db)):
    """Xuất báo cáo tuần ra CSV (UTF-8 BOM để Excel hiển thị đúng tiếng Việt)."""
    child = authorize_child(db, principal, child_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Báo cáo sử dụng", child.name or f"Trẻ #{child.id}", f"{days} ngày gần nhất"])
    writer.writerow([])
    writer.writerow(["Ngày", "Phút sử dụng"])
    today = datetime.now().date()
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        writer.writerow([day.isoformat(), daily_usage_seconds(child.id, day, db) // 60])
    writer.writerow([])
    writer.writerow(["Top ứng dụng", "Phút", "Lượt mở", "Lần bị chặn"])
    for row in top_apps(db, child.id, days):
        writer.writerow([_csv_safe(row["name"]), row["minutes"], row["opens"], row["blocked"]])
    writer.writerow([])
    writer.writerow(["Top tên miền", "Lượt truy cập", "Lần bị chặn"])
    for row in top_domains(db, child.id, days):
        writer.writerow([_csv_safe(row["domain"]), row["visits"], row["blocked"]])
    writer.writerow([])
    writer.writerow(["Chỉ số", "Giá trị"])
    for key, value in counters(db, child.id, days).items():
        writer.writerow([key, value])
    filename = f"ogk_bao_cao_tre_{child.id}_{today.isoformat()}.csv"
    return StreamingResponse(
        iter(["﻿" + buffer.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
