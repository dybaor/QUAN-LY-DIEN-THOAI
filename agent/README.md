# OGK AGENT - CLIENT GIÁM SÁT MÁY CON (HEADLESS DAEMON)

Module chạy ngầm dưới quyền `LocalSystem` trên máy tính của trẻ, phụ trách giám sát tiến trình, đo đếm thời gian sử dụng thiết bị và thực thi chính sách bảo vệ cục bộ ngay cả khi mất kết nối mạng.

---

## 1. CÁC TÍNH NĂNG KỸ THUẬT CỐT LÕI

- **Nhận diện và Chặn Ứng Dụng bằng Mã Băm SHA-256 (`blocker.py`):**
  - Quét danh sách tiến trình chạy trên hệ thống qua `psutil`.
  - Tính toán mã băm SHA-256 của file thực thi (`.exe`), vô hiệu hóa mọi thủ thuật đổi tên file để qua mặt hệ thống.
  - Tiêu diệt tiến trình bị cấm trong vòng dưới 2 giây.
- **Bộ Đếm Thời Gian Monotonic & Chống Gian Lận Giờ (`tracker.py`):**
  - Sử dụng hàm `time.monotonic()` độc lập hoàn toàn với đồng hồ hệ thống Windows.
  - Tự động phát hiện thủ thuật lùi giờ (`clock_tamper`) nếu người dùng chỉnh thời gian máy tính về quá khứ.
  - Nhận diện trạng thái nhàn rỗi (`Idle Detection` qua API `GetLastInputInfo`) để dừng tính giờ khi trẻ rời khỏi máy tính.
- **Bộ Nhớ Đệm SQLite Cục Bộ Chế Độ WAL (`local_cache.py`):**
  - Lưu trữ bản sao chính sách gần nhất (`ogk_cache.db`).
  - Hàng đợi sự kiện offline (`offline_events`): Lưu lại các vi phạm khi mất mạng và tự động đồng bộ lên Server ngay khi có kết nối trở lại.
- **Kênh Giao Tiếp WebSocket Thời Gian Thực (`ws_client.py`):**
  - Duy trì kết nối hai chiều với Server, phản hồi lệnh khóa/mở khóa từ phụ huynh trong thời gian < 1 giây.
- **Triệt tiêu 100% Thông báo Hệ điều hành:**
  - Tuyệt đối không bật hộp thoại ngoài desktop (`WTSSendMessageW`, `ctypes MessageBox`), toàn bộ thông báo cảnh báo đều chuyển thành WebSocket Toast hiển thị nội bộ trong Web Portal của trẻ.

---

## 2. HƯỚNG DẪN KHỞI CHẠY VÀ VẬN HÀNH

### Chế độ 1: Chạy Debug Trực Tiếp Trên Terminal (Khuyên dùng khi phát triển & demo)
```powershell
python agent/main_service.py debug
```
Lệnh này sẽ khởi động vòng lặp giám sát của Agent ngay trên cửa sổ console, hiển thị trực quan log kiểm tra tiến trình và đồng bộ thời gian thực.

### Chế độ 2: Cài Đặt Làm Dịch Vụ Windows Service (Production)
Yêu cầu mở PowerShell hoặc Command Prompt bằng **Run as Administrator**:
```powershell
# 1. Cài đặt và kích hoạt dịch vụ tự khởi động cùng Windows
cd agent
.\install_service.bat

# 2. Kiểm tra trạng thái dịch vụ
sc query OGKChildAgent

# 3. Gỡ bỏ dịch vụ khi cần
.\uninstall_service.bat
```

