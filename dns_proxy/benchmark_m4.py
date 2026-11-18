"""
OGK Benchmark M4 (Thành viên B - Đo lường Hiệu năng DNS Proxy 30 Mẫu Đo)
Theo Đề cương DoAn01 Mục M4
"""

import math
import os
import sys
import time
import psutil
from dnslib import DNSRecord

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from proxy_server import DNSProxyEngine


def calculate_percentile(data, percentile):
    if not data:
        return 0.0
    s = sorted(data)
    k = (len(s) - 1) * (percentile / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[int(f)] * (c - k) + s[int(c)] * (k - f)


def run_benchmark(samples_count: int = 30):
    print("=" * 75)
    print(f"CHUYÊN ĐỀ M4: ĐO LƯỜNG HIỆU NĂNG DNS PROXY VỚI {samples_count} MẪU TRUY VẤN")
    print("=" * 75)

    engine = DNSProxyEngine(upstream_dns="8.8.8.8", upstream_port=53)
    process = psutil.Process()
    process.cpu_percent(interval=None)

    test_domains = [
        "badsite-adult.test", "casino-sample-test.com", "violence-weapon-demo.org",
        "tiktok.com", "api.tiktok.com", "v16-web.tiktok.com",
        "roblox.com", "assetdelivery.roblox.com", "nordvpn.com", "expressvpn.com",
        "google.com", "www.google.com", "google.com.vn", "www.google.com.vn",
        "youtube.com", "www.youtube.com", "m.youtube.com", "bing.com", "www.bing.com",
        "use-application-dns.net", "mask.icloud.com", "cloudflare-dns.com",
        "example.com", "wikipedia.org", "python.org", "github.com",
        "khanacademy.org", "coursera.org", "stackoverflow.com", "microsoft.com"
    ]

    selected_domains = test_domains[:samples_count]
    while len(selected_domains) < samples_count:
        selected_domains.append(f"sub{len(selected_domains)}.example.com")

    latencies_ms = []
    print(f"{'STT':<5} | {'Domain':<30} | {'Action / Kết quả':<22} | {'Độ trễ (ms)':<12}")
    print("-" * 75)

    for idx, domain in enumerate(selected_domains, start=1):
        req = DNSRecord.question(domain, "A")
        t0 = time.perf_counter()
        resp_bytes = engine.handle_dns_request(req.pack())
        t_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(t_ms)

        resp = DNSRecord.parse(resp_bytes)
        ip = str(resp.rr[0].rdata) if resp.rr else "NXDOMAIN"

        if ip == "0.0.0.0":
            action = "BLOCKED (Sinkhole)"
        elif ip in ("216.239.38.120", "216.239.38.119", "204.79.197.220"):
            action = "SAFESEARCH (Rewrite)"
        elif resp.header.rcode == 3:
            action = "DOH CANARY (NXDOMAIN)"
        else:
            action = f"RESOLVED ({ip[:13]})"

        print(f"{idx:<5} | {domain:<30} | {action:<22} | {t_ms:>8.2f} ms")
        time.sleep(0.01)

    mem = process.memory_info().rss / (1024 * 1024)
    cpu = process.cpu_percent(interval=0.1)

    p50 = calculate_percentile(latencies_ms, 50)
    p95 = calculate_percentile(latencies_ms, 95)
    mean_lat = sum(latencies_ms) / len(latencies_ms)

    print("=" * 75)
    print("KẾT QUẢ THỰC NGHIỆM ĐO LƯỜNG HIỆU NĂNG (BÁO CÁO M4)")
    print("=" * 75)
    print(f"Tổng số mẫu đo        : {len(latencies_ms)} mẫu")
    print(f"Độ trễ trung bình     : {mean_lat:.2f} ms")
    print(f"Độ trễ trung vị (p50) : {p50:.2f} ms  <-- Tiêu chí p50")
    print(f"Độ trễ phân vị (p95)  : {p95:.2f} ms  <-- Tiêu chí p95")
    print(f"Chiếm dụng RAM        : {mem:.2f} MB")
    print(f"Sử dụng CPU           : {cpu:.1f} %")
    print("=" * 75)


if __name__ == "__main__":
    run_benchmark(30)

