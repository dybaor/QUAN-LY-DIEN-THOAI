#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
OGK - IN-APP SAFE BROWSER & DOMAIN INTERCEPTION MODULE
Dự án: Người Bạn Đồng Hành (OGK Parental Control System)
Mục tiêu:
1. Nhúng trình duyệt an toàn (Internal WebView) trực tiếp trong ứng dụng của trẻ.
2. TUYỆT ĐỐI không gọi webbrowser.open() hay os.startfile() ra trình duyệt ngoài.
3. Kiểm soát tên miền (Domain Interception): So khớp URL với blocked_domains từ local_cache.
4. Chặn ngay lập tức các domain cấm (youtube, facebook, tiktok, web đen...) và hiển thị trang cảnh báo an toàn.
================================================================================
"""

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Tuple
from urllib.parse import urlparse

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    from agent.local_cache import local_cache
except ImportError:
    from local_cache import local_cache  # type: ignore

# Danh mục tên miền mặc định cần chặn nếu cha mẹ cấu hình hoặc trong blocklist
DEFAULT_BLOCKED_KEYWORDS = [
    "facebook.com", "fb.com", "messenger.com",
    "tiktok.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "youtu.be",
    "discord.com", "telegram.org",
    "roblox.com", "steamcommunity.com",
    "bet", "casino", "poker", "porn", "xxx", "18plus"
]


def extract_domain(url: str) -> str:
    """Tách tên miền sạch từ URL."""
    if not url:
        return ""
    if not url.startswith(("http://", "https://", "ftp://")):
        url = "http://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if ":" in domain:
            domain = domain.split(":")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def is_domain_blocked(url: str) -> Tuple[bool, str]:
    """
    Kiểm tra URL có thuộc tên miền bị cấm hay không.
    Trả về (is_blocked: bool, reason: str).
    """
    domain = extract_domain(url)
    if not domain:
        return False, ""

    # 1. Đọc blocked_domains từ policy trong local_cache
    policy = local_cache.get_policy()
    blocked_domains_list = []
    if policy:
        raw_domains = policy.get("blocked_domains", "") or ""
        if raw_domains:
            try:
                if raw_domains.startswith("["):
                    blocked_domains_list = json.loads(raw_domains)
                else:
                    blocked_domains_list = [d.strip().lower() for d in raw_domains.split(",") if d.strip()]
            except Exception:
                blocked_domains_list = [d.strip().lower() for d in raw_domains.split(",") if d.strip()]

    # Hợp nhất danh sách policy với danh sách mặc định
    all_blocked = set(blocked_domains_list).union(set(DEFAULT_BLOCKED_KEYWORDS))

    # 2. So khớp domain
    for b in all_blocked:
        b_clean = b.strip().lower()
        if not b_clean:
            continue
        if b_clean.startswith("www."):
            b_clean = b_clean[4:]
        if domain == b_clean or domain.endswith("." + b_clean) or (len(b_clean) > 3 and b_clean in domain):
            return True, f"Tên miền '{domain}' nằm trong danh sách hạn chế truy cập của cha mẹ."

    # 3. Kiểm tra blocklist.json từ DNS proxy nếu có
    try:
        blocklist_file = os.path.join(os.path.dirname(CURRENT_DIR), "dns_proxy", "blocklist.json")
        if os.path.isfile(blocklist_file):
            with open(blocklist_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                b_domains = data.get("blocked_domains", [])
                for b in b_domains:
                    b_clean = b.lower()
                    if domain == b_clean or domain.endswith("." + b_clean):
                        return True, f"Tên miền '{domain}' nằm trong danh sách đen lọc mạng SafeSearch."
    except Exception:
        pass

    return False, ""


def render_blocked_html(url: str, domain: str, reason: str) -> str:
    """Tạo mã HTML cảnh báo an toàn hiển thị ngay trong cửa sổ Safe Browser."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Trang Web Đã Bị Hạn Chế — OGK Safe Browser</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: linear-gradient(135deg, #0b1329 0%, #0f172a 100%);
      color: #f8fafc;
      display: flex;
      justify-content: center;
      align-items: center;
      height: 100vh;
      margin: 0;
      padding: 20px;
    }}
    .card {{
      background: rgba(30, 41, 59, 0.85);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(244, 63, 94, 0.3);
      border-radius: 28px;
      padding: 40px 32px;
      text-align: center;
      max-width: 480px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
    }}
    .shield-icon {{
      font-size: 64px;
      margin-bottom: 16px;
      filter: drop-shadow(0 4px 12px rgba(244, 63, 94, 0.4));
    }}
    h1 {{
      color: #fb7185;
      font-size: 22px;
      font-weight: 800;
      margin: 0 0 12px 0;
      letter-spacing: -0.5px;
    }}
    p {{
      color: #94a3b8;
      font-size: 14px;
      line-height: 1.6;
      margin: 8px 0;
    }}
    .badge {{
      display: inline-block;
      background: rgba(136, 19, 55, 0.6);
      border: 1px solid #e11d48;
      color: #fda4af;
      padding: 6px 14px;
      border-radius: 9999px;
      font-weight: 700;
      font-size: 13px;
      margin: 14px 0;
      font-family: Consolas, monospace;
    }}
    .footer-note {{
      color: #64748b;
      font-size: 12px;
      margin-top: 24px;
      border-top: 1px solid rgba(51, 65, 85, 0.5);
      padding-top: 16px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="shield-icon">🛡️🚫</div>
    <h1>TRANG WEB ĐÃ BỊ HẠN CHẾ</h1>
    <p>Người Bạn Đồng Hành đã tự động chặn liên kết này để bảo vệ bạn:</p>
    <div class="badge">{domain or url}</div>
    <p>{reason}</p>
    <div class="footer-note">
      Trình duyệt an toàn nội bộ (In-App Safe Browser) • Không rò rỉ ra ngoài
    </div>
  </div>
</body>
</html>"""


class InAppSafeBrowserWindow:
    """
    Cửa sổ Trình duyệt An Toàn nội bộ (In-App Safe Browser).
    Chạy trực tiếp trong hệ sinh thái ứng dụng của trẻ, không mở trình duyệt ngoài.
    Hỗ trợ kiểm tra tên miền trước khi điều hướng.
    """

    def __init__(self, target_url: str, title: str = "Trình Duyệt An Toàn — OGK Safe Browser"):
        self.target_url = target_url
        self.title = title
        self.window = None

    def open(self, gui: bool = True) -> Tuple[bool, str, str]:
        """Khởi chạy trình duyệt an toàn nội bộ. Trả về (is_blocked, domain, reason)."""
        domain = extract_domain(self.target_url)
        is_blocked, reason = is_domain_blocked(self.target_url)

        # Ghi nhận sự kiện duyệt web
        try:
            local_cache.enqueue_event(
                event_type="blocked_domain" if is_blocked else "web_visited",
                subject=domain or self.target_url,
                duration_sec=0,
                policy_id=1
            )
        except Exception:
            pass

        if not gui:
            return is_blocked, domain, reason

        # 1. Thử dùng pywebview nếu có
        try:
            import webview  # type: ignore

            if is_blocked:
                html_content = render_blocked_html(self.target_url, domain, reason)
                win = webview.create_window(
                    title=f"🛡️ Hạn Chế — {domain}",
                    html=html_content,
                    width=960,
                    height=640,
                    min_size=(640, 480)
                )
            else:
                win = webview.create_window(
                    title=f"🛡️ Safe Browser — {domain}",
                    url=self.target_url,
                    width=1024,
                    height=700,
                    min_size=(640, 480)
                )

            # Chạy webview trong thread riêng
            threading.Thread(target=lambda: webview.start(), daemon=True).start()
            return is_blocked, domain, reason

        except Exception as exc:
            print(f"[SAFE_BROWSER] WebView fallback: {exc}")
            # 2. Fallback sang In-App Tkinter Safe Browser Window
            try:
                self._open_tkinter_safe_window(is_blocked, reason, domain)
            except Exception:
                pass
            return is_blocked, domain, reason

    def _open_tkinter_safe_window(self, is_blocked: bool, reason: str, domain: str):
        """Fallback Tkinter Safe Browser Window nội bộ."""
        top = tk.Toplevel()
        top.title(f"🛡️ Safe Browser — {domain or self.target_url}")
        top.geometry("860x600+250+120")
        top.configure(bg="#0b1329")
        top.attributes("-topmost", True)

        # Header Address Bar
        nav_bar = tk.Frame(top, bg="#0f172a", pady=8, padx=12)
        nav_bar.pack(fill=tk.X)

        tk.Label(nav_bar, text="🛡️ SAFE BROWSER:", font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a").pack(side=tk.LEFT, padx=(0, 8))

        url_entry = tk.Entry(nav_bar, font=("Segoe UI", 10), bg="#1e293b", fg="#ffffff", relief=tk.FLAT)
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        url_entry.insert(0, self.target_url)

        status_badge = tk.Label(
            nav_bar,
            text="✕ BỊ HẠN CHẾ" if is_blocked else "✓ AN TOÀN",
            font=("Segoe UI", 9, "bold"),
            fg="#f43f5e" if is_blocked else "#10b981",
            bg="#881337" if is_blocked else "#064e3b",
            padx=8,
            pady=3
        )
        status_badge.pack(side=tk.RIGHT, padx=4)

        # Thân trang nội bộ
        body = tk.Frame(top, bg="#0b1329", padx=24, pady=24)
        body.pack(fill=tk.BOTH, expand=True)

        if is_blocked:
            center_card = tk.Frame(body, bg="#1e293b", padx=36, pady=32, relief=tk.FLAT)
            center_card.place(relx=0.5, rely=0.5, anchor="center")

            tk.Label(center_card, text="🛡️🚫", font=("Segoe UI", 48), bg="#1e293b").pack(pady=(0, 10))
            tk.Label(center_card, text="TRANG WEB ĐÃ BỊ HẠN CHẾ", font=("Segoe UI", 16, "bold"), fg="#f43f5e", bg="#1e293b").pack()

            domain_chip = tk.Label(center_card, text=domain or self.target_url, font=("Consolas", 11, "bold"), fg="#fda4af", bg="#881337", padx=12, pady=4)
            domain_chip.pack(pady=10)

            tk.Label(center_card, text=reason, font=("Segoe UI", 11), fg="#cbd5e1", bg="#1e293b", justify=tk.CENTER).pack(pady=6)
            tk.Label(center_card, text="Trình duyệt nội bộ đang bảo vệ bạn khỏi các nội dung không phù hợp.", font=("Segoe UI", 9), fg="#64748b", bg="#1e293b").pack(pady=(12, 0))
        else:
            center_card = tk.Frame(body, bg="#1e293b", padx=36, pady=32, relief=tk.FLAT)
            center_card.place(relx=0.5, rely=0.5, anchor="center")

            tk.Label(center_card, text="🌐", font=("Segoe UI", 48), bg="#1e293b").pack(pady=(0, 10))
            tk.Label(center_card, text="PHIÊN DUYỆT WEB AN TOÀN NỘI BỘ", font=("Segoe UI", 16, "bold"), fg="#38bdf8", bg="#1e293b").pack()

            domain_chip = tk.Label(center_card, text=f"Đang mở an toàn: {domain or self.target_url}", font=("Segoe UI", 11, "bold"), fg="#10b981", bg="#064e3b", padx=12, pady=4)
            domain_chip.pack(pady=10)

            tk.Label(center_card, text="Trang web hợp lệ phục vụ học tập và tra cứu kiến thức.", font=("Segoe UI", 11), fg="#cbd5e1", bg="#1e293b").pack(pady=6)
            tk.Label(center_card, text="Mọi hoạt động đều được lọc qua cơ chế SafeSearch nội bộ.", font=("Segoe UI", 9), fg="#64748b", bg="#1e293b").pack(pady=(12, 0))


def open_safe_browser(url: str, title: str = "Trình Duyệt An Toàn — OGK Safe Browser", gui: bool = True) -> Tuple[bool, str, str]:
    """
    Hàm giao tiếp duy nhất để mở bất kỳ trang web nào.
    TUYỆT ĐỐI không gọi webbrowser.open() hay os.startfile().
    """
    browser = InAppSafeBrowserWindow(url, title)
    return browser.open(gui=gui)
