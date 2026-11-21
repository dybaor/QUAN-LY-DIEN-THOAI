"""DNS Proxy: 6 nhóm nội dung, chính sách theo độ tuổi đọc từ cache Agent, ghi sự kiện domain (F2-3, F2-4)."""

import json
import time

import pytest

from local_cache import LocalCache
from proxy_server import BLOCKLIST_FILE, DNSProxyEngine, registrable_domain


def test_blocklist_has_six_standard_categories():
    with open(BLOCKLIST_FILE, encoding="utf-8") as handle:
        data = json.load(handle)
    assert set(data["categories"]) == {"education", "entertainment", "social_media", "games", "inappropriate", "unclassified"}
    assert data["age_profiles"]["6-11"] == ["social_media", "games", "inappropriate"]


def test_registrable_domain():
    assert registrable_domain("m.youtube.com") == "youtube.com"
    assert registrable_domain("www.vnexpress.net") == "vnexpress.net"
    assert registrable_domain("thi.hocmai.com.vn") == "hocmai.com.vn"


def test_default_profile_without_agent_cache(tmp_path):
    engine = DNSProxyEngine(cache_path=str(tmp_path / "missing.db"))
    assert engine.is_blocked("www.facebook.com") == (True, "social_media")
    assert engine.is_blocked("vi.wikipedia.org") == (False, "education")
    assert engine.is_blocked("example.org") == (False, "unclassified")
    assert engine.is_blocked("dns.google")[0] is True


@pytest.fixture
def enrolled_cache(tmp_path):
    cache = LocalCache(db_path=str(tmp_path / "agent_cache.db"))
    cache.save_identity("dev-dns", 3, "a", "r", "k")
    cache.save_policy({"child_id": 3, "version": 2, "blocked_categories": "inappropriate",
                       "blocked_domains": "vi-du-game.com,extra.test"})
    return cache


def test_policy_categories_and_custom_domains_from_cache(enrolled_cache):
    engine = DNSProxyEngine(cache_path=enrolled_cache.db_path)
    assert engine.is_blocked("www.facebook.com") == (False, "social_media"), "Phụ huynh đã cho phép mạng xã hội"
    assert engine.is_blocked("cdn.vi-du-game.com") == (True, "custom")
    assert engine.is_blocked("www.pornhub.com")[0] is True


def test_queries_reported_to_agent_queue_with_dedup(enrolled_cache):
    engine = DNSProxyEngine(cache_path=enrolled_cache.db_path)
    for name in ("www.wikipedia.org", "en.wikipedia.org", "www.pornhub.com"):
        engine.report(name, "blocked_domain" if "porn" in name else "domain_query")
    deadline = time.monotonic() + 2
    while len(enrolled_cache.peek_events()) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    events = {(e["type"], e["subject"]) for e in enrolled_cache.peek_events()}
    assert events == {("domain_query", "wikipedia.org"), ("blocked_domain", "pornhub.com")}
    assert all(e["device_id"] == "dev-dns" and e["child_id"] == 3 for e in enrolled_cache.peek_events())
