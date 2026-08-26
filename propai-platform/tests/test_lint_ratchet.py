"""eslint 경고 래칫 계약 — **초판이 뚫린 자리를 각각 잠근다.**

이 파일은 **독립 리뷰가 초판에서 찾은 결함들** 때문에 존재한다.
초판은 손으로 3케이스(없는 파일·빈 파일·`[]`)만 태우고 *"★4축 검증 완료"* 라고 적었는데,
리뷰가 **레코드 1개짜리 리포트**로 그 축을 통과시켰다.
CLAUDE.md §A-1 — *"분기·필드·상수를 만들면 테스트는 같은 커밋에. 나중은 오지 않는다."*
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "ci" / "lint_ratchet.py"


def _run(tmp: Path, report, ratchet, *extra: str) -> tuple[int, str]:
    rp, rt = tmp / "report.json", tmp / "ratchet.json"
    rp.write_text(report if isinstance(report, str) else json.dumps(report), encoding="utf-8")
    rt.write_text(ratchet if isinstance(ratchet, str) else json.dumps(ratchet), encoding="utf-8")
    p = subprocess.run(
        [sys.executable, str(_SCRIPT), str(rp), str(rt), *extra],
        capture_output=True, text=True, timeout=60,
    )
    return p.returncode, p.stdout + p.stderr


def _rec(name: str, warnings: int = 0, errors: int = 0) -> dict:
    msgs = [{"severity": 1, "ruleId": "w", "message": "경고"} for _ in range(warnings)]
    msgs += [{"severity": 2, "ruleId": "e", "message": "에러"} for _ in range(errors)]
    return {"filePath": f"/x/apps/web/{name}", "messages": msgs}


def _report(n_clean: int, **warned: int) -> list[dict]:
    """깨끗한 파일 n개 + 경고 파일들."""
    return [_rec(f"clean{i}.ts") for i in range(n_clean)] + [
        _rec(f, w) for f, w in warned.items()
    ]


def _ratchet(floor: int, **files: int) -> dict:
    return {"_meta": {"lintedFileFloor": floor}, **files}


def test_스크립트가_실재한다() -> None:
    assert _SCRIPT.is_file(), f"없음: {_SCRIPT}"


# ── ① 탐지 ───────────────────────────────────────────────────────────────────
def test_경고가_늘면_실패한다(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, _report(10, **{"a.ts": 3}), _ratchet(5, **{"a.ts": 2}))
    assert rc == 1, out
    assert "2 → 3" in out


def test_신규_파일의_경고를_잡는다(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, _report(10, **{"new.ts": 1}), _ratchet(5))
    assert rc == 1, out
    assert "신규 파일" in out


# ── ② ★F1 공허 진리 — 모집단이 줄면 "경고 0"은 통과가 아니다 ─────────────────
def test_린트가_대상을_잃으면_통과가_아니다(tmp_path: Path) -> None:
    """★초판이 뚫린 자리. 깨끗한 레코드 **1개**만 든 리포트가 exit 0 이었다."""
    rc, out = _run(tmp_path, _report(1), _ratchet(900, **{"a.ts": 2}))
    assert rc == 3, f"경고 0 인데 통과했다 — 린트가 1개만 봤다:\n{out}"
    assert "대상을 잃었을" in out


def test_경고_하나짜리_한_파일도_통과가_아니다(tmp_path: Path) -> None:
    """리뷰가 제시한 '더 나쁜 변형' — 카운트가 줄어 통과처럼 보인다."""
    rc, _ = _run(tmp_path, _report(0, **{"a.ts": 1}), _ratchet(900, **{"a.ts": 2}))
    assert rc == 3


def test_모집단이_충분하면_정상_판정한다(tmp_path: Path) -> None:
    """★대조군 — 하한이 항상 걸리면 위 두 테스트가 공허해진다."""
    rc, out = _run(tmp_path, _report(1000, **{"a.ts": 2}), _ratchet(900, **{"a.ts": 2}))
    assert rc == 0, out
    assert "통과" in out


# ── ③ ★F6 입력 이상은 위반이 아니라 무효 ─────────────────────────────────────
@pytest.mark.parametrize(
    "name,report,ratchet",
    [
        ("손상된 리포트 JSON", '{"broken": ', {"_meta": {"lintedFileFloor": 0}}),
        ("리포트가 리스트가 아님", {"nope": 1}, {"_meta": {"lintedFileFloor": 0}}),
        ("래칫이 dict 가 아님", [], "[]"),
        ("래칫 값이 문자열", [_rec("a.ts", 1)], {"_meta": {"lintedFileFloor": 0}, "a.ts": "2"}),
        ("_meta 하한이 정수가 아님", [_rec("a.ts")], {"_meta": {"lintedFileFloor": "많이"}}),
    ],
)
def test_입력_이상은_exit_3(name: str, report, ratchet, tmp_path: Path) -> None:
    rc, out = _run(tmp_path, report, ratchet)
    assert rc == 3, f"{name}: 측정 무효가 exit {rc} 로 나갔다(1이면 '위반'으로 읽힌다)\n{out}"


def test_빈_파일과_빈_리스트도_무효(tmp_path: Path) -> None:
    rp = tmp_path / "e.json"; rp.write_text("", encoding="utf-8")
    rt = tmp_path / "r.json"; rt.write_text(json.dumps(_ratchet(0)), encoding="utf-8")
    p = subprocess.run([sys.executable, str(_SCRIPT), str(rp), str(rt)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 3, p.stdout


# ── ④ ★F5 rename 위양성 — 원인을 단정하지 않는다 ────────────────────────────
def test_이름만_바뀌면_원인을_단정하지_않는다(tmp_path: Path) -> None:
    rc, out = _run(
        tmp_path,
        _report(1000, **{"new_name.ts": 8}),
        _ratchet(900, **{"old_name.ts": 8}),
    )
    assert rc == 1, out  # 여전히 막는다(사람이 봐야 한다)
    assert "이동/이름변경일 수 있다" in out, out
    assert "이 PR 이 새로 만든 것이다" not in out


def test_진짜_증가는_단정한다(tmp_path: Path) -> None:
    """★대조군 — 위 완화가 항상 걸리면 진짜 증가의 진단이 무뎌진다."""
    rc, out = _run(tmp_path, _report(1000, **{"a.ts": 5}), _ratchet(900, **{"a.ts": 2}))
    assert rc == 1
    assert "이 PR 이 새로 만든 것이다" in out


# ── ⑤ ★F3 헤드룸을 조용히 두지 않는다 ───────────────────────────────────────
def test_줄었으면_부채_총량을_말한다(tmp_path: Path) -> None:
    rc, out = _run(tmp_path, _report(1000, **{"a.ts": 1}), _ratchet(900, **{"a.ts": 10}))
    assert rc == 0, out
    assert "헤드룸 9건" in out, out


# ── ⑥ 갱신 모드가 _meta 를 남기고, 그 _meta 가 비교를 오염시키지 않는다 ──────
def test_update_는_meta_를_기록하고_비교에서_제외한다(tmp_path: Path) -> None:
    rp = tmp_path / "r.json"
    rp.write_text(json.dumps(_report(1000, **{"a.ts": 2})), encoding="utf-8")
    rt = tmp_path / "rat.json"
    up = subprocess.run([sys.executable, str(_SCRIPT), str(rp), str(rt), "--update"],
                        capture_output=True, text=True, timeout=60)
    assert up.returncode == 0, up.stdout
    data = json.loads(rt.read_text(encoding="utf-8"))
    assert data["_meta"]["lintedFileFloor"] > 0
    # 같은 리포트로 다시 재면 통과해야 하고, `_meta` 가 "줄어든 파일"로 잡히면 안 된다.
    ck = subprocess.run([sys.executable, str(_SCRIPT), str(rp), str(rt)],
                        capture_output=True, text=True, timeout=60)
    assert ck.returncode == 0, ck.stdout
    assert "_meta" not in ck.stdout


# ── ⑦ 배선 — CI 가 실제로 이 스크립트를 부르는가 ────────────────────────────
def test_ci_가_래칫을_호출한다() -> None:
    """★배선하지 않으면 이 스크립트는 소비처 0 인 장식이다."""
    yml = (_REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    code = "\n".join(l for l in yml.splitlines() if not l.lstrip().startswith("#"))
    assert "scripts/ci/lint_ratchet.py" in code, "ci.yml 실행 라인에서 래칫을 부르지 않는다"
    assert "--format json -o" in code, "Lint 스텝이 JSON 리포트를 남기지 않는다"
    # 대조군: 이 조회기가 살아 있는가.
    assert "pnpm type-check" in code, "조회기 사망 — ci.yml 을 제대로 읽지 못했다"


def test_실제_래칫_파일이_계약을_지킨다() -> None:
    p = _REPO / "propai-platform" / "apps" / "web" / "lint-ratchet.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "_meta" in data, "모집단 하한이 없다 — F1 이 다시 열린다"
    assert isinstance(data["_meta"]["lintedFileFloor"], int)
    assert data["_meta"]["lintedFileFloor"] > 500, "하한이 너무 낮으면 가드가 무의미하다"
    assert all(isinstance(v, int) for k, v in data.items() if k != "_meta")
