"""
OGK-Agent Process & Policy Blocker Module (Thành viên A - Chặn tiến trình bằng SHA-256)
- Nhận diện ứng dụng vi phạm bằng mã băm SHA-256 của file thực thi (.exe), TUYỆT ĐỐI không dựa vào tên file.
- Chấm dứt tiến trình an toàn bằng `psutil.Process(pid).terminate()`.
- Cưỡng chế Daily Quota và Lịch tuần (Schedule Matrix 7x48).
- Khóa phiên làm việc trong cửa sổ trẻ (In-App Overlay Locking, không ảnh hưởng Windows).
- Thông báo sự kiện 100% bằng Web UI Toast Notifications, tuyệt đối không gọi popup hệ điều hành.
"""

import ctypes
import datetime
import hashlib
import json
import os
import threading
import time
from typing import Dict, Optional, Set, Tuple
import psutil
from local_cache import local_cache


class ProcessBlocker:
    """Module kiểm soát và cưỡng chế ứng dụng theo mã băm SHA-256."""

    def __init__(self):
        self._hash_cache: Dict[Tuple[str, float, int], str] = {}
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._wts = ctypes.windll.wtsapi32

    def calculate_file_sha256(self, filepath: str) -> Optional[str]:
        """Tính SHA-256 của file thực thi có cache theo (filepath, mtime, size).
        Hỗ trợ giải quyết App Execution Aliases và thiếu drive letter trên Windows."""
        if not filepath:
            return None
        try:
            # Giải quyết trường hợp psutil trả về đường dẫn thiếu ký tự ổ đĩa (ví dụ: \Users\...)
            if filepath.startswith("\\") and not filepath.startswith("\\\\"):
                sys_drive = os.environ.get("SystemDrive", "C:")
                if not os.path.exists(filepath) and os.path.exists(sys_drive + filepath):
                    filepath = sys_drive + filepath

            # Giải quyết symlink / App Execution Aliases
            resolved = os.path.realpath(filepath)
            if not os.path.isfile(resolved):
                return None
            stat = os.stat(resolved)
            cache_key = (resolved.lower(), stat.st_mtime, stat.st_size)
            if cache_key in self._hash_cache:
                return self._hash_cache[cache_key]

            sha256 = hashlib.sha256()
            with open(resolved, "rb") as f:
                while chunk := f.read(65536):
                    sha256.update(chunk)
            digest = sha256.hexdigest().lower()
            self._hash_cache[cache_key] = digest
            return digest
        except Exception:
            return None

    def show_user_popup(self, title: str, message: str) -> None:
        """Ghi nhận thông báo sự kiện (TUYỆT ĐỐI KHÔNG gọi popup hệ điều hành để không làm gián đoạn trải nghiệm).
        100% thông báo sự kiện được chuyển sang Web UI Toast Notifications."""
        print(f"[AGENT_EVENT_TOAST] {title}: {message}")

    def _dispatch_violation(self, proc_name: str, policy_id: int):
        """Ghi nhận sự kiện vi phạm và đưa vào hàng đợi đồng bộ Web trên thread riêng."""
        def _bg():
            try:
                self.show_user_popup(
                    "OGK-Agent: Ứng dụng đã bị dừng",
                    f"Ứng dụng '{proc_name}' bị chặn do nằm trong danh sách hạn chế của cha mẹ."
                )
                local_cache.enqueue_event(
                    event_type="blocked_app",
                    subject=proc_name,
                    duration_sec=0,
                    policy_id=policy_id,
                )
            except Exception:
                pass
        threading.Thread(target=_bg, daemon=True).start()

    def lock_workstation(self, reason: str = "Hết hạn mức hoặc có lệnh từ phụ huynh") -> bool:
        """Ghi nhận sự kiện khóa cửa sổ (TUYỆT ĐỐI không gọi LockWorkStation để tránh ảnh hưởng cả Windows)."""
        print(f"[LOCK_ACTION] Ghi nhận khóa phiên làm việc! Lý do: {reason}")
        try:
            def _log_lock():
                try:
                    local_cache.enqueue_event(
                        event_type="locked",
                        subject=reason,
                        duration_sec=0,
                    )
                except Exception:
                    pass
            threading.Thread(target=_log_lock, daemon=True).start()
            return True
        except Exception:
            return False

    def remote_shutdown(self, timeout_sec: int = 10, reason: str = "Lệnh từ phụ huynh"):
        """Đóng phiên làm việc an toàn (TUYỆT ĐỐI không gọi shutdown /s để tránh làm sập nguồn Windows)."""
        print(f"[SHUTDOWN_ACTION] Đóng phiên làm việc! Lý do: {reason}")
        self.show_user_popup(
            "KẾT THÚC PHIÊN LÀM VIỆC",
            f"Phiên làm việc của bạn đã được ba mẹ đóng lại ({reason}). Hãy nghỉ ngơi nhé!"
        )

    def cancel_shutdown(self):
        """Hủy lệnh tắt máy nếu phụ huynh hủy."""
        try:
            os.system("shutdown /a")
            self.show_user_popup("THÔNG BÁO", "Lệnh tắt máy từ xa đã được ba mẹ hủy bỏ.")
        except Exception:
            pass

    def is_within_allowed_schedule(self, schedule_matrix: str) -> bool:
        """Kiểm tra ma trận lịch tuần 7x24 (168 ký tự) hoặc 7x48 (336 ký tự)."""
        if not schedule_matrix:
            return True
        now = datetime.datetime.now()
        if len(schedule_matrix) == 168:
            # Chuẩn mới: 7 ngày x 24 giờ
            index = now.weekday() * 24 + now.hour
            if 0 <= index < 168:
                return schedule_matrix[index] == "1"
        elif len(schedule_matrix) == 336:
            # Chuẩn cũ: 7 ngày x 48 slot (30 phút)
            index = now.weekday() * 48 + (now.hour * 2 + now.minute // 30)
            if 0 <= index < 336:
                return schedule_matrix[index] == "1"
        return True

    def check_and_enforce(self) -> None:
        """Chu kỳ quét và cưỡng chế chính sách."""
        policy = local_cache.get_policy()
        
        # 1. Nạp và trích xuất danh sách cấm theo SHA-256 (hỗ trợ cả JSON mảng và text)
        blocked_hashes: Set[str] = set()
        blocked_raw = (policy.get("blocked_apps", "") or "") if policy else ""
        if blocked_raw:
            try:
                parsed = json.loads(blocked_raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "hash" in item:
                            h = str(item["hash"]).strip().lower()
                            if len(h) == 64:
                                blocked_hashes.add(h)
                        elif isinstance(item, str):
                            h = item.strip().lower()
                            if len(h) == 64:
                                blocked_hashes.add(h)
            except Exception:
                for line in blocked_raw.replace(",", "\n").splitlines():
                    h = line.strip().lower()
                    if len(h) == 64:
                        blocked_hashes.add(h)

        # Hash mẫu Notepad để kiểm thử mặc định
        blocked_hashes.add("468ffe129c395abf6b21a09efdf261910a95fb98aa982ead73caa7b2b684577e")

        # Quét các tiến trình đang chạy
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pid = proc.info["pid"]
                name = proc.info["name"]
                if pid <= 4 or not name:
                    continue

                # Tuyệt đối không tự tiêu diệt tiến trình của chính mình hoặc tiến trình cha
                if pid in (os.getpid(), getattr(os, "getppid", lambda: -1)()):
                    continue

                # Bỏ qua các daemon hệ điều hành Windows để tối ưu tốc độ quét (< 50ms)
                if name.lower() in ("svchost.exe", "services.exe", "lsass.exe", "csrss.exe", "wininit.exe", "smss.exe", "fontdrvhost.exe", "dwm.exe", "sihost.exe", "taskhostw.exe", "conhost.exe"):
                    continue

                try:
                    exe_path = proc.exe()
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue
                except Exception:
                    continue

                if not exe_path:
                    continue

                f_hash = self.calculate_file_sha256(exe_path)
                if f_hash and f_hash in blocked_hashes:
                    print(f"[BLOCKED] Dừng ứng dụng vi phạm SHA-256: {name} ({f_hash})")
                    try:
                        proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                    self._dispatch_violation(name, policy.get("id", 1) if policy else 1)
            except Exception:
                continue

        if not policy:
            return

        now = datetime.datetime.now()
        is_weekend = now.weekday() in (5, 6)

        # 2. Kiểm tra Lịch tuần
        schedule_matrix = policy.get("schedule_matrix", "")
        if not self.is_within_allowed_schedule(schedule_matrix):
            self.lock_workstation("Ngoài khung giờ cho phép theo lịch tuần")
            return

        # 3. Kiểm tra Daily Quota
        today_usage = local_cache.get_today_usage_seconds()
        quota_min = policy.get("daily_quota_weekend_min", 180) if is_weekend else policy.get("daily_quota_weekday_min", 120)
        if policy.get("adjustment_date") == now.date().isoformat():
            quota_min = max(0, quota_min + (policy.get("adjustment_minutes") or 0))
        if today_usage >= quota_min * 60:
            self.lock_workstation(f"Đã sử dụng hết hạn mức {quota_min} phút của ngày hôm nay")
            return


blocker = ProcessBlocker()
