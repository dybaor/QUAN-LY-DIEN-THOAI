# OGK SERVER — MÁY CHỦ QUẢN LÝ & WEB DASHBOARD

FastAPI + SQLite (WAL). Máy chủ lưu chính sách, xác thực 3 vai trò, điều phối WebSocket và phục vụ Dashboard phụ huynh (`/`) cùng Cổng học tập của trẻ (`/child`).

## 1. Cấu trúc `app/`

| File | Vai trò |
| --- | --- |
| `config.py` | Đường dẫn dữ liệu, khóa bí mật (`OGK_JWT_SECRET`, `OGK_DATA_KEY` hoặc tự sinh `ogk_secrets.json`) |
| `security.py` | Argon2id, AES-256-GCM (`EncryptedString`), chữ ký HMAC chính sách, JWT cho Agent |
| `deps.py` | Phiên cookie + CSRF, Bearer token thiết bị, phân quyền `parent`/`child-view`/`admin`, chống IDOR |
| `audit.py` | Nhật ký kiểm toán (ai, lúc nào, IP, cũ → mới) |
| `services.py` | Tính quỹ thời gian, lịch 7×48, chuẩn hóa loại sự kiện, tuần tự hóa & ký chính sách |
| `routers/auth.py` | Tài khoản phụ huynh, nhiều hồ sơ trẻ, mã ghép đôi, thiết bị |
| `routers/child_portal.py` | API riêng cho Cổng học tập (`/api/child/*`) |
| `routers/enroll.py` | Ghép đôi Agent, xoay vòng token, gỡ cài đặt có xác thực |
| `routers/policy_events.py` | Chính sách, tạm nghỉ, sự kiện 7 trường (idempotency), vòng đời dữ liệu |
| `routers/commands.py` | Heartbeat, chính sách có chữ ký, WebSocket `/ws/parent`, `/ws/child`, `/ws/agent`, lệnh khẩn |
| `routers/reports.py` | Top 10 ứng dụng/tên miền, xuất CSV, nhật ký kiểm toán, "Hôm nay em đã dùng gì" |

## 2. API chính

| Vai trò | Endpoint |
| --- | --- |
| Công khai | `GET /api/auth/status`, `POST /api/auth/register` (chỉ khi chưa có tài khoản), `POST /api/auth/login` |
| Phụ huynh | `GET/POST /api/children`, `PUT /api/children/{id}`, `POST /api/children/{id}/pairing-code`, `GET /policy/{id}`, `PUT /policy/update`, `POST /policy/pause`, `POST /commands/send`, `GET /reports/summary/{id}`, `GET /reports/export/{id}.csv`, `GET /reports/audit-log/{id}`, `DELETE /data/purge-child/{id}` |
| Cổng trẻ (`child-view`) | `POST /api/child/pair`, `GET /api/child/session`, `GET /api/child/policy`, `GET/POST /api/child/web-usage`, `POST /api/child/verify-pin`, `POST /api/child/time-requests`, `GET /api/child/today`, `GET /api/child/audit-log` |
| Agent (Bearer) | `POST /enroll/verify`, `POST /enroll/refresh`, `POST /heartbeat`, `GET /agent/policy`, `POST /events/batch`, `POST /enroll/uninstall-authorize` |

Mọi yêu cầu ghi bằng cookie phải gửi header `X-CSRF-Token` (giá trị nhận khi đăng nhập hoặc từ `/api/auth/me`, `/api/child/session`).

## 3. Khởi chạy

Dùng launcher ở thư mục gốc: `Start_App.bat` (Windows) hoặc `./Start_App.command` (macOS). Chạy trực tiếp:

```powershell
python server/run_server.py
```

| Biến môi trường | Ý nghĩa |
| --- | --- |
| `OGK_DATA_DIR` / `OGK_DB_PATH` | Thư mục / file cơ sở dữ liệu |
| `OGK_HOST`, `OGK_PORT` | Mặc định `127.0.0.1:8000`; máy chủ từ chối mở ra mạng nếu không có TLS |
| `OGK_SSL_CERTFILE`, `OGK_SSL_KEYFILE` | Bật HTTPS (TLS 1.2+); cookie tự đặt `Secure` |
| `OGK_COOKIE_SECURE=1` | Ép cookie `Secure` khi chạy sau reverse proxy HTTPS |
