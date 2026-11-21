"""
OGK Child Monitoring Agent — Windows Service (LocalSystem) & chế độ debug.

Lệnh:
  python main_service.py enroll <MÃ-8-KÝ-TỰ>   Ghép đôi máy với tài khoản phụ huynh
  python main_service.py status                Xem trạng thái ghép đôi
  python main_service.py debug                 Chạy trực tiếp trong phiên người dùng (kèm biểu tượng khay)
  python main_service.py tray                  Chỉ chạy biểu tượng khay hệ thống (phiên của trẻ)
  python main_service.py uninstall             Gỡ cài đặt (bắt buộc tài khoản phụ huynh)
  python main_service.py install|remove|start|stop   Quản lý Windows Service (cần quyền Administrator)

Agent chỉ ghi sự kiện (app_start/app_stop/blocked_app/quota_warning/locked...) và chặn tiến trình bị cấm;
KHÔNG khóa Windows và KHÔNG mở hộp thoại. Khóa/cảnh báo hiển thị bằng overlay trong Cổng học tập (web).

Khi chạy dạng Service, giao diện khay hệ thống (`tray_ui.py`) trong phiên của trẻ là bắt buộc: nếu không thấy
giao diện quá 2 phút, Agent tự tạm dừng giám sát và báo cho phụ huynh (chống phần mềm theo dõi ẩn — F5-6).
"""

import os
import sys
import threading
import time

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import win32event
import win32service
import win32serviceutil

import settings
from blocker import blocker
from enforcer import TimeEnforcer, is_paused
from local_cache import local_cache
from tracker import tracker
from ui_bridge import LocalBridge, PipeBridge, UIBridge
from ws_client import ws_client


class AgentEngine:
    def __init__(self, bridge: UIBridge):
        self.bridge = bridge
        self.enforcer = TimeEnforcer(blocker, local_cache.enqueue_event)
        self.monitoring = True
        self._tick = 0
        self._step_lock = threading.Lock()  # Lệnh WebSocket và vòng lặp chính không chạy chồng nhau
        ws_client.on_server_time = tracker.check_server_time
        for command in ("lock_window", "lock_now", "lock"):
            ws_client.on(command, self._on_lock)
        for command in ("unlock_window", "unlock"):
            ws_client.on(command, self._on_unlock)
        for command in ("sync_policy", "extend_time", "time_deducted", "settings_updated"):
            ws_client.on(command, lambda data: ws_client.sync_policy())
        ws_client.on("purge_cache", self._on_purge)
        ws_client.on("device_removed", self._on_removed)

    # ---------- Lệnh từ phụ huynh ----------
    def _on_lock(self, data: dict):
        self.enforcer.manual_lock = data.get("reason") or "Lệnh từ phụ huynh"
        self.step()

    def _on_unlock(self, data: dict):
        self.enforcer.manual_lock = None
        self.enforcer.reset()
        ws_client.sync_policy()

    def _on_purge(self, data: dict):
        local_cache.purge_activity()
        print("[PRIVACY] Đã xóa bộ nhớ đệm hoạt động theo yêu cầu của phụ huynh.")

    def _on_removed(self, data: dict):
        local_cache.clear_identity()
        print("[PAIRING] Máy đã được phụ huynh gỡ ghép đôi. OGK ngừng giám sát.")

    # ---------- Vòng lặp chính (mỗi giây) ----------
    def step(self):
        with self._step_lock:
            self._step()

    def _step(self):
        if not local_cache.is_enrolled:
            return
        ui_ok = self.bridge.present()
        if ui_ok != self.monitoring:
            self.monitoring = ui_ok
            ws_client.ui_present = ui_ok
            print("[ANTI-STALKERWARE] " + ("Giao diện khay đã hoạt động lại — tiếp tục giám sát." if ui_ok
                                          else "Không thấy giao diện khay hệ thống — tạm dừng giám sát."))
            threading.Thread(target=ws_client.send_heartbeat, daemon=True).start()
        if not ui_ok:
            tracker.tick(None)
            return
        policy = local_cache.get_policy()
        paused = is_paused(policy or {})
        state = self.bridge.state()
        tracker.check_clock_tamper()
        tracker.tick(state, counting=not paused)
        if self._tick % 2 == 0:
            blocker.check_and_enforce(policy)  # Chặn ứng dụng vẫn áp dụng khi tạm nghỉ giới hạn thời gian
        status = self.enforcer.evaluate(policy, local_cache.get_today_usage_seconds())
        self.bridge.publish_status(status)

    def run(self, stop_requested):
        ws_client.start()
        threading.Thread(target=ws_client.send_heartbeat, daemon=True).start()
        last_heartbeat = time.monotonic()
        while not stop_requested():
            try:
                self.step()
                if time.monotonic() - last_heartbeat >= settings.HEARTBEAT_INTERVAL_SEC:
                    last_heartbeat = time.monotonic()
                    threading.Thread(target=ws_client.send_heartbeat, daemon=True).start()
            except Exception as exc:
                print(f"[LỖI AGENT ENGINE]: {exc}")
            self._tick += 1
            time.sleep(1)
        tracker.finalize_current_app()
        ws_client.stop()


class OGKChildAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "OGKChildAgent"
    _svc_display_name_ = "OGK Child Monitoring Agent"
    _svc_description_ = "Quản lý thời gian sử dụng và bảo vệ an toàn thiết bị cho trẻ em (luôn hiển thị biểu tượng khay)."

    def __init__(self, args=None):
        try:
            win32serviceutil.ServiceFramework.__init__(self, args or [self._svc_name_])
        except Exception:
            pass  # Cho phép khởi tạo ngoài Service Control Manager (kiểm thử / debug)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.is_running = False
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        bridge = PipeBridge()
        bridge.start()
        AgentEngine(bridge).run(lambda: not self.is_running)
        bridge.stop()


def run_debug():
    from tray_ui import TrayApp

    print("=" * 65)
    print("  OGK-AGENT: CHẾ ĐỘ CHẠY TRỰC TIẾP (DEBUG) — Ctrl + C để dừng")
    print("=" * 65)
    if not local_cache.is_enrolled:
        print("[!] Máy chưa ghép đôi. Chạy: python main_service.py enroll <MÃ> (mã tạo trên dashboard phụ huynh).")
    engine = AgentEngine(LocalBridge(TrayApp().start_in_thread()))
    try:
        engine.run(lambda: False)
    except KeyboardInterrupt:
        print("\n[*] Đã dừng Agent.")


def main(argv):
    command = argv[1].lower() if len(argv) > 1 else ""
    if command in ("debug", "--debug", "-d", "run"):
        run_debug()
    elif command == "enroll":
        from enrollment import enroll
        if len(argv) < 3:
            sys.exit("Cách dùng: python main_service.py enroll <MÃ-8-KÝ-TỰ>")
        data = enroll(argv[2])
        print(f"[OK] Đã ghép đôi với hồ sơ trẻ '{data.get('child_name') or data['child_id']}'. Device ID: {data['device_id']}")
    elif command == "tray":
        from tray_ui import main as tray_main
        tray_main()
    elif command == "uninstall":
        from uninstall_agent import run as uninstall_run
        sys.exit(uninstall_run())
    elif command == "status":
        print(f"Máy chủ: {settings.SERVER_URL}")
        print(f"Đã ghép đôi: {'có' if local_cache.is_enrolled else 'chưa'} — device_id={local_cache.device_id}, "
              f"child_id={local_cache.child_id}")
    elif not command:
        import servicemanager
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingleService(OGKChildAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(OGKChildAgentService)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except SystemExit:
        raise
    except Exception as top_err:
        import datetime
        import traceback
        log_dir = os.path.join(settings.DATA_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "agent_error.log"), "a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.datetime.now().isoformat()}] {top_err}\n{traceback.format_exc()}\n")
        raise
