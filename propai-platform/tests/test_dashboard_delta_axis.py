"""계기판 델타 축 — **거짓 초록(없는 sha)** 봉합과 「주석만」의 관측이상 강등을 잠근다.

★왜 이 파일이 있나 (2026-09-09 · sid=7af9eaa2)

  ① **거짓 초록**: 배포된 sha 가 로컬에 없으면 `git diff` 가 fatal 이고 `2>/dev/null` 이
     그것을 삼켜 grep 입력이 0줄 → **`0`** 이 나오고 계기판이 **"✅ 수렴"** 이라 찍었다.
     실측: `deadbeef..origin/main` → 0 · 대조군 유효 sha → 2.
     **「배포 안 됨」이 「수렴」으로 뒤집힌다** — 위양성보다 나쁘다.

  ② **위양성**: 주석·독스트링만 바뀐 2파일에 `exit 2`(★★위반)를 냈다. 상시 빨강은 곧 무시되고
     그때 진짜 위반이 묻힌다(#868 이 이미 치른 값). 그렇다고 **0(이상 없음)** 으로 내리지 않는다 —
     컨테이너 소스는 여전히 git 과 갈려 있고 이 저장소는 그 소스를 표식으로 grep 한다.
     ⇒ 있는 칸을 쓴다: **관측 이상(4)**.

★락의 형태 — **파티션형**(형제 `test_dashboard_observation_exit_code.py` 와 같은 축).
  다섯 모집단이 **서로 다른 답**을 내야 한다. 하나라도 뭉치면 이 파일이 빨개진다.

★픽스처는 **리터럴 소스 텍스트**로 핀한다 — 프로덕션 정규식·함수에서 파생시키지 않는다
  («상수를 자기 자신과 비교하는 락» 방지). 그리고 **실물 함수를 태운다**(사본 금지 · #905).
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "propai-platform" / "scripts" / "monitor" / "integrator_dashboard.sh"

# ── 리터럴 픽스처 (프로덕션에서 파생하지 않는다) ────────────────────────────
_BASE_PY = '''\
"""옛 설명."""
# 옛 주석
def f(x):
    return x + 1
'''
_COMMENT_ONLY_PY = '''\
"""새 설명 — 뜻이 완전히 다르다."""
# 새 주석 · 여러 줄로
#   늘렸다
def f(x):
    return x + 1
'''
_CODE_CHANGED_PY = '''\
"""옛 설명."""
# 옛 주석
def f(x):
    return x + 2
'''
_OTHER_TS = "export const a = 1;\n"


def _run(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout


def _mk_repo(tmp: Path, head_files: dict[str, str], base_files: dict[str, str]) -> str:
    """base 커밋과 `origin/main` 브랜치를 가진 합성 저장소를 만든다 → base sha 반환."""
    _run(["git", "init", "-q", "-b", "main", str(tmp)], REPO)
    _run(["git", "config", "user.email", "t@t"], tmp)
    _run(["git", "config", "user.name", "t"], tmp)
    for rel, body in base_files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    _run(["git", "add", "-A"], tmp)
    _run(["git", "commit", "-qm", "base"], tmp)
    base = _run(["git", "rev-parse", "HEAD"], tmp).strip()
    for rel, body in head_files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    _run(["git", "add", "-A"], tmp)
    _run(["git", "commit", "-qm", "head"], tmp)
    # 프로덕션 함수는 head 를 `origin/main` 으로 부른다 — 같은 이름의 브랜치를 만든다
    _run(["git", "branch", "origin/main"], tmp)
    return base


def _call(fn: str, cwd: Path, *args: str) -> str:
    """★실물 함수를 태운다 — 파이프라인을 여기 복사하지 않는다."""
    quoted = " ".join(f"'{a}'" for a in args)
    out = subprocess.run(
        ["bash", "-c", f". '{SCRIPT}' --verdict-lib; {fn} {quoted}"],
        cwd=cwd, capture_output=True, text=True,
    )
    return out.stdout.strip()


@pytest.fixture()
def repo_comment_only(tmp_path: Path) -> tuple[Path, str]:
    d = tmp_path / "co"
    d.mkdir()
    base = _mk_repo(d, {"pkg/m.py": _COMMENT_ONLY_PY}, {"pkg/m.py": _BASE_PY})
    return d, base


@pytest.fixture()
def repo_code_changed(tmp_path: Path) -> tuple[Path, str]:
    d = tmp_path / "cc"
    d.mkdir()
    base = _mk_repo(d, {"pkg/m.py": _CODE_CHANGED_PY}, {"pkg/m.py": _BASE_PY})
    return d, base


# ── A. 없는 base 는 「모름」이지 「수렴」이 아니다 ─────────────────────────
def test_missing_base_is_unknown_not_zero(repo_comment_only):
    d, _ = repo_comment_only
    assert _call("runtime_delta", d, "deadbeefdeadbeef", "pkg/") == "?"


def test_valid_base_still_counts(repo_comment_only):
    """★대조군 — A 가 「항상 ?」로 만점을 받지 못하게 한다."""
    d, base = repo_comment_only
    assert _call("runtime_delta", d, base, "pkg/") == "1"


# ── B~D. 「주석만」과 「코드 변경」이 **서로 다른 답**을 내야 한다 ──────────
def test_comment_only_is_yes(repo_comment_only):
    d, base = repo_comment_only
    assert _call("comment_only_delta", d, base, "pkg/") == "yes"


def test_code_change_is_no(repo_code_changed):
    d, base = repo_code_changed
    assert _call("comment_only_delta", d, base, "pkg/") == "no"


def test_two_populations_actually_differ(repo_comment_only, repo_code_changed):
    """★공허 진리 가드 — 두 픽스처가 같은 답을 내면 이 락은 아무것도 안 가른다."""
    a = _call("comment_only_delta", repo_comment_only[0], repo_comment_only[1], "pkg/")
    b = _call("comment_only_delta", repo_code_changed[0], repo_code_changed[1], "pkg/")
    assert a != b, f"두 모집단이 같은 답({a})을 냈다 — 픽스처가 판별력이 없다"


# ── E. 판정 불가는 **강등하지 않는다**(안전한 쪽) ─────────────────────────
def test_non_python_change_is_unknown(tmp_path: Path):
    d = tmp_path / "ts"
    d.mkdir()
    base = _mk_repo(d, {"pkg/m.py": _BASE_PY, "pkg/a.ts": "export const a = 2;\n"},
                    {"pkg/m.py": _BASE_PY, "pkg/a.ts": _OTHER_TS})
    assert _call("comment_only_delta", d, base, "pkg/") == "unknown"


def test_non_python_that_happens_to_parse_is_still_unknown(tmp_path: Path):
    """★확장자 검사가 **판별력을 갖는** 픽스처.

    앞 케이스(`.ts`)는 AST 파싱이 어차피 실패해 `unknown` 이 나온다 — 즉 확장자 검사를
    **지워도 같은 답**이라 그 분기를 잠그지 못한다(손 변이로 SURVIVED 실측, 2026-09-09).

    `requirements.txt` 는 **파이썬으로 파싱된다**(`foo==1` 은 유효한 식이고 `#` 는 주석이다).
    확장자 검사가 없으면 «주석만 바뀐 requirements» 가 `yes` 로 분류돼 **강등**되는데,
    의존성 파일은 **재빌드가 필요하다**. 그래서 이 픽스처가 그 분기를 실제로 가른다.
    """
    d = tmp_path / "req"
    d.mkdir()
    base = _mk_repo(d,
                    {"pkg/requirements.txt": "# 새 주석\nfoo==1\n"},
                    {"pkg/requirements.txt": "# 옛 주석\nfoo==1\n"})
    assert _call("comment_only_delta", d, base, "pkg/") == "unknown"


def test_added_file_is_unknown(tmp_path: Path):
    """추가·삭제·rename 은 줄이 0이어도 배포가 필요할 수 있다 → 강등 금지."""
    d = tmp_path / "add"
    d.mkdir()
    base = _mk_repo(d, {"pkg/m.py": _BASE_PY, "pkg/new.py": "x = 1\n"}, {"pkg/m.py": _BASE_PY})
    assert _call("comment_only_delta", d, base, "pkg/") == "unknown"


def test_missing_base_is_unknown_for_classifier(repo_comment_only):
    d, _ = repo_comment_only
    assert _call("comment_only_delta", d, "deadbeefdeadbeef", "pkg/") == "unknown"


# ── ★판정 자체를 태운다(파티션) — 「존재 락」이 아니라 「행위 락」 ────────
#   ⑤-2 블록 안에 인라인으로 두면 보드·SSH 가 살아야 태울 수 있어 아무도 안 태운다.
#   그래서 `delta_verdict` 를 순수 함수로 꺼냈고, 여기서 **다섯 모집단**을 직접 태운다.
@pytest.mark.parametrize(
    ("wd", "ad", "cd", "cow", "coa", "expected"),
    [
        ("0", "0", "0", "unknown", "unknown", "converged"),   # 수렴
        ("0", "2", "0", "unknown", "yes", "obs"),             # api 주석만 → 강등
        ("2", "0", "0", "yes", "unknown", "obs"),             # web 주석만 → 강등
        ("0", "2", "0", "unknown", "no", "viol"),             # 코드 변경 → 위반
        ("0", "2", "0", "unknown", "unknown", "viol"),        # 판정 불가 → 강등 금지
        ("0", "0", "1", "yes", "yes", "viol"),                # 컨테이너 입력 → 재빌드 필요
    ],
)
def test_delta_verdict_partition(tmp_path: Path, wd, ad, cd, cow, coa, expected):
    assert _call("delta_verdict", tmp_path, wd, ad, cd, cow, coa) == expected


def test_verdict_values_are_not_all_the_same(tmp_path: Path):
    """★공허 진리 가드 — 「항상 viol」·「항상 obs」가 만점을 받지 못하게 한다."""
    got = {
        _call("delta_verdict", tmp_path, "0", "0", "0", "unknown", "unknown"),
        _call("delta_verdict", tmp_path, "0", "2", "0", "unknown", "yes"),
        _call("delta_verdict", tmp_path, "0", "2", "0", "unknown", "no"),
    }
    assert len(got) == 3, f"세 모집단이 {got} 로 뭉쳤다 — 판정이 입력을 안 읽는다"


# ── 배선 — 판정 지점이 실제로 이 함수를 쓰는가 ────────────────────────────
def test_judgment_point_consumes_the_classifier():
    """★함수만 고치고 판정 지점(⑤-2)을 안 고치면 처방은 아무것도 하지 않는다.

    ⑤-2 블록이 `comment_only_delta` 를 **호출**하고 그 결과로 `OBS` 를 세우는지 본다.
    (이름이 있는 것과 그것이 불리는 것은 다르다 — 호출 형태로 좁혀서 본다.)
    """
    src = SCRIPT.read_text(encoding="utf-8")
    head = src.index("⑤-2")
    block = src[head:]
    assert "CO_API=$(comment_only_delta " in block, "판정 지점이 분류기를 호출하지 않는다"
    assert "$(delta_verdict " in block, "판정 지점이 판정 함수를 호출하지 않는다(인라인 복제 의심)"
    assert "OBS=1" in block, "판정 지점이 관측이상으로 강등하지 않는다"
    # ★음성 축 — 코드가 바뀐 경우의 위반 판정이 사라지지 않았는가
    assert "VIOL=1" in block, "코드 변경 시의 위반 판정이 사라졌다"


# ── ★부채: web(TS) 축은 이번에 안 잠근다 — 초록 안에 보이게 남긴다 ────────
@pytest.mark.xfail(reason="★부채 — TS/TSX 의 「주석만」 판정 미구현(AST 도구 없음). "
                          "web 축의 같은 상황은 여전히 위양성이다.", strict=True)
def test_typescript_comment_only_is_classified():
    d = Path("/nonexistent")
    assert _call("comment_only_delta", d, "x", "pkg/") == "yes"
