# CHÍNH SÁCH BẢO VỆ DỮ LIỆU VÀ QUYỀN RIÊNG TƯ
## HỆ THỐNG "NGƯỜI BẠN ĐỒNG HÀNH" (OGK SYSTEM)
> **Căn cứ pháp lý:** Nghị định số 13/2023/NĐ-CP về Bảo vệ dữ liệu cá nhân  
> **Nguyên tắc cốt lõi:** *"Công cụ đồng hành, không phải phần mềm theo dõi lén"*

---

# PHẦN 1: BẢNG MINH BẠCH DỮ LIỆU DÀNH CHO PHỤ HUYNH

Kính gửi Quý Phụ huynh, Hệ thống **Người Bạn Đồng Hành (OGK)** được thiết kế với mục tiêu bảo vệ trẻ em trên không gian mạng và cân bằng thời gian sử dụng thiết bị, đồng thời tôn trọng tối đa quyền riêng tư của trẻ theo đúng tinh thần của Nghị định 13/2023/NĐ-CP.

### 1. Phân loại và Phạm vi Thu thập Dữ liệu

| STT | Trường Dữ liệu Thu thập | Mục đích Sử dụng | Phạm vi & Giới hạn Thu thập | Thời hạn Lưu trữ |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **Thời gian sử dụng màn hình** (`duration_sec`) | Tính toán định mức (Quota) ngày thường và cuối tuần | Đo tổng thời gian máy tính hoạt động và ứng dụng ở Foreground qua `time.monotonic()`. **Không tính khi không thao tác > 5 phút.** | 90 ngày (Tự động xóa) |
| **2** | **Tên tiến trình ứng dụng** (`subject`) | Phân loại học tập / giải trí / chặn ứng dụng cấm | Chỉ lưu tên file nhị phân (ví dụ: `Teams.exe`, `Minecraft.exe`). **Tuyệt đối không đọc nội dung file hay tài liệu.** | 90 ngày |
| **3** | **Tên miền cấp hai** (`subject`) | Lọc website theo độ tuổi và chặn web độc hại | Chỉ lưu domain gốc (ví dụ: `wikipedia.org`, `tiktok.com`). **Tuyệt đối không lưu URL đầy đủ, không lưu lịch sử tìm kiếm chi tiết.** | 90 ngày |
| **4** | **Mã định danh thiết bị** (`device_id`) | Nhận dạng máy con để đồng bộ chính sách | Tạo từ MachineGuid của Windows Registry, không liên kết với thông tin cá nhân ngoài đời thực. | Theo vòng đời tài khoản |
| **5** | **Thời điểm sự kiện** (`ts`) | Thống kê biểu đồ sử dụng trong ngày và trong tuần | Định dạng chuẩn ISO-8601 UTC. | 90 ngày |

### 2. Cam kết "4 KHÔNG" về Quyền riêng tư
1. ❌ **KHÔNG chụp ảnh màn hình (No Screenshots):** Hệ thống không chứa bất kỳ hàm chụp màn hình desktop nào.
2. ❌ **KHÔNG ghi lại phím bấm (No Keylogger):** Hệ thống chỉ sử dụng Windows API `GetLastInputInfo` để kiểm tra có thao tác phím/chuột hay không nhằm dừng đếm giờ khi trẻ rời máy; hoàn toàn không đọc phím nào được bấm.
3. ❌ **KHÔNG theo dõi URL đầy đủ (No Full URL Tracking):** DNS Proxy chỉ phân giải tên miền (Domain Name), hoàn toàn không thể và không đọc đường dẫn chi tiết phía sau (Path, Query Parameter).
4. ❌ **KHÔNG chia sẻ dữ liệu cho bên thứ ba:** Toàn bộ dữ liệu nằm trên Server do gia đình tự quản lý (Self-hosted) hoặc Lab nội bộ, không có tracking hay quảng cáo.

### 3. Cơ chế Lưu trữ & Quyền được quên (Right to be Forgotten)
- **Tự động thanh trừng sau 90 ngày:** Endpoint `DELETE /events/cleanup-old-records` tự động chạy định kỳ xóa các bản ghi cũ hơn 90 ngày.
- **Quyền được quên:** Phụ huynh có thể nhấn nút xóa toàn bộ dữ liệu của trẻ qua API `DELETE /data/purge-child/{child_id}`. Khi nhận lệnh, hệ thống sẽ xóa vĩnh viễn mọi dữ liệu liên quan cả trên Server lẫn máy con.

---

# PHẦN 2: THÔNG ĐIỆP THÂN THIỆN DÀNH CHO BÉ

Chào em, người bạn nhỏ đang sử dụng chiếc máy tính này! 👋

Ứng dụng **"Người Bạn Đồng Hành"** được cài đặt trên máy để cùng em học tập và giải trí một cách vui vẻ, khỏe mạnh nhất. Chúng mình muốn em hiểu rõ ứng dụng hoạt động như thế nào:

### 1. Người Bạn Đồng Hành GIÚP em những gì?
- ⏰ **Nhắc em nghỉ ngơi:** Giúp mắt em không bị mỏi khi nhìn màn hình quá lâu.
- 🛡️ **Bảo vệ em khỏi nguy hiểm:** Tự động chặn các trang web xấu, cờ bạc hoặc trò chơi bạo lực không phù hợp với lứa tuổi của em.
- 🔍 **Tìm kiếm an toàn (SafeSearch):** Khi em tra cứu bài học trên Google hay xem video trên YouTube, ứng dụng giúp lọc sạch những nội dung xấu để em yên tâm khám phá.
- ⏳ **Minh bạch:** Khi sắp hết giờ dùng máy, hệ thống luôn cảnh báo trước 10 phút, 5 phút và 1 phút, đồng thời cho em thêm 60 giây để em kịp lưu lại bài học của mình.

### 2. Người Bạn Đồng Hành KHÔNG làm gì?
- 🚫 **Không chụp ảnh màn hình của em:** Mọi hình ảnh em vẽ, tài liệu em học đều là của riêng em.
- 🚫 **Không đọc tin nhắn hay mật khẩu của em:** Chúng mình không biết em đang gõ chữ gì trên bàn phím.
- 🚫 **Không theo dõi bí mật:** Mọi thứ ứng dụng ghi nhận (như hôm nay em đã dùng máy bao nhiêu phút) đều được hiển thị rõ ràng trên màn hình để em và ba mẹ cùng xem.

Chúc em có những giờ học tập bổ ích và những phút giây giải trí thật vui bên chiếc máy tính! 🌟

