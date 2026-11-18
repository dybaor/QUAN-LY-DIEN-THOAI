# OGK DNS PROXY - TRÌNH PHÂN GIẢI & LỌC TÊN MIỀN MẠNG

Module DNS Server cục bộ lắng nghe trên cổng UDP 53, phụ trách kiểm soát lưu lượng truy cập Internet ở tầng mạng, ngăn chặn các trang web độc hại và cưỡng chế tính năng tìm kiếm an toàn (SafeSearch).

---

## 1. CÁC TÍNH NĂNG CHÍNH

- **Lọc Tên Miền Theo Danh Sách Cấm (`blocklist.json`):**
  - Chứa danh sách các tên miền độc hại, bạo lực, cờ bạc, nội dung không lành mạnh.
  - Tự động chặn bằng cách phản hồi bản ghi DNS trỏ về `127.0.0.1` hoặc trả về `NXDOMAIN`.
- **Cưỡng Chế Tìm Kiếm An Toàn (Enforce SafeSearch - `safesearch.py`):**
  - Tự động điều hướng các yêu cầu tìm kiếm Google (`google.com`, `google.com.vn`) sang `forcesafesearch.google.com` (IP: `216.239.38.120`).
  - Điều hướng YouTube (`youtube.com`) sang `restrict.youtube.com` (IP: `216.239.38.119`).
- **Chặn Vượt Rào DNS over HTTPS (DoH Bypass Prevention):**
  - Chặn tên miền DoH Canary (`use-application-dns.net`) của trình duyệt Firefox/Chrome để ngăn trình duyệt tự động kích hoạt DNS over HTTPS né tránh proxy cục bộ.
- **Tối Ưu Hiệu Năng & Độ Trễ:**
  - Forward các tên miền hợp lệ tới DNS công cộng (Cloudflare `1.1.1.1` hoặc Google `8.8.8.8`).
  - Script đo kiểm độ trễ `benchmark_m4.py` kiểm chứng 30 mẫu p50/p95 đạt chuẩn đồ án.

---

## 2. HƯỚNG DẪN KHỞI CHẠY VÀ KIỂM TRA

### Khởi Chạy DNS Proxy
Do cổng mạng UDP 53 là cổng đặc quyền của hệ thống, bạn **bắt buộc phải mở Terminal với quyền Administrator**:
```powershell
cd dns_proxy
python proxy_server.py
```
Khi chạy thành công, console sẽ hiển thị:
```text
[DNS Proxy] Dang lang nghe tren 127.0.0.1:53...
[DNS Proxy] Da nap 200+ ten mien cam tu blocklist.json
```

### Kiểm Tra Hoạt Động Bằng `nslookup`
Mở một cửa sổ dòng lệnh khác để kiểm tra:
```powershell
# 1. Kiểm tra phân giải tên miền hợp lệ (Phải trả về IP thật)
nslookup dantri.com.vn 127.0.0.1

# 2. Kiểm tra SafeSearch (Phải trả về IP 216.239.38.120)
nslookup www.google.com 127.0.0.1

# 3. Kiểm tra tên miền cấm (Phải trả về 127.0.0.1 hoặc bị chặn)
nslookup bet365.com 127.0.0.1
```

### Chạy Benchmark Hiệu Năng M4
```powershell
python dns_proxy/benchmark_m4.py
```

