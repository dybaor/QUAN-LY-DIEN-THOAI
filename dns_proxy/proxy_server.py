"""
OGK DNS Proxy Server (F2-3, F2-4, F2-5)
- Lắng nghe UDP 127.0.0.1:53, cưỡng chế SafeSearch và chặn DoH (canary + resolver công cộng).
- Phân loại tên miền theo 6 nhóm chuẩn; nhóm bị chặn lấy từ chính sách của trẻ trong bộ nhớ đệm Agent
  (`blocked_categories`, `blocked_domains`), mặc định cấu hình cho trẻ 6–11 tuổi khi chưa có chính sách.
- Ghi sự kiện `domain_query` / `blocked_domain` (chỉ tên miền cấp 2, không lưu URL) vào hàng đợi của Agent
  để Agent gửi lên máy chủ bằng token đã ghép đôi.
"""

import json
import os
import socket
import socketserver
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Optional, Set, Tuple

from dnslib import A, QTYPE, RCODE, RR, DNSRecord

from safesearch import check_safesearch_or_doh

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILE = "6-11"
POLICY_REFRESH_SEC = 30
QUERY_REPORT_INTERVAL_SEC = 600
SECOND_LEVEL_SUFFIXES = {"com", "net", "org", "edu", "gov", "ac", "co", "info", "biz", "name", "pro", "health", "int"}


def _find_file(name: str) -> str:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), name))
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, name))
    candidates += [os.path.join(CURRENT_DIR, name), os.path.join(os.getcwd(), name)]
    return next((path for path in candidates if os.path.exists(path)), candidates[-1])


BLOCKLIST_FILE = _find_file("blocklist.json")
AGENT_CACHE = os.environ.get("OGK_AGENT_CACHE") or os.path.join(
    os.environ.get("OGK_AGENT_DATA") or os.path.expandvars(r"%ProgramData%\OGKAgent"), "agent_cache.db")


def registrable_domain(qname: str) -> str:
    """Tên miền cấp 2 (vd. m.youtube.com → youtube.com, www.vnexpress.net → vnexpress.net, a.b.com.vn → b.com.vn)."""
    parts = qname.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in SECOND_LEVEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


class DNSProxyEngine:
    def __init__(self, upstream_dns: str = "8.8.8.8", upstream_port: int = 53, cache_path: str = AGENT_CACHE):
        self.upstream_dns = upstream_dns
        self.upstream_port = upstream_port
        self.cache_path = cache_path
        self.domain_category: Dict[str, str] = {}
        self.doh_resolvers: Set[str] = set()
        self.age_profiles: Dict[str, list] = {}
        self.blocked_categories: Set[str] = set()
        self.custom_blocked: Set[str] = set()
        self.identity: Tuple[Optional[str], Optional[int]] = (None, None)
        self._policy_loaded_at = 0.0
        self._reported: Dict[Tuple[str, str], float] = {}
        self._lock = threading.Lock()
        self._load_blocklist()
        self.refresh_policy(force=True)

    # ---------- Danh mục & chính sách ----------
    def _load_blocklist(self):
        with open(BLOCKLIST_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        for category, domains in data.get("categories", {}).items():
            for domain in domains:
                self.domain_category[domain.strip().lower()] = category
        self.doh_resolvers = {d.strip().lower() for d in data.get("doh_resolvers", [])}
        self.age_profiles = data.get("age_profiles", {})
        self.blocked_categories = set(self.age_profiles.get(DEFAULT_PROFILE, ["inappropriate"]))
        print(f"[DNS_PROXY] Đã nạp {len(self.domain_category)} tên miền thuộc 6 nhóm nội dung.")

    def _cache(self) -> Optional[sqlite3.Connection]:
        if not os.path.exists(self.cache_path):
            return None
        conn = sqlite3.connect(self.cache_path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def refresh_policy(self, force: bool = False):
        if not force and time.monotonic() - self._policy_loaded_at < POLICY_REFRESH_SEC:
            return
        self._policy_loaded_at = time.monotonic()
        try:
            conn = self._cache()
            if not conn:
                return
            with conn:
                identity = dict(conn.execute("SELECT key, value FROM agent_identity WHERE key IN ('device_id','child_id')"))
                row = conn.execute("SELECT payload FROM cached_policy ORDER BY updated_at DESC LIMIT 1").fetchone()
            conn.close()
        except sqlite3.Error:
            return
        self.identity = (identity.get("device_id"), int(identity["child_id"]) if identity.get("child_id") else None)
        if row:
            policy = json.loads(row[0])
            categories = policy.get("blocked_categories")
            if categories is not None:
                self.blocked_categories = {c for c in categories.split(",") if c}
            self.custom_blocked = {d.strip().lower() for d in (policy.get("blocked_domains") or "").replace("\n", ",").split(",")
                                   if d.strip()}

    def classify(self, qname: str) -> str:
        parts = qname.split(".")
        for i in range(len(parts) - 1):
            category = self.domain_category.get(".".join(parts[i:]))
            if category:
                return category
        return "unclassified"

    def _matches(self, qname: str, domains: Set[str]) -> bool:
        parts = qname.split(".")
        return any(".".join(parts[i:]) in domains for i in range(len(parts) - 1))

    def is_blocked(self, qname: str) -> Tuple[bool, str]:
        qname = qname.strip().lower().rstrip(".")
        if self._matches(qname, self.doh_resolvers):
            return True, "doh_resolver"
        if self._matches(qname, self.custom_blocked):
            return True, "custom"
        category = self.classify(qname)
        return category in self.blocked_categories, category

    # ---------- Ghi sự kiện vào hàng đợi Agent ----------
    def report(self, qname: str, event_type: str):
        device_id, child_id = self.identity
        if not device_id or not child_id or "." not in qname or qname.endswith((".arpa", ".local")):
            return
        domain = registrable_domain(qname)
        key = (domain, event_type)
        now = time.monotonic()
        with self._lock:
            if now - self._reported.get(key, -QUERY_REPORT_INTERVAL_SEC) < QUERY_REPORT_INTERVAL_SEC:
                return
            self._reported[key] = now
        threading.Thread(target=self._enqueue, args=(device_id, child_id, event_type, domain), daemon=True).start()

    def _enqueue(self, device_id: str, child_id: int, event_type: str, domain: str):
        try:
            conn = self._cache()
            if not conn:
                return
            with conn:
                conn.execute(
                    "INSERT INTO event_queue (ts, device_id, child_id, type, subject, duration_sec, policy_id, idempotency_key) "
                    "VALUES (?, ?, ?, ?, ?, 0, NULL, ?)",
                    (datetime.utcnow().isoformat(), device_id, child_id, event_type, domain, uuid.uuid4().hex))
            conn.close()
        except sqlite3.Error:
            pass

    # ---------- Xử lý truy vấn ----------
    def handle_dns_request(self, data: bytes) -> bytes:
        try:
            req = DNSRecord.parse(data)
        except Exception:
            return b""
        self.refresh_policy()
        qname = str(req.q.qname).rstrip(".").lower()

        safe_reply = check_safesearch_or_doh(req)
        if safe_reply:
            self.report(qname, "domain_query")
            return safe_reply

        blocked, reason = self.is_blocked(qname)
        if blocked:
            print(f"[DOMAIN_BLOCKED] {qname} ({reason}) → 0.0.0.0")
            self.report(qname, "blocked_domain")
            reply = req.reply()
            if req.q.qtype in (QTYPE.A, QTYPE.ANY):
                reply.add_answer(RR(req.q.qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=60))
            else:
                reply.header.rcode = RCODE.NXDOMAIN
            return reply.pack()

        if req.q.qtype in (QTYPE.A, QTYPE.AAAA):
            self.report(qname, "domain_query")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(3.0)
                sock.connect((self.upstream_dns, self.upstream_port))
                sock.send(data)
                return sock.recv(4096)
        except OSError:
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
            except OSError:
                pass


def start_dns_server(host="127.0.0.1", port=53):
    print("=" * 65)
    print(f"OGK DNS PROXY SERVER LẮNG NGHE TẠI UDP {host}:{port} — Ctrl + C để dừng")
    print("=" * 65)
    server = ThreadedUDPServer((host, port), DNSHandler, DNSProxyEngine())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Đang dừng DNS Proxy Server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    start_dns_server()
