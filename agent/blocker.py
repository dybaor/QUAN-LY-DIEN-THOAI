"""
OGK-Agent Process Blocker (F2-1, F2-2)
- Nhận diện ứng dụng bị cấm bằng SHA-256 của file thực thi (đổi tên file không qua mặt được).
- Kết thúc tiến trình và ghi sự kiện `blocked_app`; máy chủ chuyển sự kiện này thành thông báo trong Cổng học tập.
- Không khóa Windows, không mở hộp thoại: việc khóa chỉ là overlay web, Agent chỉ ghi sự kiện `locked`.
"""

import hashlib
import json
import os
import threading
from typing import Dict, Optional, Set, Tuple

import psutil

from local_cache import local_cache

SYSTEM_PROCESSES = {
    "svchost.exe", "services.exe", "lsass.exe", "csrss.exe", "wininit.exe", "smss.exe", "fontdrvhost.exe",
    "dwm.exe", "sihost.exe", "taskhostw.exe", "conhost.exe", "winlogon.exe", "explorer.exe",
}


class ProcessBlocker:
    def __init__(self):
        self._hash_cache: Dict[Tuple[str, float, int], str] = {}

    def calculate_file_sha256(self, filepath: str) -> Optional[str]:
        """SHA-256 của file thực thi, cache theo (đường dẫn, mtime, kích thước)."""
        if not filepath:
            return None
        try:
            if filepath.startswith("\\") and not filepath.startswith("\\\\"):
                drive = os.environ.get("SystemDrive", "C:")
                if not os.path.exists(filepath) and os.path.exists(drive + filepath):
                    filepath = drive + filepath
            resolved = os.path.realpath(filepath)
            if not os.path.isfile(resolved):
                return None
            stat = os.stat(resolved)
            key = (resolved.lower(), stat.st_mtime, stat.st_size)
            if key not in self._hash_cache:
                digest = hashlib.sha256()
                with open(resolved, "rb") as handle:
                    while chunk := handle.read(65536):
                        digest.update(chunk)
                self._hash_cache[key] = digest.hexdigest().lower()
            return self._hash_cache[key]
        except OSError:
            return None

    def _dispatch_violation(self, proc_name: str, policy_id: Optional[int]):
        """Ghi sự kiện `blocked_app`; máy chủ chuyển thành thông báo trong Cổng học tập (không có popup hệ điều hành)."""
        def _report():
            local_cache.enqueue_event("blocked_app", proc_name, 0, policy_id)
        threading.Thread(target=_report, daemon=True).start()

    def enforce_lock(self, reason: str = "Hết hạn mức hoặc có lệnh từ phụ huynh", record: bool = True) -> bool:
        """Ghi nhận trạng thái khóa (sự kiện `locked`). Không thao tác lên Windows: màn hình khóa là overlay web."""
        print(f"[LOCK] Ghi nhận khóa: {reason}")
        if record:
            local_cache.enqueue_event("locked", reason, 0)
        return True

    @staticmethod
    def blocked_entries(policy: Optional[dict]) -> Dict[str, Optional[int]]:
        """{sha256: kích thước file hoặc None nếu chưa biết}."""
        raw = (policy or {}).get("blocked_apps") or ""
        entries: Dict[str, Optional[int]] = {}
        try:
            items = json.loads(raw)
            items = items if isinstance(items, list) else []
        except ValueError:
            items = raw.replace(",", " ").split()
        for item in items:
            value = item.get("hash", "") if isinstance(item, dict) else str(item)
            value = value.strip().lower()
            if len(value) == 64:
                size = item.get("size") if isinstance(item, dict) else None
                entries[value] = size if isinstance(size, int) and size > 0 else None
        return entries

    @staticmethod
    def blocked_hashes(policy: Optional[dict]) -> Set[str]:
        return set(ProcessBlocker.blocked_entries(policy))

    def check_and_enforce(self, policy: Optional[dict] = None) -> int:
        """Quét tiến trình, kết thúc ứng dụng có SHA-256 bị cấm. Trả về số tiến trình đã dừng.

        Để dừng nhanh (< 2 giây) mà không băm mọi file .exe đang chạy: nếu mục cấm có kích thước file,
        chỉ băm các tiến trình có đúng kích thước đó. Mục cấm cũ không có kích thước thì băm toàn bộ (có cache).
        """
        policy = policy if policy is not None else local_cache.get_policy()
        blocked = self.blocked_entries(policy)
        if not blocked:
            return 0
        sizes = {size for size in blocked.values() if size}
        hash_everything = any(size is None for size in blocked.values())
        own = {os.getpid(), os.getppid()}
        killed = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pid, name = proc.info["pid"], proc.info["name"]
                if pid <= 4 or not name or pid in own or name.lower() in SYSTEM_PROCESSES:
                    continue
                exe = proc.exe()
                if not hash_everything:
                    try:
                        if os.stat(exe).st_size not in sizes:
                            continue
                    except OSError:
                        continue
                digest = self.calculate_file_sha256(exe)
                if digest and digest in blocked:
                    print(f"[BLOCKED] Dừng ứng dụng bị cấm: {name} ({digest[:16]}…)")
                    proc.kill()
                    killed += 1
                    self._dispatch_violation(name, (policy or {}).get("id"))
            except (psutil.Error, OSError):
                continue
        return killed


blocker = ProcessBlocker()
