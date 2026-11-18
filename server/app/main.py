import os
import sys
from pathlib import Path

# Đảm bảo đường dẫn import cho app package
CURRENT_FILE = Path(__file__).resolve()
SERVER_ROOT = CURRENT_FILE.parent.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base, SessionLocal
from app.models import Parent, Child, Policy, TimeRequest
from app.routers import enroll, policy_events, commands, requests as time_requests

# 1. Khởi tạo cấu trúc bảng SQLite tự động theo chế độ WAL
Base.metadata.create_all(bind=engine)

# 2. Nạp dữ liệu mẫu ban đầu (Seed data) nếu cơ sở dữ liệu trống
db = SessionLocal()
try:
    if not db.query(Parent).first():
        sample_parent = Parent(
            username="phuhuynh1", 
            hashed_password="hashed_dummy_password"
        )
        db.add(sample_parent)
        db.commit()
        db.refresh(sample_parent)

        sample_child = Child(
            name=None, 
            age=10, 
            parent_id=sample_parent.id
        )
        db.add(sample_child)
        db.commit()
        db.refresh(sample_child)

        # Cấu hình chính sách mặc định ban đầu: CHƯA CÓ TÊN BÉ VÀ CHƯA CÓ PIN (Mặc định NULL)
        default_policy = Policy(
            child_id=sample_child.id,
            child_name=None,
            lock_pin=None,
            lock_password_hash=None,
            daily_quota_weekday_min=120,
            daily_quota_weekend_min=180,
            schedule_matrix="1" * 168,
            blocked_apps="",
            blocked_domains="",
            version=1
        )
        db.add(default_policy)
        db.commit()

    # Seed 1 yêu cầu xin thêm giờ nếu bảng rỗng
    if not db.query(TimeRequest).first():
        sample_req = TimeRequest(
            child_id=1,
            requested_minutes=15,
            reason="Bé xin thêm 15 phút: Hoàn thành bài tập trực tuyến",
            status="pending"
        )
        db.add(sample_req)
        db.commit()
finally:
    db.close()

# 3. Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="OGK Server - Người Bạn Đồng Hành",
    description="Backend API Quản lý & Giám sát Thiết bị Trẻ em",
    version="1.0.0"
)

# 4. Gắn các Routers (Enrollment, Policy & Events, Commands & WebSocket, Requests)
app.include_router(enroll.router)
app.include_router(policy_events.router)
app.include_router(commands.router)
app.include_router(time_requests.router)

# 5. Cấu hình thư mục Jinja2 Templates (Tương thích cả Dev lẫn PyInstaller Bundle)
import sys

def _resolve_templates_dir() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "templates")
            candidates.append(Path(sys._MEIPASS) / "server" / "templates")
        candidates.append(Path(sys.executable).resolve().parent / "templates")
    candidates.append(Path(__file__).resolve().parent.parent / "templates")
    candidates.append(Path.cwd() / "templates")
    candidates.append(Path.cwd() / "server" / "templates")
    for c in candidates:
        if c.exists() and (c / "dashboard.html").exists():
            return c
    return candidates[0]

TEMPLATES_DIR = _resolve_templates_dir()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def _resolve_static_dir() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "static")
            candidates.append(Path(sys._MEIPASS) / "server" / "static")
        candidates.append(Path(sys.executable).resolve().parent / "static")
    candidates.append(Path(__file__).resolve().parent.parent / "static")
    candidates.append(Path.cwd() / "static")
    candidates.append(Path.cwd() / "server" / "static")
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]

STATIC_DIR = _resolve_static_dir()
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 6. Endpoint trang chủ phục vụ Web Dashboard phụ huynh
@app.get("/", response_class=HTMLResponse)
def serve_dashboard(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html"
    )

# 7. Endpoint Cửa sổ Trực quan dành cho Trẻ em (Child Web Portal)
@app.get("/child", response_class=HTMLResponse)
@app.get("/child/{child_id}", response_class=HTMLResponse)
def serve_child_portal(request: Request, child_id: int = 1):
    return templates.TemplateResponse(
        request=request,
        name="child_portal.html"
    )

# 8. Endpoint Safe Web Proxy (Gỡ bỏ X-Frame-Options & CSP Frame Restrictions)
import urllib.request
import urllib.parse
import unicodedata
import re
import html
import datetime
from fastapi import Response, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DeviceEvent
from app.websocket_manager import manager

# Danh mục từ khóa cấm/nhạy cảm bắt buộc kiểm duyệt
RESTRICTED_KEYWORDS = [
    # 1. Nhóm nội dung không phù hợp lứa tuổi / đồi trụy (Adult/Explicit content)
    'sex', 'porn', 'xxx', '18+', '18plus', 'hentai', 'lon', 'buoi', 'dam', 'khoa than',
    'khong che', 'phim nguoi lon', 'gai goi', 'kich duc', 'tinh duc', 'thu dam', 'lam tinh',
    'jav', 'nude', 'erotic', 'lo hang', 'clip nong', 'do trui', 'khieu dam',

    # 2. Nhóm cờ bạc, cá cược trực tuyến, nhà cái, game bài đổi thưởng
    'bet', '88bet', 'f8bet', 'kubet', 'shbet', 'hi88', '789bet', 'jun88', 'new88', 'w88',
    'casino', 'nha cai', 'tai xiu', 'lo de', 'so de', 'danh bac', 'co bac', 'ca do', 'ca cuoc',
    'game bai', 'ban ca doi thuong', 'nohu', 'no hu', 'slot game', 'baccarat', 'roulette',
    'poker', 'xoc dia', 'xocdia', 'quay hu', 'keo nha cai',

    # 3. Nhóm bạo lực, chất gây nghiện, nguy hiểm
    'tu tu', 'tu sat', 'thuoc phien', 'ma tuy', 'ke', 'can sa', 'thuoc lac', 'bong cuoi',
    'chat gay nghien', 'vu khi', 'mua sung', 'dao kiem', 'danh nhau', 'bao luc'
]

def remove_vietnamese_tones(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text)
    res = ''.join([c for c in nfkd if not unicodedata.combining(c)])
    return res.replace('đ', 'd').replace('Đ', 'D')

def check_restricted_keyword_py(query: str) -> tuple[bool, str]:
    if not query:
        return False, ""
    raw_norm = query.strip().lower()
    no_tone_norm = remove_vietnamese_tones(raw_norm)

    for kw in RESTRICTED_KEYWORDS:
        kw_norm = kw.strip().lower()
        kw_no_tone = remove_vietnamese_tones(kw_norm)

        if len(kw_norm) <= 3:
            pattern = rf"(^|\b|\s|_|\W){re.escape(kw_norm)}($|\b|\s|_|\W)"
            pattern_no_tone = rf"(^|\b|\s|_|\W){re.escape(kw_no_tone)}($|\b|\s|_|\W)"
            if re.search(pattern, raw_norm, re.IGNORECASE) or re.search(pattern_no_tone, no_tone_norm, re.IGNORECASE):
                return True, kw
        else:
            if kw_norm in raw_norm or kw_no_tone in no_tone_norm:
                return True, kw

    return False, ""

@app.get("/proxy/web")
def proxy_web(url: str):
    """Proxy nội bộ nạp trang web vào iframe bằng cách gỡ X-Frame-Options & Content-Security-Policy"""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return Response(content="<p>Địa chỉ web không hợp lệ.</p>", media_type="text/html", status_code=400)
        
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "text/html; charset=utf-8")
            
            # Gỡ bỏ các thẻ meta X-Frame-Options hoặc CSP frame-ancestors nếu có trong HTML
            if "text/html" in content_type.lower():
                try:
                    text = content.decode("utf-8", errors="replace")
                    # Chèn base href để các link tương đối hoạt động
                    base_tag = f'<base href="{url}">'
                    if "<head>" in text.lower():
                        text = text.replace("<head>", f"<head>{base_tag}", 1).replace("<HEAD>", f"<HEAD>{base_tag}", 1)
                    content = text.encode("utf-8")
                except Exception:
                    pass

            response = Response(content=content, media_type=content_type)
            response.headers["Access-Control-Allow-Origin"] = "*"
            # Đảm bảo xóa hoặc không gán x-frame-options
            return response
    except Exception as e:
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-align: center; padding: 20px; }}
                .box {{ max-width: 480px; background: #1e293b; padding: 32px; border-radius: 20px; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.4); }}
                .btn {{ display: inline-block; margin-top: 16px; padding: 10px 20px; background: linear-gradient(135deg, #06b6d4, #0d9488); color: white; text-decoration: none; border-radius: 12px; font-weight: bold; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="box">
                <div style="font-size: 40px; margin-bottom: 12px;">🌐</div>
                <h3 style="margin: 0 0 8px 0; font-size: 18px; color: #38bdf8;">Không thể hiển thị nội dung trang này</h3>
                <p style="color: #94a3b8; font-size: 13px; line-height: 1.5; margin: 0;">Trang web này từ chối kết nối hoặc không cho phép nhúng trực tiếp. Bé vui lòng chọn ứng dụng học tập khác nhé!</p>
                <button class="btn" onclick="if (window.parent && window.parent.closeInAppBrowser) window.parent.closeInAppBrowser();">Đóng cửa sổ ✕</button>
            </div>
        </body>
        </html>
        """
        return Response(content=error_html, media_type="text/html", status_code=200)

@app.get("/health")
def health_check():
    return {
        "status": "online",
        "system": "OGK-Server",
        "sqlite_mode": "WAL"
    }