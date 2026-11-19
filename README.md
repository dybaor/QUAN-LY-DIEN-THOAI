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
│ • Binary Frame Relay (30 FPS) │               │ • DNS Proxy Lọc mạng (Port 53)│
└───────────────────────────────┘               └───────────────────────────────┘
```

1. **FastAPI Backend Server & Web Dashboard:** Quản lý chính sách (Policy), xử lý WebSocket 2 chiều, phục vụ trang quản lý Phụ huynh (`http://127.0.0.1:8000`) và cổng học tập máy con Child Web Portal (`http://127.0.0.1:8000/child`).
2. **Client Agent Service (Headless Daemon):** Tiến trình chạy ngầm giám sát thời gian thực bằng `time.monotonic()`, phát hiện gian lận đổi giờ hệ thống, tiêu diệt tiến trình cấm bằng mã băm SHA-256 trong < 2 giây.
3. **Child Web Portal:** Cổng học tập an toàn 100% Web UI, hỗ trợ khóa In-Page Lock an toàn (không gọi khóa hệ điều hành Windows), tích hợp chia sẻ màn hình đồng thuận tốc độ cao 15–30 FPS (Binary JPEG Blob).
4. **DNS Proxy Lọc mạng:** Server DNS cục bộ trên UDP port 53, lọc tên miền độc hại theo blocklist và cưỡng chế SafeSearch cho Google & YouTube.

---

## 2. CẤU TRÚC THƯ MỤC DỰ ÁN

```text
demo/
├── server/             # Máy chủ FastAPI, Database SQLite, Templates & Static Web
│   ├── app/            # Routers (policy, events, ws, requests), Models, DB
│   ├── templates/      # Dashboard phụ huynh (dashboard.html) & Child Portal (child_portal.html)
│   ├── static/         # CSS & JavaScript (child.js)
│   └── run_server.py   # Script chạy máy chủ (Port 8000)
│
├── agent/              # Client Agent chạy ngầm trên máy tính
│   ├── main_service.py # Dịch vụ Windows Service (LocalSystem)
│   ├── tracker.py      # Bộ đếm giờ monotonic, phát hiện nhàn rỗi (idle) & lùi giờ
│   ├── blocker.py      # Quét mã băm SHA-256 ứng dụng và kết thúc tiến trình cấm
│   ├── local_cache.py  # Cache SQLite cục bộ chế độ WAL hỗ trợ lưu trữ offline
│   └── ws_client.py    # Kết nối WebSocket duy trì liên lạc với Server
│
├── dns_proxy/          # Trình phân giải và lọc tên miền mạng
│   ├── proxy_server.py # DNS Proxy Server UDP Port 53
│   ├── blocklist.json  # Danh sách tên miền cấm phân loại theo chủ đề
│   └── safesearch.py   # Ép buộc địa chỉ IP SafeSearch (Google/YouTube)
│
├── tests/              # Bộ kiểm thử tự động toàn diện (25 unit/integration tests)
├── build_release.py    # Kịch bản DevOps đóng gói tự động thành file .exe độc lập
└── dist_package/       # Gói cài đặt triển khai 1-click hoàn chỉnh
```

---

## 3. HƯỚNG DẪN 1 BƯỚC KHỞI ĐỘNG NHANH ĐỂ DEMO (QUICK START)

### Cách 1: Sử dụng Bản Phát Hành 1-Click (Khuyên dùng)
1. Tải hoặc clone repository, rồi mở thư mục `dist_package/`.
2. Nhấp đúp **`Start_App.bat`** để chạy OGK Server, Agent và mở hai giao diện trên trình duyệt.
3. Để bật DNS Proxy, chạy riêng **`start_proxy.bat`** bằng quyền Administrator.
4. Dùng **`Stop_App.bat`** để dừng Server và Agent.

> `dist_package/` chứa bộ chạy Windows dựng sẵn. Mã nguồn mới nhất nằm trong `server/`, `agent/` và `dns_proxy/`; các file `.exe` trong gói là bản dựng hiện có và cần được build lại trên Windows sau khi cập nhật mã nguồn. Database và cache runtime không được đưa lên GitHub.

### Khởi chạy nhanh trên macOS
Trên macOS, chạy `./Start_App.command` từ thư mục dự án. Launcher tự tạo `.venv`, cài thư viện backend còn thiếu, khởi động server và mở trang phụ huynh cùng giao diện trẻ trên trình duyệt. Nhấn `Ctrl+C` trong Terminal để dừng.

### Cách 2: Khởi chạy từ Mã Nguồn Python
Yêu cầu: Python 3.11+ trên Windows 10/11 x64.

1. **Cài đặt thư viện phụ thuộc:**
   ```powershell
   pip install fastapi uvicorn sqlalchemy websockets psutil pywin32 dnslib pytest pytest-asyncio
   ```
2. **Khởi chạy Server:**
   ```powershell
   python server/run_server.py
   ```
3. **Mở trình duyệt:**
   - Phụ huynh quản lý: `http://127.0.0.1:8000`
   - Máy con học tập: `http://127.0.0.1:8000/child`

---

## 4. CHẠY KIỂM THỬ TỰ ĐỘNG (AUTOMATED TESTS)

Chạy bộ kiểm thử tự động toàn diện bằng `pytest`:
```powershell
python -m pytest tests/ -v
```
*(Đảm bảo 25/25 bài kiểm thử chạy qua thành công 100%)*
