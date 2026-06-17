"""AT-9 — 법정/도메인 수치 하드코딩 부재(INV-3). app 소스 전체 정적 스캔."""
import pathlib

from tools.static_scan import scan_for_numeric_legal_constants

_APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "app"
# 법정상수 아닌 정당한 예외(부동소수 비교 오차 등) — AST 스캐너가 지수표기까지 잡으므로 명시 제외.
_ALLOW = ("_FLOAT_TOL",)


def test_no_hardcoded_legal_params():
    offenders: dict[str, list[str]] = {}
    for py in _APP_DIR.rglob("*.py"):
        hits = scan_for_numeric_legal_constants(py.read_text(encoding="utf-8"), allowlist=_ALLOW)
        if hits:
            offenders[str(py.relative_to(_APP_DIR))] = hits
    assert offenders == {}, f"hardcoded legal params found: {offenders}"
