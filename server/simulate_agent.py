import datetime
import requests

SERVER_URL = "http://127.0.0.1:8000"

print("==================================================")
print("1. KIỂM THỬ GHÉP ĐÔI THIẾT BỊ (ENROLLMENT)")
print("==================================================")

# 1. Yêu cầu sinh mã ghép đôi 8 ký tự
code_resp = requests.post(f"{SERVER_URL}/enroll/generate-code", json={"child_id": 1})
if code_resp.status_code != 200:
    print("❌ Lỗi sinh mã:", code_resp.text)
    exit()

code_data = code_resp.json()
enroll_code = code_data["code"]
print(f"✓ Mã ghép đôi sinh ra thành công: {enroll_code}")
print(f"✓ Thời hạn mã: {code_data['expires_at']}")

# 2. Agent gửi mã kèm dấu vân tay thiết bị (Fingerprint) để nhận Token
verify_payload = {
    "code": enroll_code,
    "fingerprint": "DESKTOP-DEMO-WIN11-HWID",
    "device_name": "Laptop Học Tập Bé An"
}
verify_resp = requests.post(f"{SERVER_URL}/enroll/verify", json=verify_payload)
if verify_resp.status_code != 200:
    print("❌ Lỗi xác thực mã:", verify_resp.text)
    exit()

verify_data = verify_resp.json()
device_id = verify_data["device_id"]
access_token = verify_data["access_token"]
print("✓ Ghép đôi thành công!")
print(f"  - Device ID : {device_id}")
print(f"  - Token Type: {verify_data['token_type']}")
print(f"  - Access Token (rút gọn): {access_token[:25]}...")

print("\n==================================================")
print("2. KIỂM THỬ ĐỒNG BỘ CHÍNH SÁCH (POLICY SYNC)")
print("==================================================")

policy_resp = requests.get(f"{SERVER_URL}/policy/1")
print("✓ Lấy chính sách hiện tại của trẻ ID 1:")
print(f"  - Quota ngày thường : {policy_resp.json().get('daily_quota_weekday_min')} phút")
print(f"  - Phiên bản Policy : v{policy_resp.json().get('version')}")

print("\n==================================================")
print("3. KIỂM THỬ GỬI SỰ KIỆN THEO LÔ (EVENTS BATCH - 7 TRƯỜNG)")
print("==================================================")

now = datetime.datetime.utcnow().isoformat()
mock_events = [
    {
        "ts": now,
        "device_id": device_id,
        "child_id": 1,
        "type": "app_stop",
        "subject": "Microsoft Teams",
        "duration_sec": 2400,
        "policy_id": 1
    },
    {
        "ts": now,
        "device_id": device_id,
        "child_id": 1,
        "type": "app_stop",
        "subject": "Minecraft.exe",
        "duration_sec": 1800,
        "policy_id": 1
    },
    {
        "ts": now,
        "device_id": device_id,
        "child_id": 1,
        "type": "blocked_domain",
        "subject": "game-cam-tre-em.com",
        "duration_sec": 0,
        "policy_id": 1
    }
]

batch_resp = requests.post(f"{SERVER_URL}/events/batch", json=mock_events)
if batch_resp.status_code == 200:
    print(f"✓ Gửi lô sự kiện thành công: Đã ghi nhận {batch_resp.json()['recorded_count']} bản ghi vào SQLite WAL.")
else:
    print("❌ Lỗi gửi sự kiện:", batch_resp.text)

print("\n==================================================")
print("4. KIỂM THỬ HEARTBEAT (NHỊP TIM ĐỊNH KỲ)")
print("==================================================")
hb_payload = {
    "device_id": device_id,
    "status": "online",
    "current_policy_version": 1
}
hb_resp = requests.post(f"{SERVER_URL}/heartbeat", json=hb_payload)
if hb_resp.status_code == 200:
    print("✓ Gửi Heartbeat thành công, Server phản hồi:", hb_resp.json())
else:
    print("❌ Lỗi Heartbeat:", hb_resp.text)

print("\n==================================================")
print("5. KIỂM TRA SỐ LIỆU TỔNG QUAN CHO DASHBOARD")
print("==================================================")
stats_resp = requests.get(f"{SERVER_URL}/dashboard-stats/1")
stats = stats_resp.json()
print(f"✓ Tổng số phút hôm nay: {stats['today_minutes']} phút")
print(f"✓ Hạn mức: {stats['quota_minutes']} phút")
print("\n🎉 TOÀN BỘ LUỒNG KIỂM THỬ ĐÃ SẴN SÀNG ĐỂ NHÓM ĐỐI CHIẾU!")