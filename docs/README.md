# HƯỚNG DẪN THIẾT LẬP VÀ KHỞI CHẠY NHANH TOÀN HỆ THỐNG
## DỰ ÁN: NGƯỜI BẠN ĐỒNG HÀNH (OGK SYSTEM)
> **Nền tảng:** Windows 10/11 x64 · Python 3.11+ · FastAPI · SQLite WAL · pywin32 · dnslib

---

## 1. Cấu trúc Thư mục Chuẩn hóa Dự án

```text
DoAn_NguoiBanDongHanh/
├── server/                      # [Thành viên C - Backend & Dashboard Web]
│   ├── app/                     # Mã nguồn FastAPI, SQLAlchemy, Router, WebSocket
│   ├── templates/               # Giao diện Dashboard Phụ huynh (Jinja2 + Tailwind + Chart.js)
│   ├── requirements.txt         # Thư viện phụ thuộc server
│   └── simulate_agent.py        # Kịch bản kiểm thử API tích hợp
│
├── agent/                       # [Thành viên A - Windows Service Core]
│   ├── main_service.py          # Windows Service (LocalSystem, pywin32)
│   ├── tracker.py               # Đo giờ time.monotonic(), Idle detection, Clock tamper M6
│   ├── blocker.py               # Chặn tiến trình bằng SHA-256 (psutil.terminate), Popup
│   ├── local_cache.py           # SQLite cache cục bộ (WAL mode, offline event queue)
│   ├── ws_client.py             # Client WebSocket lắng nghe lệnh lock_now (< 5s)
│   ├── install_service.bat      # Script cài đặt tự động một chạm (quyền Admin)
│   ├── uninstall_service.bat    # Script gỡ bỏ Windows Service
│   └── test_agent.py            # Script chạy console độc lập để kiểm thử
│
├── dns_proxy/                   # [Thành viên B - DNS & Network Security]
│   ├── proxy_server.py          # DNS Server UDP 127.0.0.1:53 (dnslib)
│   ├── blocklist.json           # Tối thiểu 200 tên miền phân loại 6 danh mục
│   ├── safesearch.py            # Cưỡng chế IP SafeSearch và chặn DoH canary (NXDOMAIN)
│   └── benchmark_m4.py          # Script đo 30 mẫu độ trễ p50/p95
│
├── docs/                        # [Bộ hồ sơ tài liệu bắt buộc]
│   ├── BaoCao.docx              # Bản thuyết minh đầy đủ đồ án (20–30 trang)
│   ├── BaoCaoKyThuatMang.pdf   # Phụ lục báo cáo thực nghiệm mạng M1–M6
│   ├── PRIVACY.md               # Bảng minh bạch dữ liệu theo Nghị định 13/2023 (2 phiên bản)
│   ├── THREATMODEL.md           # Bảng phân tích mô hình đe dọa STRIDE (6 tiêu chí)
│   ├── AI_USAGE.md              # Kê khai sử dụng AI và nhật ký debug lỗi
│   └── README.md                # Tài liệu hướng dẫn này
│
├── .gitignore                   # Loại trừ file tạm, database và cache
└── VideoDemo.mp4                # Video thực nghiệm 5–7 phút có lời bình
```

---

## 2. Các Bước Khởi chạy Hệ thống (Quick Start)

### Bước 1: Khởi động Server Quản lý (Thành viên C)
Mở cửa sổ dòng lệnh Terminal thứ nhất:
```powershell
cd DoAn_NguoiBanDongHanh/server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- Mở trình duyệt truy cập Web Dashboard Phụ huynh tại: `http://127.0.0.1:8000`

---

### Bước 2: Khởi động DNS Proxy Lọc mạng (Thành viên B)
Mở cửa sổ dòng lệnh Terminal thứ hai với quyền **Administrator**:
```powershell
cd DoAn_NguoiBanDongHanh/dns_proxy
python proxy_server.py
```
- DNS Proxy sẽ lắng nghe tại `127.0.0.1:53`, sẵn sàng lọc web xấu và ép SafeSearch cho Google/YouTube.
- Chạy benchmark đo đạc hiệu năng 30 mẫu M4:
  ```powershell
  python benchmark_m4.py
  ```

---

### Bước 3: Khởi chạy và Kiểm thử Agent Máy con (Thành viên A)
#### Cách 1: Chạy kiểm thử Console Standalone (Khuyên dùng khi debug & demo):
Mở cửa sổ dòng lệnh Terminal thứ ba:
```powershell
cd DoAn_NguoiBanDongHanh/agent
python test_agent.py
```
Hoặc chạy trực tiếp engine Agent trên màn hình:
```powershell
python main_service.py debug
```

#### Cách 2: Cài đặt dưới dạng Windows Service chính thức:
1. Mở Command Prompt với quyền **Run as Administrator**.
2. Chạy file cài đặt một chạm:
   ```cmd
   cd DoAn_NguoiBanDongHanh\agent
   install_service.bat
   ```
3. Kiểm tra trạng thái và cơ chế tự phục hồi sau 5 giây:
   ```cmd
   sc qfailure OGKChildAgent
   sc queryex OGKChildAgent
   ```

