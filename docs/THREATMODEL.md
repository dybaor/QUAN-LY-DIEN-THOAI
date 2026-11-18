# MÔ HÌNH PHÂN TÍCH ĐE DỌA AN TOÀN HỆ THỐNG (THREAT MODEL - STRIDE)
## DỰ ÁN: NGƯỜI BẠN ĐỒNG HÀNH (OGK SYSTEM)
> **Phương pháp luận:** Microsoft STRIDE Threat Modeling Framework  
> **Phạm vi phân tích:** Máy con (OGK-Agent Service, DNS Proxy), Máy chủ (OGK-Server FastAPI), Kênh truyền (WebSocket, HTTPS), Cơ sở dữ liệu (SQLite WAL, Local Cache).

---

## 1. Sơ đồ Ranh giới Tin cậy (Trust Boundaries & Data Flow Diagram)

```text
       [Trình duyệt của trẻ] 
                | 
       =========|================== (Trust Boundary 1: User Space -> SYSTEM)
                v
       [DNS Proxy 127.0.0.1:53] <---> [Local Cache %ProgramData%\OGKAgent]
                ^
                | IPC / In-Memory
                v
       [OGK-Agent Windows Service (LocalSystem)]
                |
       =========|================== (Trust Boundary 2: Client PC -> LAN / Internet)
                | HTTPS (TLS 1.2+) & WSS
                v
       [OGK-Server (FastAPI / Uvicorn)]
                |
                v
       [SQLite Database (WAL Mode)]
```

---

## 2. Bảng Phân tích Chi tiết 6 Tiêu chí STRIDE

### 2.1. Spoofing Identity (Giả mạo Danh tính)
- **Mối đe dọa:** Máy lạ trong mạng LAN giả mạo Agent gửi sự kiện rác hoặc kẻ xấu giả mạo phụ huynh ra lệnh khóa máy.
- **Biện pháp đối phó:**
  - Quy trình Ghép đôi (Enrollment) 2 bước: Phụ huynh sinh mã 8 ký tự chỉ có hạn 10 phút. Agent phải gửi mã kèm MachineGuid phần cứng (Fingerprint) để nhận cặp JWT token (Access ngắn hạn 15 phút, Refresh token).
  - Mọi API cấu hình và lệnh khẩn cấp qua WebSocket đều yêu cầu xác thực JWT / Bearer Token.

### 2.2. Tampering with Data (Xâm phạm Toàn vẹn Dữ liệu)
- **Mối đe dọa:** 
  1. Trẻ chỉnh lùi giờ Windows 2-3 tiếng để gian lận Quota.
  2. Trẻ mở tệp tin SQLite `%ProgramData%\OGKAgent\agent_cache.db` để sửa thời gian đã dùng về 0.
  3. Trẻ đổi tên file game `roblox.exe` thành `winword.exe` để qua mặt bộ lọc.
- **Biện pháp đối phó:**
  - **Chống lùi giờ (M6):** Đo thời gian bằng `time.monotonic()` phần cứng CPU; phát hiện độ lệch lùi giờ > 60s sẽ lập tức phát sinh sự kiện vi phạm `clock_tamper`.
  - **Bảo mật tệp tin ACL:** Thư mục `%ProgramData%\OGKAgent` được khóa bằng Windows ACL (`icacls`), chỉ cấp toàn quyền cho `NT AUTHORITY\SYSTEM` và `Administrators`; tài khoản Standard User của trẻ không có quyền đọc/ghi.
  - **Nhận diện bằng mã băm SHA-256:** Agent tính toán hash nhị phân của tệp tin, bất chấp đổi tên file thì hash vẫn trùng khớp với blacklist.

### 2.3. Repudiation (Chối bỏ Trách nhiệm)
- **Mối đe dọa:** Trẻ hoặc người dùng phủ nhận việc truy cập trang web cấm hoặc mở game trong giờ học.
- **Biện pháp đối phó:**
  - Mọi sự kiện đều được gắn timestamp ISO-8601 UTC và ghi nhật ký kiểm toán bất biến (Audit Log) theo lược đồ 7 trường chuẩn: `ts`, `device_id`, `child_id`, `type`, `subject`, `duration_sec`, `policy_id`.
  - Dữ liệu sự kiện được lưu song song tại Local Cache SQLite WAL và Server FastAPI.

### 2.4. Information Disclosure (Tiết lộ Thông tin Nhạy cảm)
- **Mối đe dọa:** Lộ lọt lịch sử duyệt web hoặc thông tin cá nhân của trẻ ra bên ngoài Internet.
- **Biện pháp đối phó:**
  - **Tuân thủ Nghị định 13/2023:** Tuyệt đối không lưu URL đầy đủ, chỉ lưu tên miền cấp hai (ví dụ: `google.com`).
  - Tuyệt đối không chụp màn hình, không dùng keylogger.
  - Mã hóa kênh truyền qua HTTPS / TLS 1.2+ và WebSocket an toàn (WSS).

### 2.5. Denial of Service (Từ chối Dịch vụ)
- **Mối đe dọa:** 
  1. Trẻ mở Task Manager bấm "End Task" tiến trình Agent hoặc ngắt mạng để Agent không thể kiểm soát.
  2. Trẻ spam DNS query làm tràn bộ nhớ DNS Proxy.
- **Biện pháp đối phó:**
  - **Quyền LocalSystem:** Service chạy dưới tài khoản `NT AUTHORITY\LocalSystem`, tài khoản trẻ không thể tắt (`Access is Denied`).
  - **Khả năng chịu lỗi (M5):** Cấu hình `sc failure` tự động restart Service sau 5 giây nếu bị kill.
  - **Chế độ Ngoại tuyến (Offline Mode):** Khi mất mạng, Agent tự động dùng policy trong SQLite cache, tiếp tục đếm giờ và cưỡng chế khóa máy độc lập.
  - **Tối ưu DNS Socket:** Sử dụng `ThreadingUDPServer` đa luồng, xử lý truy vấn trong bộ nhớ RAM cực nhanh ($p_{50} < 6\text{ms}$), không bị nghẽn socket.

### 2.6. Elevation of Privilege (Leo thang Đặc quyền)
- **Mối đe dọa:** Trẻ lợi dụng quyền thực thi của Windows Service (LocalSystem) để thực thi lệnh trái phép hoặc chiếm quyền Administrator.
- **Biện pháp đối phó:**
  - Service không mở bất kỳ port IPC nào không xác thực.
  - Giao diện người dùng (Tray UI / Notification) chạy tách biệt trong User Session, chỉ nhận thông báo 1 chiều qua Windows API chuẩn `WTSSendMessageW`, không chia sẻ bộ nhớ hoặc Handle nhạy cảm giữa Session 0 và User Session.

