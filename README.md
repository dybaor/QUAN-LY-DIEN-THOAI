# OGK - NGƯỜI BẠN ĐỒNG HÀNH (CHILD DEVICE & NETWORK PROTECTION SYSTEM)

Hệ thống quản lý thời gian sử dụng thiết bị, bảo vệ không gian mạng và đồng hành cùng trẻ em minh bạch, tôn trọng quyền riêng tư (theo Nghị định 13/2023/NĐ-CP).

---

## 1. KIẾN TRÚC TỔNG THỂ HỆ THỐNG

Hệ thống hoạt động theo mô hình Client - Server kết hợp Web App thời gian thực:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                     HỆ THỐNG "NGƯỜI BẠN ĐỒNG HÀNH" (OGK)                 │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         ▼                                                   ▼
┌───────────────────────────────┐               ┌───────────────────────────────┐
│       FASTAPI BACKEND         │               │       CLIENT SUBSYSTEM        │
│       (Port 8000)             │               │       (Windows 10/11 x64)     │
├───────────────────────────────┤               ├───────────────────────────────┤
│ • RESTful API & SQLite DB     │◄──WebSocket──►│ • Agent Daemon (LocalSystem)  │
│ • Parent Dashboard (/)        │   (Realtime)  │   - Đo thời gian & Idle       │
│ • Child Web Portal (/child)   │               │   - Quét SHA-256 tiến trình   │
│ • Binary Frame Relay (30 FPS) │               │ • Tray UI (khay hệ thống)     │
│                               │               │ • DNS Proxy Lọc mạng (Port 53)│
└───────────────────────────────┘               └───────────────────────────────┘
```

1. **FastAPI Backend Server & Web Dashboard:** Quản lý chính sách (Policy), xử lý WebSocket 2 chiều, phục vụ trang quản lý Phụ huynh (`http://127.0.0.1:8000`) và cổng học tập máy con Child Web Portal (`http://127.0.0.1:8000/child`).
2. **Client Agent Service + Tray UI:** Windows Service đếm giờ bằng `time.monotonic()` (loại trừ màn hình khóa và nhàn rỗi), phát hiện chỉnh đồng hồ (so với giờ máy chủ), chặn ứng dụng theo SHA-256 và ghi sự kiện (cảnh báo 10/5/1 phút, ân hạn 60 giây, `locked`...). **Agent không khóa Windows và không mở popup**: việc khóa chỉ là overlay trên Cổng học tập. Biểu tượng khay hệ thống chạy trong phiên của trẻ, giao tiếp với Service qua named pipe (chỉ chuyển trạng thái).
3. **Child Web Portal:** Cổng học tập của trẻ (ghép đôi bằng mã 8 ký tự), màn hình khóa (overlay) khi hết giờ / ngoài lịch tuần / phụ huynh khóa, chia sẻ màn hình khi trẻ đồng ý (15–30 FPS), màn hình minh bạch "Hôm nay em đã dùng gì" và nhật ký thay đổi của ba mẹ.
4. **DNS Proxy Lọc mạng:** Server DNS cục bộ trên UDP port 53, phân loại 6 nhóm nội dung (giáo dục, giải trí, mạng xã hội, trò chơi, không phù hợp, chưa phân loại), chặn theo chính sách độ tuổi của trẻ, cưỡng chế SafeSearch và chặn DoH.

---

## 2. CẤU TRÚC THƯ MỤC DỰ ÁN

```text
├── Start_App.bat       # Launcher duy nhất cho Windows (mã nguồn hoặc gói .exe)
├── Start_App.command   # Launcher duy nhất cho macOS (chỉ máy chủ + giao diện web)
├── reset_database.py   # Đưa dữ liệu về trạng thái chưa có tài khoản (gọi qua --reset)
├── server/             # FastAPI + SQLite WAL, Dashboard phụ huynh & Cổng học tập của trẻ
│   ├── app/            # config, security (Argon2id/AES-GCM/HMAC/JWT), deps (phân quyền), audit, routers
│   ├── templates/      # dashboard.html, child_portal.html
│   └── static/         # CSS & JavaScript
├── agent/              # Agent Windows: Service + biểu tượng khay hệ thống (tray_ui.py)
│   ├── main_service.py # Service / CLI: enroll, status, debug, tray, uninstall
│   ├── enforcer.py     # Hạn mức, lịch 7x48, cảnh báo 10/5/1 phút, ân hạn 60 giây, ghi sự kiện (không khóa Windows)
│   ├── tracker.py      # Đếm giờ monotonic, loại trừ màn hình khóa / nhàn rỗi, đối chiếu giờ máy chủ
│   ├── blocker.py      # Chặn ứng dụng theo SHA-256, hiển thị lý do cho trẻ
│   ├── ui_bridge.py    # Named pipe Service ↔ khay hệ thống (chỉ chuyển trạng thái, chống chế độ ẩn)
│   ├── ws_client.py    # Heartbeat 60s, chính sách có chữ ký HMAC, gửi bù sự kiện (idempotency)
│   └── local_cache.py  # SQLite WAL, token mã hóa AES-GCM (khóa bảo vệ bằng DPAPI)
├── dns_proxy/          # DNS Proxy: 6 nhóm nội dung, SafeSearch, chặn DoH
├── desktop/            # Ứng dụng Electron OGKParent / OGKChild
├── tests/              # pytest + node:test
└── build_release.py    # Đóng gói .exe vào dist_package/
```

---

## 3. KHỞI CHẠY NHANH

### Windows
Nhấp đúp **`Start_App.bat`** ở thư mục gốc. Lần đầu launcher tự tạo `.venv` và cài thư viện (cần Python 3.11+), bật máy chủ trong cửa sổ **OGK Server**, rồi mở Dashboard phụ huynh (`http://127.0.0.1:8000`) và Cổng học tập (`http://127.0.0.1:8000/child`). Trong gói đã build (`dist_package/`), cùng file này chạy `ogk_server.exe` thay cho Python.

| Lệnh | Tác dụng |
| --- | --- |
| `Start_App.bat --server-only` | Chỉ bật máy chủ (dùng với `OGKParent.exe` / `OGKChild.exe`) |
| `Start_App.bat --with-agent` | Bật thêm Agent chế độ debug (máy đã ghép đôi) |
| `Start_App.bat --with-dns` | Bật thêm DNS Proxy (chạy bằng *Run as administrator*) |
| `Start_App.bat --reset` | Xóa dữ liệu, đưa hệ thống về trạng thái chưa có tài khoản |
| `Start_App.bat --stop` | Dừng máy chủ, Agent debug và DNS Proxy |

### macOS
Chạy `./Start_App.command` (hỗ trợ `--server-only`, `--reset`). Nhấn `Ctrl+C` để dừng. Agent và DNS Proxy chỉ chạy trên Windows.

### Luồng sử dụng
1. **Dashboard** → tạo tài khoản phụ huynh (mật khẩu ≥ 10 ký tự) và hồ sơ trẻ đầu tiên (tên, tuổi, mã PIN mở khóa 4–6 số).
2. **Thiết bị của trẻ** → *Tạo mã ghép đôi* (8 ký tự, hạn 10 phút).
3. Trên máy của trẻ:
   - **Cổng học tập**: nhập mã trên màn hình chờ. Khi demo trên một máy, bấm *Mở Cổng học tập trên máy này*.
   - **Agent**: chạy `agent\install_service.bat` bằng quyền Administrator và nhập mã (hoặc `python agent/main_service.py enroll <MÃ>` rồi `Start_App.bat --with-agent`).

---

## 4. BẢO MẬT & QUYỀN RIÊNG TƯ

- Mật khẩu phụ huynh và mã PIN băm **Argon2id**. Nhập sai 5 lần thì khóa 15 phút; đăng nhập bị giới hạn tần suất theo IP.
- Phiên đăng nhập dùng cookie `HttpOnly` + `SameSite=Strict` (`Secure` khi chạy HTTPS), được hủy phía máy chủ khi đăng xuất. Mọi yêu cầu ghi phải có mã chống CSRF.
- Phân quyền 3 vai trò `parent` / `child-view` / `admin`. Mọi truy vấn đều kiểm tra quyền sở hữu trẻ (chống IDOR). Admin chỉ có thêm quyền quản trị hệ thống, không xem được dữ liệu trẻ của gia đình khác.
- Agent dùng access token 15 phút + refresh token xoay vòng, có danh sách thu hồi. Chính sách được ký **HMAC-SHA256** bằng khóa riêng của từng thiết bị. Có hỗ trợ TLS 1.2+ và ghim chứng chỉ (`OGK_SERVER_URL=https://…`, `OGK_CERT_SHA256=…`).
- Trường nhạy cảm được mã hóa **AES-256-GCM**: tên trẻ và khóa ký trên máy chủ (khóa lấy từ `OGK_DATA_KEY`, hoặc tự sinh trong `ogk_secrets.json`); token trên Agent (khóa bảo vệ bằng DPAPI).
- **Nhật ký kiểm toán**: mọi thay đổi cấu hình đều ghi lại ai, lúc nào, IP, giá trị cũ → mới. Trẻ xem được trong Cổng học tập.
- Dữ liệu hoạt động cũ hơn 90 ngày tự động bị xóa. Nút *Xóa toàn bộ dữ liệu* xóa trên máy chủ và yêu cầu Agent xóa bộ nhớ đệm.
- Agent luôn hiện biểu tượng khay hệ thống. Nếu không thấy giao diện quá 2 phút, Agent tạm dừng giám sát và báo cho phụ huynh. Gỡ cài đặt bắt buộc có tài khoản phụ huynh.

---

## 5. CHẠY KIỂM THỬ TỰ ĐỘNG

```powershell
python -m pytest tests -q
node --test tests/ui_behavior.test.cjs
```
Bộ test dùng thư mục dữ liệu tạm (`tests/conftest.py`), không chạm vào `ogk_system.db` thật.
