"""
OGK DNS Proxy Server (Thành viên B - Network Security Core)
Lắng nghe cổng UDP 53 tại 127.0.0.1, phân loại tên miền, cưỡng chế SafeSearch,
chặn DoH canary và chuyển tiếp các truy vấn hợp lệ tới Upstream 8.8.8.8.
"""

import json
import os
import socket
import socketserver
import threading
from typing import Set
from dnslib import A, QTYPE, RCODE, RR, DNSRecord
import requests

from safesearch import check_safesearch_or_doh

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_blocklist_path() -> str:
    """Xác định đường dẫn blocklist.json cho cả môi trường Python lẫn PyInstaller .exe."""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "blocklist.json"))
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "blocklist.json"))
    candidates.append(os.path.join(CURRENT_DIR, "blocklist.json"))
    candidates.append(os.path.join(os.getcwd(), "blocklist.json"))
    for p in candidates:
        if os.path.exists(p):
            return p
    return os.path.join(CURRENT_DIR, "blocklist.json")


BLOCKLIST_FILE = _get_blocklist_path()


class DNSProxyEngine:
    def __init__(self, upstream_dns: str = "8.8.8.8", upstream_port: int = 53, server_url: str = "http://127.0.0.1:8000"):
        self.upstream_dns = upstream_dns
        self.upstream_port = upstream_port
        self.server_url = server_url
        self.blocked_domains: Set[str] = set()
        self._load_blocklist()

    def _load_blocklist(self):
        if not os.path.exists(BLOCKLIST_FILE):
            return
        try:
            with open(BLOCKLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            categories = data.get("categories", {})
            for _, domains in categories.items():
                for d in domains:
                    self.blocked_domains.add(d.strip().lower())
            for d in data.get("doh_resolvers", []):
                self.blocked_domains.add(d.strip().lower())
            print(f"[DNS_PROXY] Đã nạp {len(self.blocked_domains)} tên miền cấm (6 danh mục) từ blocklist.json.")
        except Exception as exc:
            print(f"[DNS_PROXY_ERROR] Lỗi nạp blocklist: {exc}")

    def is_blocked(self, qname: str) -> bool:
        """Kiểm tra tên miền có bị cấm không (hỗ trợ Wildcard Subdomains)."""
        qname = qname.strip().lower().rstrip(".")
        if qname in self.blocked_domains:
            return True
        parts = qname.split(".")
        for i in range(1, len(parts) - 1):
            if ".".join(parts[i:]) in self.blocked_domains:
                return True
        return False

    def report_violation(self, domain: str):
        """Gửi sự kiện vi phạm về FastAPI Server trong background thread."""
        def _send():
            try:
                import datetime
                payload = [{
                    "ts": datetime.datetime.utcnow().isoformat(),
                    "device_id": "DNS-PROXY-CLIENT",
                    "child_id": 1,
                    "type": "blocked_domain",
                    "subject": domain,
                    "duration_sec": 0,
                    "policy_id": 1
                }]
                requests.post(f"{self.server_url}/events/batch", json=payload, timeout=3.0)
            except Exception:
                pass
        threading.Thread(target=_send, daemon=True).start()

    def handle_dns_request(self, data: bytes) -> bytes:
        try:
            req = DNSRecord.parse(data)
        except Exception:
            return b""

        qname = str(req.q.qname).rstrip(".").lower()

        # 1. Kiểm tra SafeSearch hoặc DoH Canary
        ss_res = check_safesearch_or_doh(req)
        if ss_res:
            return ss_res

        # 2. Kiểm tra tên miền cấm (Sinkhole 0.0.0.0)
        if self.is_blocked(qname):
            print(f"[DOMAIN_BLOCKED] Chặn truy cập web cấm: {qname} (0.0.0.0)")
            self.report_violation(qname)
            reply = req.reply()
            reply.add_answer(RR(req.q.qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=60))
            return reply.pack()

        # 3. Chuyển tiếp Upstream DNS 8.8.8.8
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3.0)
            sock.sendto(data, (self.upstream_dns, self.upstream_port))
            resp, _ = sock.recvfrom(4096)
            sock.close()
            return resp
        except Exception:
            reply = req.reply()
            reply.header.rcode = RCODE.SERVFAIL
            return reply.pack()


class ThreadedUDPServer(socketserver.ThreadingMixIn, socketserver.UDPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, handler_cls, engine):
        super().__init__(addr, handler_cls)
        self.engine = engine


class DNSHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        resp = self.server.engine.handle_dns_request(data)
        if resp:
            try:
                sock.sendto(resp, self.client_address)
            except Exception:
                pass


def start_dns_server(host="127.0.0.1", port=53):
    print("=" * 65)
    print(f"OGK DNS PROXY SERVER LẮNG NGHE TẠI UDP {host}:{port}")
    print("Nhấn Ctrl + C để dừng server.")
    print("=" * 65)
    engine = DNSProxyEngine()
    server = ThreadedUDPServer((host, port), DNSHandler, engine)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Đang dừng DNS Proxy Server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    start_dns_server()

