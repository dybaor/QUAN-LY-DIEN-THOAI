"""
OGK SafeSearch & DoH Canary Controller (Thành viên B)
- Cưỡng chế SafeSearch bằng cách rewrite IP chính thức của Google, YouTube, Bing.
- Trả mã lỗi NXDOMAIN cho các miền DoH Canary (use-application-dns.net, mask.icloud.com)
  nhằm vô hiệu hóa tính năng DNS-over-HTTPS của trình duyệt (Firefox, Chrome, Edge).
"""

from typing import Dict, Optional, Set
from dnslib import A, AAAA, QTYPE, RCODE, RR, DNSRecord

# Danh sách IP SafeSearch chính thức
SAFESEARCH_MAP: Dict[str, str] = {
    "google.com": "216.239.38.120",
    "www.google.com": "216.239.38.120",
    "google.com.vn": "216.239.38.120",
    "www.google.com.vn": "216.239.38.120",
    "youtube.com": "216.239.38.119",
    "www.youtube.com": "216.239.38.119",
    "m.youtube.com": "216.239.38.119",
    "youtubei.googleapis.com": "216.239.38.119",
    "bing.com": "204.79.197.220",
    "www.bing.com": "204.79.197.220",
}
GOOGLE_SAFESEARCH_IPV4 = "216.239.38.120"
GOOGLE_SAFESEARCH_IPV6 = "2001:4860:4802:32::78"

# Danh sách miền Canary DoH
DOH_CANARY_DOMAINS: Set[str] = {
    "use-application-dns.net",
    "mask.icloud.com",
    "mask-h2.icloud.com",
}


def check_safesearch_or_doh(request: DNSRecord) -> Optional[bytes]:
    """Kiểm tra và xử lý SafeSearch Rewrite hoặc Canary NXDOMAIN.
    
    Trả về bytes gói tin DNS response nếu match, ngược lại trả về None.
    """
    qname = str(request.q.qname).rstrip(".").lower()
    qtype = QTYPE[request.q.qtype]

    # 1. Chặn DoH Canary -> Trả NXDOMAIN
    if qname in DOH_CANARY_DOMAINS:
        reply = request.reply()
        reply.header.rcode = RCODE.NXDOMAIN
        return reply.pack()

    # 2. Cưỡng chế SafeSearch -> Rewrite IP
    if qname in SAFESEARCH_MAP:
        safe_ip = SAFESEARCH_MAP[qname]
        reply = request.reply()
        if qtype in ("A", "ANY"):
            reply.add_answer(RR(request.q.qname, QTYPE.A, rdata=A(safe_ip), ttl=300))
        if qtype in ("AAAA", "ANY") and safe_ip == GOOGLE_SAFESEARCH_IPV4:
            reply.add_answer(RR(request.q.qname, QTYPE.AAAA, rdata=AAAA(GOOGLE_SAFESEARCH_IPV6), ttl=300))
        return reply.pack()

    return None

