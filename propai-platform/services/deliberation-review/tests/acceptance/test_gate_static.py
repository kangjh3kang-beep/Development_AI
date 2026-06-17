"""AT-9 — 게이팅/판정 임계 파라미터화(하드코딩 부재). judge/gate/mapping 소스 정적 스캔."""
import pathlib

from tools.static_scan import scan_for_numeric_legal_constants

_ROOT = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "app" / "services"
_SCAN_DIRS = (_ROOT / "judge", _ROOT / "gate", _ROOT / "mapping")


def test_thresholds_parameterized():
    offenders: dict[str, list[str]] = {}
    for d in _SCAN_DIRS:
        for py in d.rglob("*.py"):
            hits = scan_for_numeric_legal_constants(py.read_text(encoding="utf-8"))
            if hits:
                offenders[py.name] = hits
    assert offenders == {}, f"hardcoded thresholds in gate/judge: {offenders}"
