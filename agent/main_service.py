"""
OGK Child Monitoring Agent - Windows Service & Debug Engine
Phụ trách: Thành viên A (System Core)
Chức năng:
- Windows Service chạy quyền LocalSystem (tự phục hồi M5)
- Giám sát tiến trình Foreground, tính giờ qua time.monotonic() (M6)
- Chặn ứng dụng bằng mã băm SHA-256 (blocker.py)
- Nhận lệnh khẩn cấp qua WebSocket (< 5s) và thực thi khóa máy
- Hỗ trợ chế độ chạy thử nghiệm độc lập (--debug) không cần cài Service
"""

import ctypes
import os
import sys
import threading
import time

# Đảm bảo đường dẫn import nội bộ chuẩn xác
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    import win32event  # type: ignore
    import win32service  # type: ignore
    import win32serviceutil  # type: ignore
except ImportError:
    win32event = None  # type: ignore
    win32service = None  # type: ignore
    win32serviceutil = None  # type: ignore

try:
    from agent.blocker import blocker
    from agent.local_cache import local_cache, flush_events_if_online
    from agent.tracker import tracker
    from agent.ws_client import ws_client
except ImportError:
    from blocker import blocker  # type: ignore
    from local_cache import local_cache, flush_events_if_online  # type: ignore
    from tracker import tracker  # type: ignore
    from ws_client import ws_client  # type: ignore


class OGKChildAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "OGKChildAgent"
    _svc_display_name_ = "OGK Child Monitoring Agent"
    _svc_description_ = "Dịch vụ giám sát thời gian sử dụng và bảo vệ an toàn thiết bị cho trẻ em."

    def __init__(self, args=None):
        # Khắc phục triệt để lỗi IndexError của pywin32 khi chạy debug hoặc standalone
        if not args:
            args = [self._svc_name_]
        try:
            win32serviceutil.ServiceFramework.__init__(self, args)
        except Exception:
            pass
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.is_running = True

    def SvcStop(self):
        """Dừng dịch vụ từ Service Manager"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.is_running = False
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        """Vòng lặp thực thi chính của Agent"""
        print(f"[*] Khởi động lõi OGK-Agent Service ({self._svc_name_})...")
        
        # 1. Khởi động WebSocket Client ở luồng riêng (nghe lệnh lock_now tức thì)
        ws_thread = threading.Thread(target=ws_client.start, daemon=True)
        ws_thread.start()

        # 2. Vòng lặp giám sát ứng dụng và đếm giờ
        flush_counter = 0
        while self.is_running:
            try:
                # Kiểm tra lùi giờ hệ thống (Chuyên đề M6)
                skew = tracker.check_clock_tamper(threshold_sec=60.0)
                if skew:
                    print(f"[CẢNH BÁO M6] Phát hiện lùi giờ hệ thống: {skew:.1f}s!")

                # Quét tiến trình Foreground và kiểm tra SHA-256
                tracker.tick()
                blocker.check_and_enforce()

                # Định kỳ 5s đồng bộ hàng đợi sự kiện và kiểm tra heartbeat
                flush_counter += 1
                if flush_counter >= 5:
                    flush_counter = 0
                    flush_events_if_online()
                    ws_client.send_heartbeat()

            except Exception as e:
                print(f"[LỖI AGENT ENGINE]: {e}")

            # Nghỉ 1 giây mỗi chu kỳ quét
            if win32event.WaitForSingleObject(self.stop_event, 1000) == win32event.WAIT_OBJECT_0:
                break

        print("[*] OGK-Agent Service đã dừng an toàn.")


def run_debug():
    """Hàm chạy console độc lập phục vụ kiểm thử và demo trực tiếp"""
    print("=" * 65)
    print("  OGK-AGENT: CHẾ ĐỘ GỠ LỖI TRỰC TIẾP (STANDALONE DEBUG)")
    print("  Nhấn Ctrl + C để dừng chương trình an toàn.")
    print("=" * 65)
    
    # 1. Khởi chạy luồng WebSocket để nhận lệnh khóa máy
    ws_thread = threading.Thread(target=ws_client.start, daemon=True)
    ws_thread.start()
    print("[*] Đã bật luồng kết nối WebSocket tới Server.")

    # 2. Vòng lặp giám sát trực tiếp
    flush_counter = 0
    try:
        while True:
            try:
                # Quét kiểm tra lùi giờ (M6)
                skew = tracker.check_clock_tamper(threshold_sec=60.0)
                if skew:
                    print(f"[CẢNH BÁO M6] Phát hiện lùi giờ hệ thống: {skew:.1f}s!")

                # Quét app và chặn SHA-256
                tracker.tick()
                blocker.check_and_enforce()

                # Định kỳ 5s đẩy sự kiện lên server nếu online
                flush_counter += 1
                if flush_counter >= 5:
                    flush_counter = 0
                    flush_events_if_online()
                    ws_client.send_heartbeat()
            except Exception as loop_err:
                pass

            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Đang dừng Agent Debug...")
        print("[*] Đã tắt thành công.")
    except Exception:
        pass

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1 and sys.argv[1].lower() in ["debug", "--debug", "-d", "run"]:
            run_debug()
        elif len(sys.argv) == 1:
            try:
                import servicemanager
                servicemanager.Initialize()
                servicemanager.PrepareToHostSingleService(OGKChildAgentService)
                servicemanager.StartServiceCtrlDispatcher()
            except Exception:
                run_debug()
        else:
            win32serviceutil.HandleCommandLine(OGKChildAgentService)
    except Exception as top_err:
        try:
            log_dir = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "OGKAgent", "logs")
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, "agent_error.log"), "a", encoding="utf-8") as f:
                import datetime, traceback
                f.write(f"[{datetime.datetime.now().isoformat()}] {top_err}\n{traceback.format_exc()}\n")
        except Exception:
            pass