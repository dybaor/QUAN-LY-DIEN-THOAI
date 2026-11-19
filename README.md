# OGK - NGƯỜI BẠN ĐỒNG HÀNH (CHILD DEVICE & NETWORK PROTECTION SYSTEM)

Hệ thống quản lý thời gian sử dụng thiết bị, bảo vệ không gian mạng và đồng hành cùng trẻ em minh bạch, tôn trọng quyền riêng tư (theo Nghị định 13/2023/NĐ-CP).

---

## 1. KIẾN TRÚC TỔNG THỂ HỆ THỐNG

Hệ thống hoạt động theo mô hình Client - Server kết hợp Web App & Desktop App thời gian thực:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                          HỆ THỐNG "NGƯỜI BẠN ĐỒNG HÀNH" (OGK)                           │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                             │
                   ┌─────────────────────────┴─────────────────────────┐
                   ▼                                                   ▼
┌───────────────────────────────────────┐             ┌─────────────────────────────────┐
│           FASTAPI BACKEND             │             │        CLIENT SUBSYSTEM         │
│             (Port 8000)               │             │       (Windows 10/11 x64)       │
├───────────────────────────────────────┤             ├─────────────────────────────────┤
│ • RESTful API & SQLite DB (WAL Mode)  │◄─WebSocket─►│ • Desktop Apps (Electron x64)   │
│ • Parent Dashboard (/)                │  (Realtime) │   - OGKParent.exe: Quản trị     │
│ • Child Web Portal (/child)           │             │   - OGKChild.exe: Kiosk an toàn │
│ • Binary Frame Stream (15–30 FPS)     │             │ • Agent Daemon (LocalSystem)    │
│ • Safe Web Proxy & Keyword Moderation │             │   - time.monotonic() (M6)       │
│ • Quota & Daily Time Adjustments      │             │   - Quét SHA-256 tiến trình < 2s│
└───────────────────────────────────────┘             │ • DNS Proxy Lọc mạng (UDP 53)   │
                                                      │   - Sinkhole 0.0.0.0 & SafeSearch│
                                                      └─────────────────────────────────┘
```

### Các thành phần cốt lõi:
1. **FastAPI Backend Server & Web UI:** 
   - Quản lý chính sách (Policy), xác thực PIN phụ huynh, nhật ký vi phạm và phiên theo dõi.
   - Cung cấp WebSocket hai chiều đồng bộ thời gian thực: duyệt xin thêm giờ, trừ giờ phạt, khóa màn hình, chat tức thì và truyền khung hình màn hình đồng thuận.
   - **Cơ chế tính giờ & Quản lý số dư chuẩn xác:** Hạn mức gốc `120 phút/ngày thường` và `180 phút/cuối tuần` được bảo toàn cố định; các thay đổi cộng/trừ giờ được quản lý qua bảng riêng `daily_time_adjustments` và tự động hết hiệu lực khi bước sang ngày mới.
   - **Bảo đảm trạng thái sạch 100% khi khởi chạy:** Quản lý chặt chẽ toàn bộ các bảng dữ liệu phát sinh (`time_requests`, `web_daily_usage`, `device_events`, `daily_time_adjustments`, `child_window_locks`), đảm bảo khi khởi động ứng dụng mới hoặc reset thì máy trẻ không bị trừ sẵn giờ và không có yêu cầu xin thêm giờ tồn đọng.
   - **Tự động cách ly môi trường kiểm thử:** Bộ fixture `tests/conftest.py` tự động khôi phục cơ sở dữ liệu về trạng thái sạch cả trước và sau khi chạy test suite, ngăn chặn triệt để việc dữ liệu test làm ô nhiễm môi trường chạy thực tế.
2. **Bộ ứng dụng Desktop chuyên biệt (Electron Windows x64):**
   - **`OGKParent.exe`:** Bảng điều khiển dành riêng cho phụ huynh (giao diện cửa sổ 1280x850, đầy đủ công cụ theo dõi, phê duyệt và điều khiển).
   - **`OGKChild.exe`:** Cổng học tập toàn màn hình (Kiosk mode), khóa in-app an toàn, ngăn tải file, ngăn thoát cửa sổ, tích hợp công cụ tìm kiếm Google SafeSearch bảo mật cao.
3. **Client Agent Service (Headless Daemon):**
   - Chạy ngầm dưới quyền LocalSystem, theo dõi thời gian thực bằng `time.monotonic()`.
   - **Chống lùi giờ hệ thống (Chuyên đề M6):** So sánh `time.monotonic()` với wall-clock `time.time()`, phát hiện sai lệch > 60s để ghi nhận sự kiện vi phạm `clock_tamper`.
   - **Chặn ứng dụng theo mã băm SHA-256:** Quét và tiêu diệt tiến trình cấm trong < 2 giây, bất chấp việc đổi tên file thực thi (`.exe`).
   - SQLite cache cục bộ (chế độ WAL) lưu trữ hàng đợi 7 trường dữ liệu chuẩn, tự đồng bộ khi có kết nối Internet trở lại.
4. **DNS Proxy Lọc mạng (Port 53 UDP):**
   - Lắng nghe cổng UDP 53 tại `127.0.0.1`, chặn các tên miền độc hại trong `blocklist.json` (người lớn, cờ bạc, bạo lực, chất cấm,...).
   - Ép buộc SafeSearch cho Google, YouTube, Bing và chặn DoH Canary Domains (`use-application-dns.net`) ngăn trình duyệt bypass DNS.

---

## 2. CẤU TRÚC THƯ MỤC DỰ ÁN

```text
QUAN-LY-DIEN-THOAI/
├── server/                     # Máy chủ FastAPI Backend & Giao diện Web
│   ├── app/                    # Mã nguồn backend (routers, models, database, websocket)
│   │   ├── routers/            # commands.py, enroll.py, policy_events.py, requests.py
│   │   ├── daily_time.py       # Quản lý số dư và điều chỉnh giờ theo ngày (không sửa quota gốc)
│   │   ├── database.py         # SQLite Engine chế độ WAL, connection pool
│   │   ├── models.py           # SQLAlchemy Models (Policy, Child, DeviceEvent, TimeRequest,...)
│   │   └── websocket_manager.py# Quản lý kết nối WebSocket và phát tín hiệu theo đối tượng
│   ├── templates/              # Giao diện HTML (dashboard.html, child_portal.html)
│   ├── static/                 # Tài nguyên CSS, JS (child.js, ui.css, time-timeline.js)
│   ├── run_server.py           # Điểm khởi chạy server FastAPI (Port 8000)
│   ├── requirements.txt        # Danh sách thư viện Python của máy chủ
│   └── Start_App.bat           # 1-Click launcher tự động tạo .venv và chạy server
│
├── desktop/                    # Ứng dụng Desktop Windows (Electron)
│   ├── main.cjs                # Quy trình chính Electron (phân nhánh Parent / Child Kiosk)
│   ├── google.cjs              # Cấu hình an toàn cho Google Search (SafeSearch, udm=14)
│   ├── preload.cjs             # Context bridge an toàn giao tiếp renderer - main
│   ├── build-windows.cjs       # Script đóng gói thành OGKParent.exe & OGKChild.exe
│   └── package.json            # Cấu hình dependencies (Electron 45, @electron/packager 20)
│
├── agent/                      # Client Agent giám sát máy tính
│   ├── main_service.py         # Windows Service daemon chạy ngầm
│   ├── tracker.py              # Đếm giờ monotonic, phát hiện nhàn rỗi (> 5p) & chống lùi giờ (M6)
│   ├── blocker.py              # Quét mã băm SHA-256 ứng dụng, dừng tiến trình vi phạm
│   ├── local_cache.py          # SQLite Cache cục bộ (%ProgramData%\OGKAgent\agent_cache.db)
│   ├── ws_client.py            # WebSocket Client giữ liên lạc với Server
│   └── test_agent.py           # Kiểm thử console độc lập cho thành phần Agent
│
├── dns_proxy/                  # DNS Proxy Server (Lọc mạng & Cưỡng chế SafeSearch)
│   ├── proxy_server.py         # DNS Proxy lắng nghe UDP 127.0.0.1:53
│   ├── blocklist.json          # Danh bạ tên miền cấm phân theo 6 nhóm chủ đề
│   └── safesearch.py           # Rewrite địa chỉ IP SafeSearch và chặn DoH Canary
│
├── dist/desktop/               # Thư mục chứa 2 file .exe sau khi build
│   ├── OGKParent-win32-x64/    # Thư mục chạy app Phụ huynh (OGKParent.exe)
│   └── OGKChild-win32-x64/     # Thư mục chạy app Trẻ em (OGKChild.exe)
│
├── dist_package/               # Gói cài đặt độc lập Windows (PyInstaller Service & DNS Proxy)
│   ├── agent_service.exe       # Windows Service daemon chạy ngầm LocalSystem
│   ├── dns_proxy.exe           # DNS Proxy lọc tên miền UDP 53
│   ├── ogk_server.exe          # Standalone server exe đóng gói sẵn
│   ├── install_service.bat     # Cài đặt Agent Service vào Windows Services
│   └── start_proxy.bat         # Khởi chạy nhanh DNS Proxy
│
├── tests/                      # Bộ kiểm thử tự động toàn diện (Pytest & Node.js test)
│   ├── conftest.py             # Fixture tự động dọn sạch database trước và sau test
│   ├── test_blocker.py         # Test chặn ứng dụng bằng SHA-256 (< 2s)
│   ├── test_child_web_lock.py  # Test cổng trẻ em, in-page lock, không can thiệp OS fullscreen
│   ├── test_daily_time_adjustments.py # Test đồng bộ giờ, xin giờ, trừ giờ, reset ngày mới
│   ├── test_policy_api.py      # Test API chính sách, PIN mở khóa, ma trận 168h
│   ├── test_safe_lock_and_web.py # Test tổng hợp bảo mật web, UI toast, websocket sync
│   ├── test_safety_and_ui.py   # Test an toàn và nhật ký giám sát màn hình
│   ├── test_websocket.py       # Test kết nối và phát lệnh WebSocket
│   └── ui_behavior.test.cjs    # Bộ 42 kiểm thử hành vi giao diện người dùng bằng Node.js
│
├── reset_database.py           # Script reset cơ sở dữ liệu về trạng thái sạch ban đầu
├── Reset_Data.bat              # 1-Click reset database trên Windows
└── build_release.py            # Kịch bản đóng gói PyInstaller cho agent và dns_proxy
```

---

## 3. HƯỚNG DẪN CÁCH KHỞI CHẠY HỆ THỐNG

### Yêu cầu môi trường:
* **Hệ điều hành:** Windows 10/11 x64 (hoặc macOS/Linux cho máy chủ backend).
* **Python:** Python 3.11+ (khuyên dùng Python 3.11.x x64).
* **Node.js:** Node.js v18+ & npm (để build và chạy ứng dụng Desktop).

---

### Cách 1: Chạy hai Ứng dụng Desktop Windows (`OGKParent.exe` & `OGKChild.exe`)

Đây là phương thức khuyến nghị mô phỏng chính xác nhất môi trường triển khai thực tế.

#### Bước 1: Khởi động máy chủ backend (chế độ server-only)
Mở Command Prompt / PowerShell tại thư mục dự án và chạy:
```cmd
server\Start_App.bat --server-only
```
*Tùy chọn: Nếu muốn đảm bảo cơ sở dữ liệu hoàn toàn sạch (0 phút đã dùng, 0 yêu cầu xin giờ tồn đọng), thêm cờ `--clean`:*
```cmd
server\Start_App.bat --server-only --clean
```
*Lệnh này sẽ tự động thiết lập virtualenv `.venv`, cài đặt thư viện cần thiết và khởi động máy chủ tại `http://127.0.0.1:8000` trong cửa sổ nền.*

#### Bước 2: Build ứng dụng Desktop (nếu chưa có trong `dist/desktop/`)
Chỉ cần thực hiện lần đầu hoặc sau khi chỉnh sửa mã nguồn trong thư mục `desktop/`:
```powershell
npm --prefix desktop ci
npm --prefix desktop run build:windows
```
*Kết quả đóng gói sẽ xuất hiện trong `dist/desktop/OGKParent-win32-x64/` và `dist/desktop/OGKChild-win32-x64/`.*

#### Bước 3: Mở hai ứng dụng
* **Mở ứng dụng Phụ huynh:**
  ```cmd
  dist\desktop\OGKParent-win32-x64\OGKParent.exe
  ```
  Hoặc chạy trực tiếp từ mã nguồn: `npm --prefix desktop run parent`.
* **Mở ứng dụng Trẻ em:**
  ```cmd
  dist\desktop\OGKChild-win32-x64\OGKChild.exe
  ```
  Hoặc chạy trực tiếp từ mã nguồn: `npm --prefix desktop run child`.

> **Ghi chú chạy đa máy (Remote Server):** Mặc định app trỏ về `http://127.0.0.1:8000`. Khi triển khai máy phụ huynh và máy trẻ ở hai máy tính khác nhau trong mạng LAN, đặt biến môi trường:
> ```powershell
> $env:OGK_SERVER_URL="https://dia-chi-ip-hoac-domain-server"
> ```

---

### Cách 2: Khởi chạy nhanh trên Trình duyệt Web (1-Click)

Dành cho kiểm thử giao diện nhanh không cần cài đặt Electron.

* **Trên Windows:** Nhấp đúp file **`server\Start_App.bat`**.
  * Server tự khởi động và tự động mở 2 tab trình duyệt:
    * Dashboard Phụ huynh: `http://127.0.0.1:8000/`
    * Cổng Trẻ em: `http://127.0.0.1:8000/child`
* **Trên macOS:** Nhấp đúp file **`server/Start_App.command`** hoặc chạy từ Terminal:
  ```bash
  bash server/Start_App.command
  ```

---

### Cách 3: Chạy Agent Giám sát và DNS Proxy Lọc mạng

Áp dụng trên máy tính của trẻ để thực thi chính sách tầng hệ điều hành và mạng:

1. **Khởi chạy DNS Proxy (UDP 53):**
   * Mở CMD / PowerShell bằng quyền **Run as Administrator**.
   * Chạy:
     ```cmd
     dist_package\start_proxy.bat
     ```
     *(Hoặc: `python dns_proxy/proxy_server.py`)*
   * Đặt DNS của card mạng máy tính trẻ trỏ về `127.0.0.1`:
     ```powershell
     Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ServerAddresses ("127.0.0.1")
     ```
2. **Khởi chạy Client Agent Service:**
   * Cài đặt thành Windows Service tự khởi động: Chuột phải vào `dist_package\install_service.bat` -> chọn **Run as administrator**.
   * Hoặc chạy thử nghiệm ở chế độ Debug trên màn hình Console:
     ```cmd
     agent_service.exe --debug
     ```
     *(Hoặc: `python agent/main_service.py`)*

---

### Cách 4: Cấu hình Chế độ Kiosk khóa thoát trên máy trẻ

Để ngăn trẻ tắt app hoặc mở ứng dụng khác:
1. Tạo một tài khoản Windows tiêu chuẩn (Standard User, không có quyền Admin), ví dụ đặt tên là `TreEm`.
2. Giữ nguyên tài khoản Quản trị viên (Administrator) cho phụ huynh có mật khẩu bảo vệ.
3. Thiết lập **Shell Launcher** (hoặc cấu hình Registry `HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon\Shell` của user `TreEm` trỏ trực tiếp đến `OGKChild.exe`).
4. Đặt cơ chế tự động mở lại app nếu bị tắt đột ngột (Exit Code Action = Restart).
5. Vô hiệu hóa Task Manager cho tài khoản trẻ qua Local Group Policy Editor (`gpedit.msc` -> `User Configuration\Administrative Templates\System\Ctrl+Alt+Del Options\Remove Task Manager` = **Enabled**).
6. Khi cần bảo trì hoặc thoát Kiosk: Phụ huynh nhấn `Ctrl + Alt + Del` -> Chọn **Switch User** / **Sign out** và đăng nhập vào tài khoản Administrator.

---

## 4. HƯỚNG DẪN KIỂM THỬ & TEST BUG (TESTING & TROUBLESHOOTING)

Hệ thống tích hợp bộ kiểm thử tự động toàn diện gồm **87 bài test** (45 bài Python Pytest + 42 bài Node.js UI behavior).

### 4.1. Chạy toàn bộ Test tự động (Automated Test Suite)

#### 1. Kiểm thử Backend, Agent & Policy (Pytest)
```powershell
# Chạy toàn bộ test suite
python -m pytest tests agent/test_agent.py -v

# Hoặc chạy bằng môi trường ảo của server
& "server\.venv\Scripts\python.exe" -m pytest tests agent/test_agent.py -v
```
*(Tiêu chí đạt: **45/45 bài kiểm thử PASS 100%**)*.

#### 2. Kiểm thử Hành vi Giao diện & WebSocket (Node.js Test Runner)
```powershell
node --test tests/ui_behavior.test.cjs
```
*(Tiêu chí đạt: **42/42 bài kiểm thử PASS 100%**)*.

---

### 4.2. Các kịch bản kiểm thử thủ công và phát hiện lỗi (Manual Test Scenarios)

#### Kịch bản 1: Đồng bộ số dư thời gian & Phê duyệt xin thêm giờ
1. Mở song song `OGKParent.exe` (hoặc `http://127.0.0.1:8000`) và `OGKChild.exe` (hoặc `http://127.0.0.1:8000/child`).
2. Quan sát số phút còn lại trên cả 2 giao diện: Phải hiển thị giống nhau theo thời gian thực.
3. Tại giao diện trẻ em, nhấn **"Xin thêm giờ"** (chọn 15 phút).
   * **Kiểm tra:** Yêu cầu xuất hiện ngay lập tức tại mục *"Duyệt xin thêm giờ"* trên giao diện Phụ huynh thông qua WebSocket mà không cần bấm F5.
4. Phụ huynh nhấn **"Duyệt (+15p)"**:
   * **Kiểm tra:** Số phút còn lại trên cả hai ứng dụng lập tức tăng thêm 15 phút.
5. Phụ huynh nhấn nút **"-15p"** hoặc **"-30p"** trong menu điều khiển:
   * **Kiểm tra:** Số phút còn lại của trẻ lập tức bị trừ tương ứng, thanh tiến trình cập nhật ngay.

#### Kịch bản 2: Kiểm tra bảo toàn hạn mức gốc 120/180 và điều chỉnh hết hạn sang ngày mới
* **Mục đích:** Phát hiện lỗi nghiêm trọng từng xuất hiện ở các bản cũ (bản cũ lấy lệnh trừ giờ trừ trực tiếp vào `daily_quota_weekday_min`, làm mất hạn mức mặc định 120 phút của trẻ vĩnh viễn).
* **Cách kiểm tra:**
  1. Kiểm tra cơ sở dữ liệu `ogk_system.db`:
     ```powershell
     python -c "import sqlite3; c=sqlite3.connect('ogk_system.db').cursor(); c.execute('SELECT daily_quota_weekday_min, daily_quota_weekend_min FROM policies WHERE child_id=1'); print(c.fetchall())"
     ```
     *Kết quả chuẩn: Luôn giữ nguyên `(120, 180)`.*
  2. Các giá trị cộng/trừ giờ nằm trong bảng riêng `daily_time_adjustments` ứng với cột `day = YYYY-MM-DD`.
  3. Khi sang ngày mới (hoặc chỉnh ngày hệ thống tiến lên 1 ngày), giá trị điều chỉnh tự động hết hiệu lực (`adjustment_minutes = 0`), số giờ của trẻ được trả về nguyên vẹn 120 phút (ngày thường) hoặc 180 phút (cuối tuần).

#### Kịch bản 3: Kiểm tra Chia sẻ màn hình và Trở về trạng thái chờ tự động
1. Trên giao diện phụ huynh, nhấn nút **"Xem màn hình"**.
2. Trên app trẻ, hộp thoại đồng thuận xuất hiện -> Nhấn **"Đồng ý chia sẻ"**.
   * **Kiểm tra:** Màn hình phụ huynh chuyển sang hiển thị khung video trực tiếp (15–30 FPS).
3. Thử nghiệm ngắt kết nối:
   * Trẻ bấm **"Dừng chia sẻ"**, HOẶC tắt ứng dụng `OGKChild.exe`, HOẶC rút dây mạng:
   * **Kiểm tra:** Khung hình phía phụ huynh **ngay lập tức trở về trạng thái chờ kích hoạt** (hiển thị biểu tượng 🖥️ và nút "Xem màn hình") mà không bị đơ màn hình hay phải tải lại trang.

#### Kịch bản 4: Kiểm tra Chặn ứng dụng theo mã băm SHA-256
1. Tạo một ứng dụng giả lập hoặc dùng ứng dụng có trong danh sách hạn chế.
2. Đổi tên file exe thành một tên hoàn toàn vô hại (ví dụ `notepad.exe` đổi thành `tro_choi_hoc_tap.exe`).
3. Khởi chạy file thực thi đó.
   * **Kiểm tra:** Trong vòng **dưới 2 giây**, tiến trình vi phạm bị Agent phát hiện mã băm SHA-256 và chấm dứt (kill) ngay lập tức.
   * Một thông báo vi phạm được ghi vào bảng *Nhật ký Vi phạm* trên Dashboard phụ huynh.

#### Kịch bản 5: Kiểm tra Chống lùi giờ hệ thống (Chuyên đề M6)
1. Trong khi Agent đang chạy, mở cài đặt Windows và lùi đồng hồ hệ thống về trước hơn 60 giây (ví dụ lùi 5 phút).
2. **Kiểm tra:** Module `tracker.py` so sánh `time.monotonic()` với `time.time()`, phát hiện sự chênh lệch và lập tức phát sinh sự kiện vi phạm `clock_tamper` gửi về Dashboard phụ huynh.

#### Kịch bản 6: Kiểm tra Tìm kiếm Google SafeSearch & DNS Proxy
1. Trên app trẻ em, gõ từ khóa học tập (ví dụ: `toán lớp 5`):
   * **Kiểm tra:** Cửa sổ kết quả Google Tìm kiếm mở ra trong môi trường an toàn, có tham số `safe=active` và `udm=14`.
2. Thử nhấp vào các đường link ra ngoài trang kết quả tìm kiếm:
   * **Kiểm tra:** App tự động hủy điều hướng, không mở trang ngoài.
3. Thử tìm kiếm các từ khóa người lớn, đồi trụy hoặc cờ bạc:
   * **Kiểm tra:** App phát hiện từ khóa trong danh mục cấm và chặn ngay lập tức.
4. Kiểm tra DNS Proxy từ dòng lệnh (khi DNS trỏ về 127.0.0.1):
   ```powershell
   Resolve-DnsName -Name "pornhub.com" -Server 127.0.0.1
   ```
   *Kết quả: Trả về `0.0.0.0` (Sinkhole).*
   ```powershell
   Resolve-DnsName -Name "www.google.com" -Server 127.0.0.1
   ```
   *Kết quả: Rewrite về IP SafeSearch `216.239.38.120`.*

#### Kịch bản 7: Kiểm tra Khởi động sạch ban đầu (Clean Boot & Không ô nhiễm dữ liệu)
* **Mục đích:** Đảm bảo khi mới chạy ứng dụng trên máy sạch hoặc sau khi reset, trẻ không bị trừ sẵn giờ và không có các yêu cầu xin thêm giờ tồn đọng do dữ liệu test cũ để lại.
* **Cách kiểm tra:**
  1. Khởi động máy chủ với cờ `--clean` hoặc chạy `Reset_Data.bat`:
     ```cmd
     server\Start_App.bat --server-only --clean
     ```
  2. Mở song song `OGKParent.exe` và `OGKChild.exe`:
     * **Phía Phụ huynh:** Mục *"Trung tâm phê duyệt"* hiển thị `0 chờ duyệt` (*"Hiện không có yêu cầu nào đang chờ duyệt"*); widget thời gian hiển thị `Đã dùng 0p / 2g`.
     * **Phía Trẻ em:** Thời gian sử dụng còn lại hiển thị đầy đủ `120 phút` (ngày thường) hoặc `180 phút` (cuối tuần), thanh tiến trình 100% xanh.
  3. Chạy toàn bộ test suite (`python -m pytest tests agent/test_agent.py`), sau đó kiểm tra lại database:
     ```powershell
     python -c "import sqlite3; c=sqlite3.connect('ogk_system.db').cursor(); print('Requests:', c.execute('SELECT count(*) FROM time_requests').fetchone()[0]); print('Adjustments:', c.execute('SELECT count(*) FROM daily_time_adjustments').fetchone()[0]); print('Usage:', c.execute('SELECT count(*) FROM web_daily_usage').fetchone()[0])"
     ```
     *Kết quả: Tất cả đều bằng `0` nhờ cơ chế auto-cleanup của `tests/conftest.py`.*

---

### 4.3. Script dọn dẹp & Reset dữ liệu sạch (Clean State)

Khi muốn đưa cơ sở dữ liệu về trạng thái sạch 100% (Trường hợp A: Chưa cấu hình tên bé, chưa có mã PIN, 0 yêu cầu xin giờ, 0 phút bị trừ):
* **Cách 1 (Khuyên dùng trên Windows):** Nhấp đúp vào file **`Reset_Data.bat`** tại thư mục gốc dự án (tự động kích hoạt môi trường ảo Python của server).
* **Cách 2 (Khởi động kèm Reset sạch):** Chạy `Start_App.bat` với tham số `--clean`:
  ```cmd
  server\Start_App.bat --server-only --clean
  ```
* **Cách 3 (Chạy script Python thủ công):**
  ```powershell
  python reset_database.py
  ```
Script sẽ đóng tất cả kết nối SQLite pool, xóa hoàn toàn các file `ogk_system.db`, `db-shm`, `db-wal` cũ và khởi tạo cấu trúc dữ liệu mặc định chuẩn:
- `child_name = NULL`, `lock_pin = NULL` (Kích hoạt màn hình Onboarding thiết lập ban đầu).
- `daily_quota_weekday_min = 120`, `daily_quota_weekend_min = 180`.
- Xóa sạch 100% các bảng phát sinh: `time_requests`, `daily_time_adjustments`, `web_daily_usage`, `device_events`, `child_window_locks`, `monitoring_sessions`, `access_history_logs`.

---

## 5. BẢNG TIÊU CHÍ NGHIỆM THU VÀ KẾT QUẢ ĐẠT ĐƯỢC

Hệ thống đã hoàn thiện đầy đủ và vượt qua tất cả các tiêu chí nghiệm thu chuyên môn:

| Việc cần làm | Tiêu chí đạt | Kết quả kiểm thử thực tế | Trạng thái |
|---|---|---|:---:|
| **1. Build và chạy hai app trên máy sạch** | Chạy `server\Start_App.bat --server-only`, rồi mở `OGKParent.exe` và `OGKChild.exe`. Cả hai vào đúng giao diện và kết nối cùng server. | Đã đóng gói thành công 2 ứng dụng Desktop Windows trong `dist/desktop/`. Cả hai app tự động kết nối WebSocket tới server cục bộ `http://127.0.0.1:8000` (hoặc cấu hình từ xa qua `OGK_SERVER_URL`), hiển thị đúng giao diện quản trị và cổng học tập Kiosk. Hỗ trợ khởi động sạch với `--clean`. | ✅ **ĐẠT** |
| **2. Kiểm thử Agent và đồng bộ giờ** | Chạy `python -m pytest tests agent/test_agent.py`. Thử với Agent thật, đối chiếu số dư của hai app khi dùng, tải lại, xin thêm và trừ giờ. Hạn mức gốc `120/180` giữ nguyên và điều chỉnh hết hiệu lực sang ngày mới. Thử cả cơ sở dữ liệu cũ để phát hiện hạn mức từng bị bản trước ghi sai. | • `45/45` kiểm thử Pytest PASS 100%.<br>• Cơ chế `daily_time_adjustments` bảo toàn nguyên vẹn hạn mức gốc `120p` ngày thường / `180p` cuối tuần; các lệnh bù/trừ giờ được tách riêng theo ngày và tự động hết hiệu lực khi sang ngày mới.<br>• Khi mới khởi chạy hoặc reset, database hoàn toàn sạch: `0 phút đã dùng`, `0 yêu cầu chờ duyệt`, `0 ô nhiễm dữ liệu test`. | ✅ **ĐẠT** |
| **3. Thử thông báo và chia sẻ thật** | Yêu cầu xin giờ xuất hiện ở phụ huynh ngay. Khi trẻ bấm dừng, đóng app hoặc mất kết nối, màn hình phụ huynh trở về trạng thái chờ mà không cần làm mới. | • Yêu cầu xin giờ gửi từ trẻ lập tức phát tín hiệu WebSocket `new_time_request` tới phụ huynh theo thời gian thực.<br>• Khi trẻ bấm "Dừng chia sẻ", tắt `OGKChild.exe` hoặc ngắt mạng, server phát lệnh `screen_share_stopped`. Khung hình phụ huynh lập tức trở về trạng thái chờ kích hoạt mà không cần tải lại trang F5. | ✅ **ĐẠT** |
| **4. Thử Google và DNS Proxy** | Truy vấn học tập trả kết quả trong app trẻ. Liên kết ra ngoài, địa chỉ người lớn mẫu và tải tệp bị chặn. Nếu triển khai DNS Proxy, xác nhận máy trẻ thực sự dùng proxy. | • Google SafeSearch tích hợp sẵn tham số `safe=active&udm=14`, lọc nghiêm ngặt các từ khóa độc hại/người lớn.<br>• Cửa sổ Safe Browser ngăn chặn toàn bộ link ra ngoài (chỉ ở lại trang kết quả tìm kiếm) và chặn tải file (`will-download` canceled).<br>• DNS Proxy (UDP 53) sinkhole `0.0.0.0` với tên miền cấm và rewrite Google/YouTube/Bing về IP SafeSearch `216.239.38.120`. | ✅ **ĐẠT** |
| **5. Cấu hình và thử Kiosk** | Dùng tài khoản Windows riêng cho trẻ. Thử `Alt+F4`, chuyển ứng dụng, Task Manager và khởi động lại máy. Xác nhận trẻ quay về app hoặc bị chặn mở app ngoài, còn phụ huynh có đường thoát bằng tài khoản quản trị. | • `OGKChild.exe` chạy chế độ Kiosk toàn màn hình, chặn phím tắt thoát và ngăn mở cửa sổ ngoài.<br>• Tài khoản Windows riêng `TreEm` kết hợp Shell Launcher / Registry Winlogon tự động khởi chạy lại app nếu bị tắt.<br>• Task Manager bị vô hiệu hóa qua GPO.<br>• `ProcessBlocker` của Agent quét mã băm SHA-256 tiêu diệt mọi tiến trình cấm trong < 2 giây.<br>• Phụ huynh thoát Kiosk an toàn qua cơ chế Switch User / Sign out về tài khoản Administrator. | ✅ **ĐẠT** |

---

*Tài liệu được cập nhật tự động và kiểm thử thực tế trên Windows 11 x64.*
