# HƯỚNG DẪN TRIỂN KHAI & KỊCH BẢN DEMO THỰC THI 100% GIAO DIỆN TRỰC QUAN (ZERO-CLI)
## HỆ THỐNG "NGƯỜI BẠN ĐỒNG HÀNH" (OGK SYSTEM - PARENTAL CONTROL)
> **Nền tảng mục tiêu:** Windows 10/11 x64 (Clean Machine) — **TUYỆT ĐỐI KHÔNG CẦN CÀI PYTHON**.

---

## I. TỔNG QUAN BỘ CÀI ĐẶT TRỌN GÓI (`dist_package/`)

Thư mục `dist_package/` (hoặc file nén `dist/OGK_Deploy_Package_x64.zip`) đã tích hợp sẵn tất cả runtime nhị phân độc lập, cơ sở dữ liệu SQLite, và toàn bộ giao diện Web Dashboard:

```text
dist_package/
├── Start_App.bat              # Launcher duy nhất: --server-only, --with-agent, --with-dns, --reset, --stop
│
├── ogk_server.exe             # Máy chủ OGK + Dashboard phụ huynh + Cổng học tập của trẻ
├── agent_service.exe          # Agent (Windows Service; lệnh enroll / debug / uninstall)
├── ogk_tray.exe               # Biểu tượng khay hệ thống bắt buộc trong phiên của trẻ
├── dns_proxy.exe              # DNS Proxy UDP 53: 6 nhóm nội dung, SafeSearch, chặn DoH
│
├── templates/                 # Giao diện Web Dashboard HTML5/Tailwind/Chart.js
│   └── dashboard.html         # Trang quản trị phụ huynh 100% trực quan
│
├── blocklist.json             # Danh mục hơn 200 tên miền web đen & DoH Canary
├── install_service.bat        # Ghép đôi + Windows Service LocalSystem (tự khởi động lại 5s) + khay hệ thống
├── uninstall_service.bat      # Gỡ cài đặt (bắt buộc tài khoản phụ huynh, có audit log)
├── SHA256SUMS.txt             # Bảng mã băm xác thực tính toàn vẹn phần mềm
└── HUONG_DAN_CAI_DAT.txt      # Tóm tắt các bước chạy nhanh dưới 5 phút
```

---

## II. HƯỚNG DẪN KHỞI CHẠY TRỰC TIẾP TRÊN MÁY SẠCH (ZERO-CLI)

### 👉 Cách 1: Khởi chạy Trọn gói 1-Click (Khuyên dùng khi Demo)
1. Giải nén file `OGK_Deploy_Package_x64.zip` hoặc copy thư mục `dist_package` vào máy tính (Ví dụ: `C:\OGK_System`).
2. Nhấp đúp chuột vào file **`Start_App.bat`**.
3. **Điều gì sẽ tự động diễn ra mà không cần gõ bất kỳ lệnh nào?**
   - File `ogk_server.exe` tự khởi động ngầm.
   - Trình duyệt web mặc định (Chrome, Edge) **tự động mở thẳng** địa chỉ:
     👉 **`http://127.0.0.1:8000`**
   - Lần đầu, Dashboard yêu cầu tạo tài khoản phụ huynh (mật khẩu ≥ 10 ký tự) và hồ sơ trẻ.
   - Để chạy kèm Agent debug: `Start_App.bat --with-agent` (máy cần ghép đôi trước bằng
     `agent_service.exe enroll <MÃ>` với mã tạo ở mục "Thiết bị của trẻ").

---

### 👉 Cách 2: Chạy Từng File .EXE Riêng Lẻ Thủ Công
Nếu muốn kiểm tra từng file thực thi độc lập:
1. **Chạy Server:**
   - Nhấp đúp vào **`ogk_server.exe`**.
   - Mở trình duyệt bất kỳ gõ: `http://127.0.0.1:8000`.
2. **Chạy Agent giám sát máy con:**
   - Nhấp đúp vào **`agent_service.exe`** (hoặc chạy qua `install_service.bat` bằng chuột phải chọn *Run as administrator* để đăng ký thành Windows Service).
3. **Chạy DNS Proxy lọc mạng:**
   - Mở Command Prompt bằng **"Run as administrator"** và chạy `Start_App.bat --with-dns` (cổng UDP 53 cần quyền Admin).

---

## III. KỊCH BẢN DEMO CHI TIẾT TỪNG BƯỚC CHO GIẢNG VIÊN / HỘI ĐỒNG (5 PHÚT)

Kịch bản dưới đây được thiết kế để gây ấn tượng mạnh với Hội đồng đánh giá, chứng minh tính minh bạch, sự chuyên nghiệp và đáp ứng trọn vẹn yêu cầu **Zero-CLI**:

### 🎯 BƯỚC 1: Trình diễn Khóa / Mở Khóa Cửa Sổ Trẻ Em (< 1 Giây - Không ảnh hưởng Windows)
1. Trên trình duyệt tại `http://127.0.0.1:8000`, chỉ vào góc phải:
   - Điểm báo WebSocket hiển thị màu xanh lá: **"Trực tuyến (Realtime WebSocket)"**.
2. Bấm vào nút màu đỏ nổi bật: **"🔒 Khóa cửa sổ trẻ (< 1s)"**.
3. **Kết quả quan sát trực tiếp trên màn hình:**
   - Cửa sổ ứng dụng của trẻ (`child_client.exe`) lập tức phóng to toàn màn hình (Fullscreen Overlay), chế độ luôn nổi (`TopMost`), phong tỏa toàn bộ tương tác chuột/bàn phím vào nội dung bên dưới.
   - Hiển thị màn hình khóa thân thiện: *"Đã hết giờ dùng máy hoặc ba mẹ tạm khóa cửa sổ. Hãy nghỉ ngơi một chút nhé!"*.
   - **Đặc biệt:** Hệ điều hành Windows của bạn **hoàn toàn bình thường**, không bị văng ra màn hình khóa Windows (`LockWorkStation`).
4. **Mở khóa linh hoạt:**
   - Người lớn có thể nhập trực tiếp mã PIN bảo mật đã thiết lập trên màn hình của trẻ, HOẶC:
   - Trên Web Dashboard, bấm **"🔓 Mở khóa cửa sổ"**: Cửa sổ của trẻ lập tức tự động thu nhỏ trở về khung di động bình thường!

---

### 🎯 BƯỚC 2: Trình diễn Giảm Bớt Thời Gian (Trừ giờ tức thì qua WebSocket)
1. Trên Web Dashboard tại thẻ **"Thời gian dùng hôm nay"**, quan sát cụm nút **⚡ Giảm bớt thời gian**:
   - Bấm nút **"-15 phút"** hoặc **"-30 phút"** (hoặc nhập số phút tùy chỉnh rồi bấm "Trừ").
2. **Hiệu ứng thời gian thực ngay lập tức:**
   - API `POST /policy/deduct-time` được gọi và cập nhật cơ sở dữ liệu SQLite.
   - Tín hiệu WebSocket `time_deducted` bắn xuống máy con trong 0.2 giây.
   - Trên Cửa sổ của trẻ, một thông báo Toast nổi màu cam xuất hiện:
     > *"⚠️ Ba mẹ đã điều chỉnh giảm 15 phút thời gian giải trí!"*
   - Thanh hạn mức trên đồng hồ Status Bar của trẻ lập tức nhảy lùi số phút.
   - Nếu số phút còn lại sau khi trừ $\le 0$, hệ thống tự động kích hoạt màn hình khóa In-App Lock!

---

### 🎯 BƯỚC 2: Trình diễn Chặn Ứng dụng Bằng File Picker Tự Tính SHA-256 (Không cần gõ mã băm)
1. Cuộn chuột xuống mục **"🚫 Quản lý Ứng dụng Bị chặn"**.
2. Nhấn vào nút: **"📁 Chọn file ứng dụng (.exe)..."**.
3. Chọn một file thực thi bất kỳ trên máy (Ví dụ: `Notepad.exe`, `Calculator.exe` hoặc file game).
4. **Quan sát sự kỳ diệu:**
   - Trình duyệt tự động dùng thuật toán Web Crypto đọc file và tính mã băm SHA-256 64 ký tự hex ngay lập tức trong 0.05 giây!
   - Ô "Tên gợi nhớ" và "Mã băm SHA-256" tự động được điền đầy đủ.
5. Nhấn nút **"+ Thêm chặn"** -> Ứng dụng xuất hiện ngay trong bảng danh sách cấm.
6. Nhấn nút **"💾 Áp dụng tất cả chính sách"**:
   - Hệ thống thông báo thành công và tăng version chính sách (ví dụ v2 -> v3).
   - Tín hiệu `sync_policy` được bắn tức thì qua WebSocket đến Agent.
7. **Thử nghiệm trên máy con:**
   - Mở ứng dụng vừa bị chặn lên (kể cả khi đổi tên file từ `Notepad.exe` thành `BaiHoc.exe`):
   - Trong vòng 1 giây, tiến trình bị tắt lập tức (`terminate`), và hộp thoại popup Windows hiện lên minh bạch thông báo:
     > *"Ứng dụng đã bị chặn do nằm trong danh sách hạn chế của cha mẹ."*

---

### 🎯 BƯỚC 3: Trình diễn Kéo chuột chỉnh Ma trận Lịch tuần 7x48 (Schedule Matrix)
1. Cuộn đến mục **"📅 Ma trận Lịch Tuần Cho phép / Khóa máy"**.
2. Giới thiệu bảng ma trận: 7 hàng (Thứ 2 đến Chủ Nhật) x 48 cột (mỗi ô là 30 phút, tổng cộng đúng 336 slot).
3. **Thao tác trực quan:**
   - Nhấn nút tiện ích nhanh: **"Khóa ban đêm (22h - 6h)"** -> toàn bộ các ô từ 22:00 đêm đến 06:00 sáng lập tức chuyển sang màu đỏ.
   - Nhấn nút tiện ích: **"Khóa giờ học (8h-11h30 & 14h-17h)"** -> các khung giờ học chuyển đỏ.
   - Dùng chuột **kéo thả (Drag & Drop)** tự do trên bất kỳ ô nào để bật xanh / tắt đỏ.
4. Bấm **"Áp dụng tất cả chính sách"** để lưu ma trận 336 ký tự vào SQLite.

---

### 🎯 BƯỚC 4: Trình diễn Cửa sổ Trẻ Em (Mobile App Library & Tìm kiếm Thông minh)
1. Khi chạy `Start_App.bat`, cửa sổ ứng dụng của trẻ sẽ tự động mở với thiết kế phong cách **Mobile Grid / Glassmorphism** hiện đại:
   - **Thanh trạng thái (Status Bar):** Đồng hồ kỹ thuật số trực tiếp, thời lượng còn lại hôm nay (`⏳ Còn lại: 105p / 120p`), biểu tượng Pin `100% 🔋` và Sóng `📶 5G`.
   - **Thư viện ứng dụng theo danh mục (App Folders):** 5 nhóm kính mờ: *Học tập (Chrome, Edge, Duolingo...)*, *Sáng tạo (Scratch, Python, Word...)*, *Mạng xã hội*, *Giải trí*, *Trò chơi*. Nhấp vào thư mục để mở rộng danh sách app bên trong.
   - **Thanh tìm kiếm thông minh (Smart App Search):**
     - Đặt phía trên Dock: Thử gõ `Chrome` hoặc `Word` -> Hiển thị badge xanh **"✓ Cho phép mở"** và có thể bấm để khởi chạy ứng dụng trực tiếp!
     - Thử gõ `Roblox` (hoặc app trong danh sách cấm) -> Hiển thị badge đỏ **"✕ Đang bị hạn chế"**, làm mờ icon và giải thích lý do minh bạch khi bấm vào.
   - **Thanh Dock nổi (Floating Dock):** 3 tiện ích thiết yếu luôn sẵn sàng: Trình duyệt an toàn (Safe Browser), Ghi chú bài học (Notes), Xin thêm giờ (Hotline).
2. Trẻ nhấn nút nổi bật: **"✨ Xin thêm giờ"**:
   - Popup mở lên cho phép chọn: `+15 phút`, `+30 phút`, `+45 phút` và nhập lý do.
   - Bấm **"Gửi yêu cầu"**: Yêu cầu lập tức được chuyển lên Server qua `POST /requests/`.
3. Phụ huynh trên Web Dashboard (`http://127.0.0.1:8000`) thấy yêu cầu xuất hiện ngay tức thì trong **"Trung tâm Phê duyệt (Approval Center)"** -> Bấm **"Duyệt +15p"**.
4. Cửa sổ Client của trẻ lập tức nhận thông báo chúc mừng, thời gian trên thanh Status Bar tự động cộng thêm 15 phút!

---

### 🎯 BƯỚC 5: Trình diễn Cơ chế Đồng thuận Giám sát (Consent Dialog - Tuyệt đối không chụp lén)
1. Trên Web Dashboard của Phụ huynh, bấm nút: **"👁️ Xem màn hình"**.
2. **Hệ thống minh bạch hoạt động:**
   - Agent **tuyệt đối không âm thầm chụp trộm**.
   - Trên màn hình của trẻ, một hộp thoại ưu tiên toàn màn hình bật lên với đồng hồ đếm ngược 30 giây:
     > *"Ba mẹ đang yêu cầu xem hoạt động màn hình của bạn. Để đảm bảo tính minh bạch, bạn có đồng ý chia sẻ màn hình hiện tại không?"*
   - Kèm 2 lựa chọn: **"Đồng ý chia sẻ"** hoặc **"Từ chối"**.
3. Nếu trẻ bấm **"Đồng ý chia sẻ"**: Web Dashboard nhận phản hồi đồng ý qua WebSocket.
4. Nếu trẻ bấm **"Từ chối"** hoặc sau 30 giây không phản hồi: Dashboard nhận thông báo từ chối minh bạch.

---

### 🎯 BƯỚC 6: Trình diễn Đóng phiên làm việc an toàn (Không làm sập nguồn máy tính)
1. Trên Web Dashboard của Phụ huynh, bấm nút: **"🚪 Đóng phiên làm việc"**.
2. Hộp thoại xác nhận hiện ra -> Bấm **OK**.
3. **Phản ứng trên máy con:**
   - Cửa sổ làm việc của trẻ tự động thu nhỏ và đóng phiên làm việc an toàn.
   - **Tuyệt đối không làm sập nguồn máy tính hay tắt hệ điều hành Windows!**

---

### 🎯 BƯỚC 7: Tắt toàn bộ hệ thống khi kết thúc
Chạy **`Start_App.bat --stop`**: máy chủ, Agent debug và DNS Proxy đều được dừng.

---

## IV. BẢNG TỔNG HỢP KIỂM CHỨNG TÍNH NĂNG (CHECKLIST NGHIỆM THU)

| STT | Tính năng yêu cầu | Trạng thái | Minh chứng trực quan |
| :---: | :--- | :---: | :--- |
| **1** | Chạy độc lập không cần Python | ✅ HOÀN TẤT | Chạy trực tiếp từ các file `.exe` / `Start_App.bat` |
| **2** | 100% Zero-CLI cho Phụ huynh & Học sinh | ✅ HOÀN TẤT | Thao tác chọn file, thanh trượt, kéo chuột, UI thân thiện |
| **3** | Cửa sổ Trẻ Em Mobile Launcher (App Library) | ✅ HOÀN TẤT | Khung di động, Glassmorphism, Status Bar, App Folders |
| **4** | Thanh tìm kiếm app thông minh | ✅ HOÀN TẤT | Tự động so khớp Policy: hiện badge "✓ Cho phép" hoặc "✕ Hạn chế" |
| **5** | Khóa cô lập cửa sổ (In-App Lock Overlay) | ✅ HOÀN TẤT | In-Page Topmost Overlay, mở khóa bằng mã PIN phụ huynh hoặc Web Dashboard |
| **6** | Giảm bớt thời gian (Trừ giờ thời gian thực) | ✅ HOÀN TẤT | Nút -15p, -30p trên Dashboard, WebSocket toast thông báo tức thì |
| **7** | Xin thêm giờ & Phê duyệt AJAX | ✅ HOÀN TẤT | Modal xin giờ trên Child UI -> Phụ huynh duyệt -> Cộng giờ tức thì |
| **8** | Cơ chế Đồng thuận Giám sát (Consent) | ✅ HOÀN TẤT | Không chụp lén; Popup 30s hỏi ý kiến trẻ trước khi xem màn hình |
| **9** | Đóng phiên làm việc an toàn | ✅ HOÀN TẤT | Không gọi `shutdown /s`, bảo vệ toàn vẹn hệ điều hành Windows |
| **10** | Tự động tính SHA-256 từ file .exe | ✅ HOÀN TẤT | Chọn file là tự tính hash bằng Web Crypto trong < 100ms |
| **11** | Chặn app vi phạm dù đổi tên | ✅ HOÀN TẤT | Nhận diện mã băm nhị phân thực tế, terminate < 1.5s |
| **12** | Đóng gói Trọn gói 1-Click | ✅ HOÀN TẤT | `Start_App.bat` và `dist/OGK_Deploy_Package_x64.zip` |

