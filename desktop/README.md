# Ứng dụng OGK cho Windows

Hai ứng dụng dùng chung backend OGK. Để chạy thử trên cùng máy, mở Command Prompt ở thư mục dự án và chạy:

```bat
Start_App.bat --server-only
```

Khi server chạy tại `127.0.0.1:8000`, mở `OGKParent.exe` cho phụ huynh và `OGKChild.exe` cho trẻ. Mỗi file EXE cần các file runtime đi kèm trong thư mục của nó. Ứng dụng trẻ mở toàn màn hình và cần ghép đôi bằng mã 8 ký tự tạo trên Dashboard (mục "Thiết bị của trẻ"). Google mở trong cửa sổ OGK riêng, chỉ cho phép trang kết quả tìm kiếm với SafeSearch, chặn mở website từ kết quả và không cho tải tệp.

## Tạo hai bản Windows x64

Từ thư mục gốc dự án, dùng Node.js 22.12 trở lên:

```text
npm --prefix desktop ci
npm --prefix desktop run build:windows
```

Kết quả nằm trong `dist/desktop/OGKParent-win32-x64` và `dist/desktop/OGKChild-win32-x64`. Để chạy từ mã nguồn, dùng `npm --prefix desktop run parent` và `npm --prefix desktop run child`.

## Khóa thoát trên máy trẻ

1. Trên máy trẻ dùng Windows Enterprise, Education hoặc IoT Enterprise, tạo tài khoản cục bộ chuẩn `OGKChild` và giữ một tài khoản quản trị riêng. Sao chép toàn bộ nội dung `OGKChild-win32-x64` vào `%ProgramFiles%\OGKChild` để tài khoản trẻ chỉ có quyền đọc và thực thi. [Yêu cầu Windows của Shell Launcher](https://learn.microsoft.com/en-us/windows/configuration/shell-launcher/).
2. Áp dụng [shell-launcher.xml](shell-launcher.xml) qua Assigned Access CSP. Nếu tên tài khoản hoặc thư mục cài đặt khác, sửa các giá trị tương ứng trong XML. Hồ sơ của trẻ khởi động lại OGK mỗi khi tiến trình thoát. Tài khoản quản trị vào Windows Explorer. [Cách áp dụng cấu hình Shell Launcher](https://learn.microsoft.com/en-us/windows/configuration/shell-launcher/configure).
3. Dùng AppLocker để giới hạn ứng dụng có thể chạy từ tài khoản trẻ. Tạo chính sách người dùng cục bộ riêng cho `OGKChild` và bật **User Configuration → Administrative Templates → System → Ctrl+Alt+Del Options → Remove Task Manager**. Kiểm tra chính sách thực thi theo đúng tài khoản trẻ. [Tài liệu AppLocker](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/applocker/applocker-overview).
4. Kiểm thử sau khi đăng nhập bằng `OGKChild`. Thử Alt+F4, Alt+Tab, Task Manager, mở ứng dụng khác, rồi khởi động lại máy và đăng nhập lại. Dùng Ctrl+Alt+Del để đăng xuất và xác minh tài khoản quản trị vẫn vào được Explorer. Nếu server đặt cùng máy kiosk, cấu hình server khởi động trước lúc tài khoản trẻ đăng nhập.

Các bản này mặc định dùng server cục bộ. Với hai máy riêng, người quản trị có thể đặt biến môi trường `OGK_SERVER_URL` cùng trỏ tới một server HTTPS trong mạng được quản lý. Giới hạn mạng được phép kết nối với backend. Không mở cổng API OGK trực tiếp ra Internet.
