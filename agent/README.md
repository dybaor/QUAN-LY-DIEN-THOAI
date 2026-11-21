# OGK AGENT — WINDOWS SERVICE + BIỂU TƯỢNG KHAY HỆ THỐNG

Agent gồm hai tiến trình:

- **`main_service.py`**: Windows Service `OGKChildAgent` (LocalSystem, tự khởi động lại sau 5 giây). Service đếm giờ, chặn ứng dụng, thực thi hạn mức và lịch, đồng bộ với máy chủ.
- **`tray_ui.py`**: biểu tượng khay chạy trong phiên đăng nhập của trẻ. Khay chỉ gửi trạng thái phiên (nhàn rỗi, ứng dụng đang dùng, màn hình khóa) cho Service qua named pipe `\\.\pipe\OGKAgentUI`, hiển thị thời gian còn lại ở tooltip và có mục mở Cổng học tập.

**Nguyên tắc: Agent không đụng vào Windows.** Không `LockWorkStation`, không hộp thoại/popup, không tắt máy. Agent chỉ chặn tiến trình bị cấm và **ghi sự kiện**; mọi thứ trẻ nhìn thấy (khóa, cảnh báo, lý do chặn) nằm trong Cổng học tập (overlay web), do máy chủ quyết định theo hạn mức, lịch tuần và lệnh của phụ huynh.

## Tính năng

| Mã | Mô tả | File |
| --- | --- | --- |
| KT-2 | Ghép đôi bằng mã 8 ký tự + fingerprint (MachineGuid), nhận device_id, token, khóa ký | `enrollment.py` |
| KT-3 | Heartbeat 60 giây gửi `quota_used`, nhận `server_time` | `ws_client.py` |
| KT-4 | WebSocket `/ws/agent` (Bearer token): khóa ngay, mở khóa, +giờ, xóa cache | `ws_client.py`, `main_service.py` |
| KT-5 | Cache SQLite WAL, hàng đợi sự kiện có `idempotency_key`, chạy được khi mất mạng | `local_cache.py` |
| F1-2/F1-4 | Lịch 7×48 khung 30 phút (máy chủ thực thi bằng overlay web), cảnh báo 10/5/1 phút và ân hạn 60 giây: Agent ghi `quota_warning` / `locked` | `enforcer.py` |
| F1-3/F1-5 | Không đếm khi màn hình khóa hoặc nhàn rỗi > 5 phút; phát hiện chỉnh đồng hồ bằng monotonic và giờ máy chủ | `tracker.py` |
| F2-1/F2-2 | Chặn ứng dụng theo SHA-256 (chỉ băm file đúng kích thước nên dừng < 1 giây), ghi `blocked_app`; máy chủ báo lý do cho trẻ trong Cổng học tập | `blocker.py` |
| F4-2 | Chỉ nạp chính sách có chữ ký HMAC-SHA256 hợp lệ, từ chối bản cũ hơn | `ws_client.py` |
| F5-3 | TLS 1.2+, ghim chứng chỉ (`OGK_CERT_SHA256`), refresh token xoay vòng | `transport.py` |
| F5-4 | Token và khóa ký mã hóa AES-256-GCM; khóa AES bảo vệ bằng DPAPI | `secure_store.py` |
| F5-6 | Không thấy khay hệ thống quá 2 phút thì tạm dừng giám sát và báo phụ huynh | `ui_bridge.py`, `main_service.py` |
| F4-MR1 | Gỡ cài đặt bắt buộc có tài khoản phụ huynh, ghi log | `uninstall_agent.py` |

## Cấu hình

Đặt bằng biến môi trường hoặc trong `%ProgramData%\OGKAgent\agent_config.json`:

| Biến | Ý nghĩa |
| --- | --- |
| `OGK_SERVER_URL` | Địa chỉ máy chủ. Mặc định `http://127.0.0.1:8000`; bắt buộc `https://` nếu không phải máy này |
| `OGK_CERT_SHA256` | Vân tay SHA-256 của chứng chỉ máy chủ để ghim chứng chỉ |
| `OGK_CA_BUNDLE` | File CA riêng (tùy chọn) |

## Sử dụng

```powershell
pip install -r agent/requirements.txt
python agent/main_service.py enroll ABCD1234   # mã tạo trên Dashboard > Thiết bị của trẻ
python agent/main_service.py debug              # chạy trực tiếp kèm biểu tượng khay (hoặc Start_App.bat --with-agent)
python agent/main_service.py status
```

Cài làm Windows Service (Run as Administrator):

```powershell
.\agent\install_service.bat     # nhập mã ghép đôi, cài service và biểu tượng khay
.\agent\uninstall_service.bat   # yêu cầu tài khoản phụ huynh
```
