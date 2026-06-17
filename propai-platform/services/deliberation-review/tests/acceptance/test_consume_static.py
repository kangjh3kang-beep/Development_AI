"""R2 DoD — 소비측 분석경로 정적검사: 라이브호출/인라인 LLM 0(INV-13).

consume/ + services/verify/ 소스에 네트워크/LLM 직접 호출 토큰이 존재하면 실패.
(라이브 정합은 tasks/ 주기잡으로 분리 — 스캔 대상 아님.)
"""
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "app"
_SCAN_DIRS = (_ROOT / "consume", _ROOT / "services" / "verify")

_FORBIDDEN = (
    "LiveNetwork",
    "requests.",
    "httpx",
    "urllib",
    "socket.",
    "openai",
    "anthropic",
    "aiohttp",
)


def test_consume_path_has_no_live_calls_or_inline_llm():
    offenders: dict[str, list[str]] = {}
    for d in _SCAN_DIRS:
        for py in d.rglob("*.py"):
            src = py.read_text(encoding="utf-8")
            hits = [tok for tok in _FORBIDDEN if tok in src]
            if hits:
                offenders[str(py.relative_to(_ROOT))] = hits
    assert offenders == {}, f"live-call/LLM tokens in consume path: {offenders}"
