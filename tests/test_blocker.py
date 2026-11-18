import os
import sys
import time
import shutil
import hashlib
import subprocess
import pytest
from pathlib import Path

# Thêm agent vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "agent"))

from blocker import ProcessBlocker
from local_cache import local_cache


def test_process_blocker_by_sha256(tmp_path):
    """
    Ca kiểm thử Chuyên đề:
    1. Tạo file thực thi giả lập từ python.exe, tính SHA-256.
    2. Đổi tên file giả lập thành 'totally_different_game.exe' (chứng minh TUYỆT ĐỐI không dựa vào tên file).
    3. Nạp SHA-256 vào chính sách cấm trong cache SQLite.
    4. Khởi chạy tiến trình giả lập.
    5. Kích hoạt ProcessBlocker.check_and_enforce().
    6. Xác minh tiến trình bị tiêu diệt trong < 2 giây và ghi nhận sự kiện vi phạm vào SQLite.
    """
    blocker = ProcessBlocker()

    # 1. Tạo file thực thi giả lập bằng cách sao chép python.exe
    src_python = sys.executable
    dummy_exe = tmp_path / "totally_different_game.exe"
    shutil.copy2(src_python, dummy_exe)
    assert dummy_exe.exists(), "Không thể tạo file thực thi giả lập"

    # 2. Tính SHA-256 của file thực thi giả lập
    sha256 = hashlib.sha256(dummy_exe.read_bytes()).hexdigest().lower()
    assert len(sha256) == 64

    # 3. Nạp mã SHA-256 này vào chính sách cấm trong SQLite cache
    policy = {
        "child_id": 1,
        "version": 99,
        "daily_quota_weekday_min": 120,
        "daily_quota_weekend_min": 180,
        "schedule_matrix": "1" * 336,
        "blocked_apps": sha256,
        "blocked_domains": ""
    }
    local_cache.save_policy(policy)

    # 4. Khởi chạy tiến trình giả lập với tên đã bị đổi
    proc = subprocess.Popen(
        [str(dummy_exe), "-c", "import time; time.sleep(30)"],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    assert proc.poll() is None, "Tiến trình giả lập phải đang chạy"
    time.sleep(0.3)  # Đảm bảo tiến trình đã nạp hoàn chỉnh trên Windows PE Loader

    try:
        start_t = time.time()
        # 5. Kích hoạt bộ kiểm tra và cưỡng chế
        blocker.check_and_enforce()

        # Chờ tối đa 2.0 giây để xác minh tiến trình đã bị terminate
        try:
            proc.wait(timeout=2.0)
            elapsed = time.time() - start_t
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("ProcessBlocker không thể chấm dứt tiến trình con trong vòng 2.0 giây!")

        assert proc.poll() is not None, "Tiến trình vi phạm phải bị dừng hoàn toàn"
        assert elapsed < 2.5, f"Thời gian dừng tiến trình ({elapsed:.2f}s) vượt quá tiêu chuẩn"

        # 6. Xác minh bản ghi sự kiện vi phạm đã được lưu vào SQLite queue
        events = local_cache.peek_events(limit=20)
        violation_events = [e for e in events if e.get("type") == "blocked_app"]
        assert len(violation_events) > 0, "Phải có ít nhất 1 sự kiện blocked_app được lưu vào SQLite cache"
        
        last_ev = violation_events[-1]
        assert "totally_different_game.exe" in last_ev.get("subject", "").lower()
        print(f"\n[TEST_PASS] Tiến trình vi phạm {dummy_exe.name} ({sha256[:16]}...) đã bị dừng sau {elapsed:.2f}s!")

    finally:
        # Dọn dẹp tiến trình nếu còn tồn tại
        if proc.poll() is None:
            proc.kill()

