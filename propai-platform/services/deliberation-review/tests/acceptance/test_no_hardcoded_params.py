"""AT-9 — 법정/도메인 수치 하드코딩 부재(INV-3). app 소스 전체 정적 스캔."""
import pathlib

from tools.static_scan import scan_for_numeric_legal_constants

_APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "apps" / "api" / "app"


def test_no_hardcoded_legal_params():
    offenders: dict[str, list[str]] = {}
    for py in _APP_DIR.rglob("*.py"):
        hits = scan_for_numeric_legal_constants(py.read_text(encoding="utf-8"))
        if hits:
            offenders[str(py.relative_to(_APP_DIR))] = hits
    assert offenders == {}, f"hardcoded legal params found: {offenders}"
