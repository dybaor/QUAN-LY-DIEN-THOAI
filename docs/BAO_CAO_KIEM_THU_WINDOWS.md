# Báo cáo kiểm thử OGK trên Windows

Ngày 19/11/2026. Môi trường kiểm thử dùng Windows Pro x64, Python 3.13 và Node.js 22. Dữ liệu giao dịch thử nghiệm nằm trong SQLite và hồ sơ Electron riêng.

| Hạng mục | Kết quả quan sát |
|---|---|
| Build và khởi chạy | Build hai gói Windows x64. Launcher `server\Start_App.bat --server-only` cài phụ thuộc vào môi trường thử nghiệm riêng. `OGKParent.exe` vào `/`, `OGKChild.exe` vào `/child`, cả hai kết nối cùng FastAPI tại `127.0.0.1:8000`. Đã thử trên máy hiện tại với môi trường Python, SQLite và hồ sơ Electron mới. Chưa thử trên máy Windows vừa cài hệ điều hành. |
| Agent và số dư | Trong lượt GUI, hai app cùng hiển thị 118 phút trước khi duyệt, 133 phút sau khi duyệt 15 phút và 128 phút sau khi trừ 5 phút. Sau khi tải lại, cả hai vẫn hiển thị 128 phút. Trong lượt đo riêng, Agent chạy chế độ debug trong phiên Windows tương tác và gửi số giây tăng từ 48 lên 53. API của hai app cùng giảm số dư từ 8.952 xuống 8.947 giây. Ngưỡng idle của lượt đo riêng được nâng tạm trong tiến trình kiểm thử vì phiên Windows đã nhàn rỗi hơn 5 phút. Ngưỡng mặc định là 5 phút. Chưa thử đếm giờ khi Agent chạy bằng Windows Service. |
| Hạn mức ngày mới và SQLite cũ | Mốc thời gian giả lập xác nhận điều chỉnh hết hiệu lực qua ngày mới và gửi lại heartbeat không cộng trùng. Cơ sở dữ liệu đi kèm có hạn mức gốc 120/180. Trên bản sao giả lập dữ liệu cũ bị ghi thành 105/195, server đọc ra đúng các số đã lưu để phụ huynh đối chiếu. Sau khi lưu lại 120/180, gia hạn 10 phút được ghi riêng theo ngày. Giá trị lệch 120/180 có thể là thiết lập hợp lệ của phụ huynh, nên chỉ sửa sau khi đối chiếu. |
| Thông báo và chia sẻ | Yêu cầu xin giờ xuất hiện trên GUI phụ huynh sau 0,24 giây ở một lượt. Đã nhận khung hình thật rộng 800 px. Trạng thái phụ huynh về chờ khi bấm dừng ở app trẻ, đóng WebSocket và đóng app trẻ. Thử kết nối WebSocket im lặng không trả pong và thấy sự kiện dừng tới phụ huynh sau 10 giây. |
| Google | App mở truy vấn `pythagorean theorem` với `safe=active`. Google báo lưu lượng bất thường và đưa tới trang xác minh, nên lượt này chưa xác nhận được trang kết quả học tập. Đã thử trên cửa sổ Electron thật và xác nhận chặn liên kết ra ngoài, tải tệp Blob và địa chỉ người lớn mẫu. [Thông tin về trang xác minh của Google](https://support.google.com/websearch/answer/86640). |
| DNS Proxy | Proxy cục bộ trả `216.239.38.120` và `2001:4860:4802:32::78` cho Google. Tên miền người lớn mẫu trả `0.0.0.0` cho truy vấn A, còn `example.com` phân giải qua upstream. Máy kiểm thử vẫn phân giải mặc định qua `8.8.8.8`. Proxy mới được kiểm tra bằng truy vấn chỉ định resolver loopback, chưa triển khai làm DNS của máy trẻ. |
| Kiosk | Đã chuẩn bị [cấu hình Shell Launcher](../desktop/shell-launcher.xml) và [quy trình triển khai](../desktop/README.md). Cấu hình gán riêng tài khoản chuẩn `OGKChild` với hành động `RestartShell` và dùng Explorer cho tài khoản quản trị. Windows Pro không hỗ trợ Shell Launcher. Kiểm thử Alt+F4, chuyển ứng dụng, Task Manager và khởi động lại dưới tài khoản kiosk cần máy Enterprise, Education hoặc IoT Enterprise. |

## Kiểm thử tự động

- `python -m pytest tests agent/test_agent.py` — 46 bài qua.
- `node --test tests/ui_behavior.test.cjs` — 43 bài qua.

## Chạy bản build

Từ thư mục gốc chạy `server\Start_App.bat --server-only`. Giữ nguyên hai thư mục runtime khi sao chép các bản build.

- [OGKParent.exe](../dist/desktop/OGKParent-win32-x64/OGKParent.exe)
- [OGKChild.exe](../dist/desktop/OGKChild-win32-x64/OGKChild.exe)
