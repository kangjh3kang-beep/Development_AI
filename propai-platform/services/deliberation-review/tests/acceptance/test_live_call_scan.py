"""INC-15 — INV-13 소비경로 라이브 호출 부재 강제 + 스캐너 자기검증.

소비경로(regulation/legal 어댑터·land·cross_validate)는 외부 1차출처를 **반드시 AdapterCache(cached_get)
경유**로만 호출해야 한다(INV-13: 소비측 라이브 미호출·결정론·무음0). 직접 httpx/requests 호출 0건을 강제.
"""
import pathlib

from tools.live_call_scan import scan_for_uncached_live_calls

_APP = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "app"
_TARGET_DIRS = [
    "adapters/regulation",
    "adapters/legal",
    "services/land",
    "services/cross_validate",
]


def test_no_uncached_live_calls_in_consume_path():
    offenders: dict[str, list[str]] = {}
    for rel in _TARGET_DIRS:
        for py in (_APP / rel).rglob("*.py"):
            hits = scan_for_uncached_live_calls(py.read_text(encoding="utf-8"))
            if hits:
                offenders[str(py.relative_to(_APP))] = hits
    assert offenders == {}, f"캐시 우회 라이브 호출(INV-13 위반) — cached_get 경유 필요: {offenders}"


def test_scanner_detects_direct_httpx():
    src = "import httpx\ndef f():\n    return httpx.get('http://x')\n"
    assert any("httpx.get" in h for h in scan_for_uncached_live_calls(src))


def test_scanner_detects_requests_and_client():
    src = "import httpx, requests\nr = requests.post('u')\nc = httpx.AsyncClient()\n"
    hits = scan_for_uncached_live_calls(src)
    assert any("requests.post" in h for h in hits)
    assert any("httpx.AsyncClient" in h for h in hits)


def test_scanner_allows_cached_get_path():
    # cached_get 경유(허용 패턴) — 위반 아님.
    src = ("from app.adapters.cache.source_cache import cached_get\n"
           "def f():\n    return cached_get('vworld', 'http://x', {'pnu': 'P'})\n")
    assert scan_for_uncached_live_calls(src) == []


def test_scanner_allowlist_exempts():
    src = "import httpx\nx = httpx.get('u')\n"
    assert scan_for_uncached_live_calls(src, allowlist=("httpx.get",)) == []
