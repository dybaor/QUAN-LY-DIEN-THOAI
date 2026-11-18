# OGK SERVER - MÁY CHỦ QUẢN LÝ & WEB DASHBOARD

Module trung tâm phụ trách lưu trữ chính sách bảo vệ, quản trị cơ sở dữ liệu SQLite, điều phối kết nối thời gian thực WebSocket và phục vụ giao diện Web cho cả Phụ huynh lẫn Trẻ em.

---

## 1. CHỨC NĂNG CHÍNH

- **Quản lý Chính sách (Policy Management):** Lưu trữ giới hạn thời gian (Daily Quota), ma trận lịch tuần 168 khung giờ (7 ngày x 24 giờ), danh mục ứng dụng/tên miền cấm, mã PIN mở khóa bảo vệ.
- **WebSocket Gateway thời gian thực:**
  - Nhận và điều phối lệnh khẩn cấp (`lock_window`, `unlock_window`, `extend_time`, `request_screen_consent`).
  - Chuyển tiếp luồng khung hình chia sẻ màn hình trực tiếp dạng nhị phân (**Binary JPEG Blob 15–30 FPS**) từ máy con sang Dashboard phụ huynh với độ trễ thấp.
- **Phục vụ Giao diện Web (Zero Native Windows):**
  - **Parent Dashboard (`/`):** Giao diện quản trị toàn diện, bảng điều khiển tối giản, xem màn hình trực tiếp và duyệt yêu cầu thêm giờ.
  - **Child Web Portal (`/child`):** Không gian học tập an toàn của trẻ, tích hợp In-Page Lock Overlay (tuyệt đối không can thiệp khóa màn hình Windows OS) và xác thực mã PIN bảo mật 100%.

---

## 2. CÁC API ENDPOINTS CHÍNH

| Method | Endpoint | Mô tả |
| :--- | :--- | :--- |
| `GET` | `/` | Web Dashboard dành cho Phụ huynh |
| `GET` | `/child` | Trạm học tập Child Web Portal |
| `GET` | `/policy/{child_id}` | Lấy thông tin chính sách bảo vệ mới nhất |
| `PUT` | `/policy/{child_id}` | Cập nhật chính sách (168 giờ, app cấm, hạn mức) |
| `POST` | `/api/settings` | Cập nhật tên bé và mã PIN khóa máy |
| `POST` | `/api/settings/verify-pin` | Xác thực mã PIN mở khóa (so khớp chính xác với DB) |
| `POST` | `/commands/send` | Gửi lệnh tức thời (Khóa/Mở khóa/Xem màn hình) |
| `POST` | `/requests/` | Trẻ gửi yêu cầu xin thêm giờ học |
| `WS` | `/ws/{device_id}` | WebSocket giao tiếp thời gian thực cho Dashboard / Agent |
| `WS` | `/ws/child/{guid}` | WebSocket chuyên biệt cho Child Portal (Binary Frame Streaming) |

---

## 3. CÁCH KHỞI CHẠY ĐỘC LẬP

```powershell
# Chạy trực tiếp qua script runner
python server/run_server.py

# Hoặc khởi chạy thông qua uvicorn CLI
uvicorn server.app.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Cổng kết nối mặc định:** `8000`
- **Địa chỉ truy cập phụ huynh:** `http://127.0.0.1:8000`
- **Địa chỉ truy cập máy con:** `http://127.0.0.1:8000/child`
- **Tài liệu API Swagger tự động:** `http://127.0.0.1:8000/docs`

