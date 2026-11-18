# KÊ KHAI SỬ DỤNG TRÍ TUỆ NHÂN TẠO (AI) & NHẬT KÝ DEBUG LỖI
## DỰ ÁN: NGƯỜI BẠN ĐỒNG HÀNH (OGK SYSTEM)
> **Tuân thủ quy chế học vụ:** Minh bạch việc sử dụng công cụ AI trong quá trình nghiên cứu và phát triển đồ án.

---

## 1. Bản Kê khai Sử dụng AI (AI Usage Declaration)

- **Các công cụ AI đã sử dụng:** Google Antigravity, Gemini 1.5 Pro / Flash.
- **Phạm vi và Mục đích Sử dụng:**
  1. *Khởi tạo mã khung (Boilerplate):* Sinh cấu trúc khung ban đầu cho Pydantic schemas, SQLAlchemy models và FastAPI routers.
  2. *Tra cứu tài liệu kỹ thuật Windows API:* Tra cứu cấu trúc `LASTINPUTINFO` của hàm `GetLastInputInfo` và chữ ký hàm `WTSSendMessageW` trong thư viện `wtsapi32.dll`.
  3. *Tối ưu hóa thuật toán:* Tham khảo thuật toán đo phân vị Percentile ($p_{50}, p_{95}$) thuần Python và cấu trúc đa luồng `socketserver.ThreadingMixIn` cho DNS Proxy.
  4. *Rà soát chuẩn mã nguồn:* Hỗ trợ rà soát chuẩn PEP8, gợi ý cấu trúc tài liệu Báo cáo An toàn Mạng M1–M4 và mô hình đe dọa STRIDE.
- **Cam kết của Nhóm sinh viên:**
  - Toàn bộ logic nghiệp vụ cốt lõi (Anti-tamper Monotonic Clock, SHA-256 Process Matching, Chế độ Offline SQLite, DNS Sinkhole & SafeSearch rewrite) đều do sinh viên trực tiếp thiết kế, kiểm thử và làm chủ 100%.
  - Toàn bộ kết quả thực nghiệm và số liệu đo đạc (M1, M4, M5, M6) được chạy trực tiếp trên môi trường Windows 11 thật và kiểm chứng qua Wireshark.

---

## 2. Nhật ký Xử lý Lỗi Kỹ thuật (Technical Debugging Log)

| STT | Hiện tượng Lỗi (Bug / Issue) | Nguyên nhân Kỹ thuật Sâu xa | Biện pháp Khắc phục của Nhóm |
| :---: | :--- | :--- | :--- |
| **1** | **Lỗi Session 0 Isolation:** Service chạy LocalSystem gọi `MessageBox` không hiện trên màn hình máy tính của trẻ. | Từ Windows Vista trở lên, Service chạy cách ly trong Session 0 không có giao diện đồ họa (GUI), trong khi trẻ đăng nhập ở Session 1. | Sử dụng Windows API `wtsapi32.dll` hàm `WTSSendMessageW` kết hợp `WTSGetActiveConsoleSessionId()` để gửi popup xuyên session từ Session 0 sang Session 1 an toàn. |
| **2** | **Lỗi DNSError khi parse NXDOMAIN:** Truy vấn Canary DoH bị văng lỗi `DNSError: Error: RDATA must be RD instance [NoneType]`. | Trong thư viện `dnslib`, khi DNS Response có mã lỗi NXDOMAIN thì phần Answer Section (`rr`) rỗng. Truy cập vào thuộc tính `resp.a` sẽ gọi hàm khởi tạo `RR()` không tham số dẫn đến crash. | Thay thế bằng cú pháp an toàn: `ip = str(resp.rr[0].rdata) if resp.rr else "NXDOMAIN"`. |
| **3** | **Lỗi khóa cơ sở dữ liệu SQLite (`database is locked`):** Nhiều luồng ghi đồng thời vào local cache gây nghẽn. | Mặc định SQLite sử dụng Rollback Journal, khi một luồng ghi thì toàn bộ database bị khóa độc quyền (Exclusive Lock). | Kích hoạt chế độ **WAL (Write-Ahead Logging)** bằng lệnh `PRAGMA journal_mode=WAL;` và `PRAGMA synchronous=NORMAL;` kết hợp `threading.Lock()` trong Python. |
| **4** | **Lỗi đếm sai khi chỉnh giờ hệ thống:** Trẻ lùi đồng hồ Windows 3 tiếng khiến thời gian sử dụng bị âm hoặc cộng thêm quota. | Sử dụng hàm `datetime.now()` phụ thuộc vào đồng hồ hệ thống (Wall clock), dễ bị thao túng qua Control Panel / Settings. | **BẮT BUỘC** chuyển sang sử dụng `time.monotonic()` phần cứng CPU. Kết hợp hàm `check_clock_tamper()` đo độ lệch $\Delta_{\text{mono}} - \Delta_{\text{wall}} > 60\text{s}$ để phát hiện và cảnh báo vi phạm. |
| **5** | **Lỗi đứt kết nối WebSocket khi mạng chập chờn:** Agent mất kết nối với Server nhưng không tự reconnect. | Socket WebSocket bị đóng bất ngờ từ phía Server hoặc tầng mạng LAN khiến luồng lắng nghe bị ngắt. | Xây dựng vòng lặp `while not self._stop_event.is_set():` với cơ chế Exponential Backoff: tự động thử kết nối lại sau mỗi 5 giây, bảo toàn trạng thái lắng nghe lệnh khẩn cấp liên tục. |

