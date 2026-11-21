# HƯỚNG DẪN VẬN HÀNH & CHẠY CÁC THÀNH PHẦN ĐÃ ĐÓNG GÓI (OGK SYSTEM)

Tài liệu hướng dẫn chi tiết dành cho Kỹ sư Triển khai (DevOps), Quản trị viên và Kỹ thuật viên vận hành hệ thống **"Người Bạn Đồng Hành" (OGK Child Device & Network Protection System)** trên môi trường Windows 10/11 x64 độc lập (không cần Python).

---

## MỤC LỤC
1. [Tổng quan bộ đóng gói (Distribution Package)](#1-tổng-quan-bộ-đóng-gói-distribution-package)
2. [Cách đóng gói lại từ mã nguồn (`build_release.py`)](#2-cách-đóng-gói-lại-từ-mã-nguồn-build_releasepy)
3. [Vận hành Thành phần 1: Agent Giám sát (`agent_service.exe`)](#3-vận-hành-thành-phần-1-agent-giám-sát-agent_serviceexe)
4. [Vận hành Thành phần 2: DNS Proxy Server (`dns_proxy.exe`)](#4-vận-hành-thành-phần-2-dns-proxy-server-dns_proxyexe)
5. [Cấu hình Card Mạng chuyển tiếp DNS về máy con](#5-cấu-hình-card-mạng-chuyển-tiếp-dns-về-máy-con)
6. [Quy trình kiểm thử tích hợp (End-to-End Testing)](#6-quy-trình-kiểm-thử-tích-hợp-end-to-end-testing)
7. [Xử lý sự cố thường gặp (Troubleshooting)](#7-xử-lý-sự-cố-thường-gặp-troubleshooting)

---

## 1. TỔNG QUAN BỘ ĐÓNG GÓI (DISTRIBUTION PACKAGE)

Thư mục phát hành `dist_package/` và file nén `dist/OGK_Deploy_Package_x64.zip` chứa đầy đủ runtime độc lập, có thể mang sang bất kỳ máy tính Windows nào để chạy:

| Tên file / Thư mục | Loại | Mô tả chức năng |
| :--- | :---: | :--- |
| **`agent_service.exe`** | Binary (.exe) | Dịch vụ Windows Service chạy ngầm LocalSystem, đo thời gian (M6), chặn app SHA-256 |
| **`dns_proxy.exe`** | Binary (.exe) | Máy chủ DNS Proxy cục bộ lọc web đen, sinkhole 0.0.0.0, cưỡng chế SafeSearch & DoH Canary |
| **`blocklist.json`** | Dữ liệu (JSON) | Danh bạ hơn 6 nhóm tên miền cấm (Porn, Gambling, Social, Gaming, Malware, DoH) |
| **`Start_App.bat`** | Kịch bản (Batch) | Launcher duy nhất: bật máy chủ, `--with-agent`, `--with-dns` (Admin), `--reset`, `--stop` |
| **`install_service.bat`** | Kịch bản (Batch) | Kiểm tra Admin, nhập mã ghép đôi, đăng ký service + tự restart 5s (M5), đăng ký khay hệ thống |
| **`uninstall_service.bat`**| Kịch bản (Batch) | Gỡ cài đặt sau khi xác thực tài khoản phụ huynh (có audit log) |
| **`SHA256SUMS.txt`** | Checksum | Mã băm SHA-256 của từng file giúp kiểm tra tính toàn vẹn khi sao chép |
| **`HUONG_DAN_CAI_DAT.txt`**| Tài liệu (Text) | Hướng dẫn nhanh tại chỗ (Quick-start guide dưới 5 phút) |

---

## 2. CÁCH ĐÓNG GÓI LẠI TỪ MÃ NGUỒN (`build_release.py`)

Khi bạn cập nhật code trong thư mục `agent/` hoặc `dns_proxy/`, chạy lệnh sau tại thư mục gốc để tự động build lại toàn bộ:

```powershell
python build_release.py
```

### Quy trình tự động thực hiện:
- Tự kiểm tra và cài đặt `pyinstaller` nếu máy chưa có.
- Biên dịch `agent/main_service.py` -> `dist/agent_service.exe` (Chế độ `--onefile --noconsole`, nạp Windows API hooks).
- Biên dịch `dns_proxy/proxy_server.py` -> `dist/dns_proxy.exe` (Chế độ `--onefile`, nạp `dnslib`).
- Tạo thư mục chuẩn `dist_package/` chứa đầy đủ file thực thi, scripts và tài liệu.
- Tính mã băm `SHA256SUMS.txt` và nén thành `dist/OGK_Deploy_Package_x64.zip`.

---

## 3. VẬN HÀNH THÀNH PHẦN 1: AGENT GIÁM SÁT (`agent_service.exe`)

### A. Triển khai dưới dạng Windows Service (Khuyên dùng trong Production)
1. Copy thư mục `dist_package/` vào thư mục bảo vệ trên máy con, ví dụ: `C:\OGKAgent\`.
2. Click chuột phải vào **`install_service.bat`** -> Chọn **"Run as administrator"**.
3. Hệ thống sẽ tự động thực thi chuỗi lệnh tiêu chuẩn:
   ```cmd
   sc create "OGKChildAgent" binPath= "\"%~dp0agent_service.exe\"" start= auto DisplayName= "OGK Child Monitoring Agent" obj= LocalSystem
   sc failure "OGKChildAgent" reset= 86400 actions= restart/5000/restart/5000/restart/5000
   sc start OGKChildAgent
   ```
4. **Kiểm tra trạng thái Service**:
   - Mở PowerShell / CMD (Run as admin):
     ```cmd
     sc query OGKChildAgent
     ```
     *Trạng thái chuẩn: `STATE: 4 RUNNING`*
   - Kiểm tra cấu hình khôi phục crash (Tiêu chuẩn M5):
     ```cmd
     sc qfailure OGKChildAgent
     ```
     *Kết quả: `RESTART -- Delay = 5000 msecs`*

### B. Chạy ở Chế độ Console Gỡ lỗi (Debug Mode)
Nếu muốn quan sát trực tiếp log trên màn hình terminal mà không cần cài service:
```cmd
agent_service.exe --debug
```
*Nhấn `Ctrl + C` để dừng an toàn.*

### C. Gỡ cài đặt Service
Khi muốn gỡ hoàn toàn dịch vụ:
- Click chuột phải vào **`uninstall_service.bat`** -> Chọn **"Run as administrator"**.

---

## 4. VẬN HÀNH THÀNH PHẦN 2: DNS PROXY SERVER (`dns_proxy.exe`)

DNS Proxy có nhiệm vụ chặn các trang web cấm ngay từ tầng mạng (Network Layer) trước khi gói tin HTTP/HTTPS được thiết lập.

### A. Khởi chạy máy chủ DNS Proxy
1. Mở Command Prompt bằng **"Run as administrator"** trong thư mục gói và chạy `Start_App.bat --with-dns`.
   > *Lưu ý: Mở cổng UDP 53 trên hệ điều hành Windows bắt buộc phải có quyền Administrator.*
2. Cửa sổ dòng lệnh sẽ xuất hiện thông báo:
   ```text
   =================================================================
   OGK DNS PROXY SERVER LẮNG NGHE TẠI UDP 127.0.0.1:53
   [DNS_PROXY] Đã nạp danh sách tên miền cấm từ blocklist.json.
   Nhấn Ctrl + C để dừng server.
   =================================================================
   ```

### B. Chạy trực tiếp từ dòng lệnh
```cmd
dns_proxy.exe
```

---

## 5. CẤU HÌNH CARD MẠNG CHUYỂN TIẾP DNS VỀ MÁY CON

Để máy tính con đi qua DNS Proxy vừa bật, bạn trỏ DNS IPv4 về `127.0.0.1`:

### Cách 1: Bằng giao diện Windows GUI
1. Nhấn `Win + R`, gõ `ncpa.cpl` rồi nhấn **Enter** (mở Network Connections).
2. Click chuột phải vào Card mạng đang kết nối (Wi-Fi hoặc Ethernet) -> Chọn **Properties**.
3. Nhấp đúp vào **Internet Protocol Version 4 (TCP/IPv4)**.
4. Chọn **Use the following DNS server addresses**:
   - **Preferred DNS server**: `127.0.0.1`
   - **Alternate DNS server**: `8.8.8.8` (hoặc `1.1.1.1`)
5. Nhấn **OK** để áp dụng.

### Cách 2: Bằng 1 dòng lệnh PowerShell (Admin)
```powershell
# Xem tên Card mạng đang kết nối
Get-NetAdapter | Where-Object Status -eq 'Up'

# Đặt DNS 127.0.0.1 cho Card mạng (Ví dụ: Wi-Fi)
Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ServerAddresses ("127.0.0.1","8.8.8.8")
```

---

## 6. QUY TRÌNH KIỂM THỬ TÍCH HỢP (END-TO-END TESTING)

### Kiểm thử 1: Kiểm tra tính năng lọc Web đen (Sinkhole 0.0.0.0)
Mở một cửa sổ CMD và gõ truy vấn thử tên miền trong danh sách cấm:
```cmd
nslookup bet365.com 127.0.0.1
```
*Kết quả trả về:*
```text
Name:    bet365.com
Address: 0.0.0.0
```
-> *Địa chỉ IP trả về `0.0.0.0` chứng minh tính năng Sinkhole thành công, trình duyệt sẽ không thể mở trang web vi phạm.*

---

### Kiểm thử 2: Cưỡng chế Google SafeSearch
Gõ kiểm tra tên miền Google:
```cmd
nslookup forcesafesearch.google.com 127.0.0.1
nslookup www.google.com 127.0.0.1
```
*Kết quả trả về:* `216.239.38.120` (IP SafeSearch VIP của Google). Mọi nội dung 18+ khi tìm kiếm bằng Google Search / hình ảnh đều bị lọc tự động.

---

### Kiểm thử 3: Cưỡng chế YouTube Restricted Mode
```cmd
nslookup www.youtube.com 127.0.0.1
```
*Kết quả trả về:* `216.239.38.119` (IP YouTube Restricted VIP).

---

### Kiểm thử 4: Kiểm tra tính năng tự phục hồi của Service (M5)
1. Đảm bảo `OGKChildAgent` đang chạy (`sc query OGKChildAgent`).
2. Mở Task Manager -> Tab Details -> Tìm `agent_service.exe` -> Chọn **End Process** (cố ý làm crash).
3. Đợi đúng 5 giây, kiểm tra lại bằng lệnh:
   ```cmd
   sc query OGKChildAgent
   ```
4. Dịch vụ đã tự động được Windows khởi chạy lại thành công (Running)!

---

## 7. XỬ LÝ SỰ CỐ THƯỜNG GẶP (TROUBLESHOOTING)

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| :--- | :--- | :--- |
| **Báo lỗi `Access is denied` khi chạy file `.bat`** | Chưa chạy với quyền Administrator | Click chuột phải vào file `.bat`, chọn **"Run as administrator"**. |
| **DNS Proxy báo lỗi `Errno 10048 (Address already in use)`** | Cổng 53 đang bị dịch vụ khác chiếm (ví dụ: Internet Connection Sharing) | Chạy CMD (Admin): `netstat -ano \| findstr :53` để tìm PID chiếm cổng và tắt tiến trình đó. |
| **Không mở được blocklist.json** | Di chuyển file `dns_proxy.exe` ra khỏi thư mục chứa `blocklist.json` | Luôn giữ `dns_proxy.exe` và `blocklist.json` cùng một thư mục. |
| **Agent không đồng bộ được chính sách** | Server quản trị trung tâm chưa bật | Kiểm tra Server FastAPI đang chạy tại `http://127.0.0.1:8000`. Agent có cơ chế Offline Cache nên vẫn thực thi các chính sách đã lưu trước đó bình thường. |

