# Báo cáo nâng cấp giao diện OGK

Ngày thực hiện 17/11/2026.

## Phạm vi đã triển khai

### Dashboard phụ huynh

- Dùng nền sáng, thẻ trắng, xanh ngọc và font Inter có font hệ thống dự phòng.
- Đưa số phút còn lại lên làm thông tin nổi bật, hiển thị thời lượng đã dùng và hạn mức ngay bên dưới.
- Đặt yêu cầu xin thêm giờ cạnh thẻ thời gian. Thu gọn các nút giảm thời gian trong mục điều chỉnh.
- Thêm liên kết tới tổng quan, thời gian biểu, ứng dụng, hoạt động, thiết bị và cài đặt.
- Thu gọn phần xem màn hình khi chờ, mở khung hình khi chuyển sang trạng thái trực tiếp.
- Bổ sung giao diện cho các hàm quản lý ứng dụng bị chặn đang có trong dự án.

### Thời gian biểu

- Chỉnh hạn mức ngày thường và cuối tuần bằng ô nhập có kiểm tra từ 0 đến 1440 phút.
- Chọn các ngày, giờ bắt đầu, giờ kết thúc và trạng thái được dùng hoặc giờ nghỉ.
- Hiển thị lịch theo từng ngày, gộp các giờ liên tiếp cùng trạng thái.
- Cung cấp lịch mẫu và phần chỉnh từng ô trong tuần có thể thao tác bằng bàn phím.
- Hỗ trợ lịch qua nửa đêm và chuyển từ Chủ nhật sang thứ 2.
- Giữ dữ liệu chỉnh sửa khi lưu thất bại hoặc khi tải lại chính sách trong lúc còn thay đổi chưa lưu.
- Chặn yêu cầu lưu trùng khi một lần lưu đang xử lý. Kiểm tra cả các chỉnh sửa phát sinh trong thời gian chờ phản hồi.
- Tiếp tục đọc lịch cũ 336 ô và chuyển sang 168 ô theo logic tương thích đang có trong dự án.

### Cổng của trẻ

- Dùng nền kem, thẻ ứng dụng trắng và nút xanh ngọc.
- Thu gọn khu vực chào và tìm kiếm để danh sách ứng dụng xuất hiện cao hơn.
- Rút gọn tên nhóm ứng dụng, chỉ hiện nhãn giới hạn trên các ứng dụng bị khóa.
- Bổ sung tên truy cập cho nút mở ứng dụng và ô tìm kiếm.
- Điều chỉnh màu các hộp thoại, màn hình nghỉ, thông báo và khung trò chuyện.
- Bổ sung CSS cho màn hình hẹp, trạng thái focus và tùy chọn giảm chuyển động.

## Lỗi được phát hiện và sửa

1. Hàm cập nhật hạn mức truy cập hai ID hiển thị đã thiếu trong HTML, làm quá trình tải chính sách dừng giữa chừng. Đã bổ sung phần hiển thị tương ứng.
2. Các hàm quản lý ứng dụng tham chiếu các trường nhập và bảng chưa có trong dashboard. Đã đưa các phần tử này vào giao diện và kiểm tra luồng thêm, xóa, lưu.
3. Trạng thái thẻ thời gian với hạn mức 0 cần được hiển thị là hết thời gian. Đã bổ sung kiểm thử cho trường hợp này.
4. Nội dung từ khóa tìm kiếm ở trạng thái không có kết quả được đưa qua hàm escape HTML đang có trước khi hiển thị.

## Quyết định thiết kế và hành vi

- Chọn phong cách sáng tông kem và xanh ngọc cho cả hai cổng.
- Khung giờ chỉnh theo đơn vị 1 tiếng phù hợp dữ liệu lịch 168 ô hiện có.
- Khi chọn thứ 2 từ 22:00 đến 06:00, thời gian nghỉ kéo dài đến 06:00 sáng thứ 3. Các ngày khác áp dụng tương tự.
- Nút Lưu lịch và Lưu chính sách cùng lưu hạn mức, lịch và danh sách ứng dụng trong một yêu cầu cập nhật chính sách.
- Các trình điều khiển chỉ được mở để chỉnh sau khi tải được chính sách ban đầu.

## Kết quả kiểm thử

| Hạng mục | Kết quả | Phạm vi xác minh |
| --- | --- | --- |
| Bộ kiểm thử giao diện mới | 32/32 đạt | Chạy mã JavaScript sản phẩm trong môi trường giả lập DOM và phản hồi API |
| WebSocket ConnectionManager | 1/1 đạt | Bài kiểm thử Python gốc về quản lý kết nối và ngắt kết nối |
| Kiểm tra mã nguồn độc lập từ suite gốc | 15/15 đạt | Chạy riêng các phương thức chỉ đọc và kiểm tra HTML, CSS, JS, bằng cách tách AST để tránh import các thành phần thiếu thư viện |
| Cú pháp Python | 31 tệp đạt | Server, agent, DNS proxy, tests và script Python ở thư mục gốc |
| Cú pháp JavaScript | 2 tệp và 2 khối inline đạt | app.js, child.js và mã inline có nội dung trong các template |
| Cấu trúc HTML | 3 template đạt | Đóng thẻ, ID trùng, ID được JavaScript tham chiếu, liên kết điều hướng, label và đường dẫn tài nguyên |
| Bộ pytest đầy đủ | Dừng với 5 lỗi nạp module | Thiếu sqlalchemy và winreg |
| Giao diện mới trên trình duyệt | Chưa xác minh trực quan | Chính sách trình duyệt chặn mở bản xem trước qua file://, môi trường thực thi từ chối mở máy chủ HTTP cục bộ |
| API với cơ sở dữ liệu thực | Chưa chạy được | Môi trường thiếu thư viện backend |
| Agent Windows, chặn tiến trình, DNS proxy và chia sẻ màn hình thực | Cần kiểm thử trên Windows | Phụ thuộc hệ điều hành và thiết bị thực |

Bộ 32 kiểm thử mới bao gồm chỉnh lịch ban ngày, nhiều ngày, qua nửa đêm, vòng tuần, cả ngày, đầu vào không hợp lệ, các mẫu lịch, dữ liệu 336 ô, ứng dụng bị chặn dạng cũ, lưu lỗi, thử lại, bấm lưu đồng thời, sửa trong lúc đang lưu, hạn mức 0, duyệt và từ chối yêu cầu, bộ lọc tiếng Việt, trạng thái khóa và màu hiển thị thời gian.

Hai bài kiểm tra mã nguồn cũ được cập nhật chuỗi placeholder và bổ sung kiểm tra aria-label để khớp giao diện tìm kiếm mới.

### Lệnh đã chạy

```sh
node --test tests/ui_behavior.test.cjs
python3 -m pytest tests/test_websocket.py -q
python3 -m pytest tests/ -q
```

Lệnh cuối báo lỗi nạp ở các module sau.

```text
tests/test_blocker.py              ModuleNotFoundError: winreg
tests/test_child_web_lock.py       ModuleNotFoundError: sqlalchemy
tests/test_policy_api.py           ModuleNotFoundError: sqlalchemy
tests/test_safe_lock_and_web.py    ModuleNotFoundError: winreg
tests/test_safety_and_ui.py        ModuleNotFoundError: sqlalchemy
```

Đã thử cài các thư viện còn thiếu vào thư mục tạm nhưng nguồn gói trong môi trường hiện tại không cung cấp được gói. Môi trường cũng thiếu Jinja2 và đang có Pydantic 1, trong khi requirements yêu cầu Pydantic 2.

## Các tệp thay đổi

- server/templates/dashboard.html
- server/templates/index.html
- server/templates/child_portal.html
- server/static/css/ui.css
- server/static/js/child.js
- tests/ui_behavior.test.cjs
- tests/test_safe_lock_and_web.py
- tests/test_safety_and_ui.py
- docs/UI_UPGRADE_REPORT.md

## Xác minh còn cần thực hiện

Cần một lượt chạy trên Windows với đầy đủ thư viện để kết luận kiểm thử toàn dự án. Lượt này cần chạy pytest đầy đủ, mở dashboard và cổng trẻ qua HTTP, kiểm tra kích thước desktop và điện thoại, thiết lập hồ sơ, duyệt thêm giờ, tải lại sau khi lưu lịch, khóa và mở khóa, trò chuyện, đồng ý hoặc từ chối chia sẻ màn hình, chặn ứng dụng và DNS bằng agent thực.

Các tệp thực thi Windows cần được đóng gói lại từ mã nguồn đã cập nhật để chứa giao diện mới. Lượt thực hiện này hoàn thành thay đổi mã giao diện và các kiểm tra nêu trong bảng, còn việc xác nhận hoạt động end-to-end cần môi trường chạy phù hợp.
