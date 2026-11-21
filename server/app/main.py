import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from fastapi import FastAPI, Request, Response
from sqlalchemy import text
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config
from app.database import Base, SessionLocal, engine, run_migrations
from app.models import Policy, RevokedToken
from app.routers import auth, child_portal, commands, enroll, policy_events, reports, requests as time_requests
from app.security import encrypt_text, hash_secret
from app.services import LEGACY_EVENT_TYPES


def prepare_database():
    """Tạo bảng, nâng cấp cột cho DB cũ và chuyển mã PIN lưu thô sang Argon2id."""
    Base.metadata.create_all(bind=engine)
    run_migrations()
    with SessionLocal() as db:
        for policy in db.query(Policy).filter(Policy.lock_pin.isnot(None), Policy.lock_pin != "").all():
            policy.lock_password_hash = hash_secret(policy.lock_pin.strip())
            policy.lock_pin = None
        # Dữ liệu cũ lưu thô: mã hóa tên trẻ và quy đổi loại sự kiện về tập chuẩn của đặc tả
        for table, column in (("children", "name"), ("policies", "child_name")):
            rows = db.execute(text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL AND {column} NOT LIKE 'enc:v1:%'")).all()
            for row_id, value in rows:
                db.execute(text(f"UPDATE {table} SET {column} = :v WHERE id = :i"), {"v": encrypt_text(value), "i": row_id})
        for legacy, standard in LEGACY_EVENT_TYPES.items():
            db.execute(text("UPDATE device_events SET type = :new WHERE type = :old"), {"new": standard, "old": legacy})
        db.commit()


def run_retention() -> int:
    with SessionLocal() as db:
        deleted = policy_events.purge_older_than(db)
        db.query(RevokedToken).filter(RevokedToken.expires_at < datetime.utcnow()).delete()
        db.commit()
        return deleted


async def retention_loop():
    """Tự động xóa dữ liệu hoạt động cũ hơn 90 ngày (F3-4)."""
    while True:
        try:
            await asyncio.to_thread(run_retention)
        except Exception as exc:  # Không để lỗi dọn dẹp làm dừng máy chủ
            print(f"[RETENTION] Lỗi dọn dữ liệu cũ: {exc}")
        await asyncio.sleep(config.RETENTION_INTERVAL_SEC)


prepare_database()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="OGK Server - Người Bạn Đồng Hành",
    description="Backend API Quản lý & Giám sát Thiết bị Trẻ em",
    version="2.0.0",
    lifespan=lifespan,
)

for router in (auth.router, child_portal.router, enroll.router, policy_events.router, commands.router,
               time_requests.router, reports.router):
    app.include_router(router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith(("/api/", "/policy", "/reports", "/requests", "/agent", "/enroll")):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def _resolve_dir(name: str, marker: str = "") -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            candidates += [Path(sys._MEIPASS) / name, Path(sys._MEIPASS) / "server" / name]
        candidates.append(Path(sys.executable).resolve().parent / name)
    candidates += [SERVER_ROOT / name, Path.cwd() / name, Path.cwd() / "server" / name]
    for candidate in candidates:
        if candidate.exists() and (not marker or (candidate / marker).exists()):
            return candidate
    return candidates[0]


templates = Jinja2Templates(directory=str(_resolve_dir("templates", "dashboard.html")))
STATIC_DIR = _resolve_dir("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/child", response_class=HTMLResponse)
def serve_child_portal(request: Request):
    return templates.TemplateResponse(request=request, name="child_portal.html")


@app.get("/proxy/web")
def proxy_web(url: str):
    return Response(status_code=403, content="Trang trẻ chỉ hỗ trợ Google Tìm kiếm.")


@app.get("/health")
def health_check():
    return {"status": "online", "system": "OGK-Server", "sqlite_mode": "WAL"}
