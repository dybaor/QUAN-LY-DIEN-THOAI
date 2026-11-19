# Ứng dụng OGK cho Windows

Hai ứng dụng dùng chung backend OGK. Để chạy thử trên cùng máy, mở Command Prompt ở thư mục dự án và chạy:

```bat
server\Start_App.bat --server-only
```

Khi server chạy tại `127.0.0.1:8000`, mở `OGKParent.exe` cho phụ huynh và `OGKChild.exe` cho trẻ. Mỗi file EXE cần các file runtime đi kèm trong thư mục của nó. Ứng dụng trẻ mở toàn màn hình. Google mở trong cửa sổ OGK riêng, chỉ cho phép trang kết quả tìm kiếm với SafeSearch, chặn mở website từ kết quả và không cho tải tệp.

## Tạo hai bản Windows x64

Từ thư mục gốc dự án:

```text
npm --prefix desktop ci
npm --prefix desktop run build:windows
```

Kết quả nằm trong `dist/desktop/OGKParent-win32-x64` và `dist/desktop/OGKChild-win32-x64`. Để chạy từ mã nguồn, dùng `npm --prefix desktop run parent` và `npm --prefix desktop run child`.

## Khóa thoát trên máy trẻ

Chế độ toàn màn hình của app dùng để thử giao diện. Trên máy trẻ do phụ huynh quản lý, dùng tài khoản Windows riêng không có quyền quản trị, cấu hình [Shell Launcher](https://learn.microsoft.com/en-us/windows/configuration/shell-launcher/quickstart-kiosk) trỏ tới `OGKChild.exe` và đặt hành động khi thoát là khởi động lại ứng dụng. Giới hạn các ứng dụng và thành phần hệ thống khác với chính sách Windows phù hợp. Shell Launcher hỗ trợ các phiên bản Windows Enterprise, Education và IoT Enterprise theo [tài liệu Microsoft](https://learn.microsoft.com/en-us/windows/configuration/shell-launcher/). Giữ một tài khoản quản trị riêng để thoát và bảo trì.

Các bản này mặc định dùng server cục bộ. Với hai máy riêng, người quản trị có thể đặt biến môi trường `OGK_SERVER_URL` cùng trỏ tới một server HTTPS trong mạng được quản lý. Giới hạn mạng được phép kết nối với backend. Không mở cổng API OGK trực tiếp ra Internet.
