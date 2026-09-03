"""★`scripts/coord.sh` 의 요약이 **실제로 요약하는지** 잠근다. (3판)

【왜 생겼나】`CLAUDE.md` 와 `coordination/PROTOCOL.md` 는 **인계 공유를 `coord.sh note` 로 하라**고
지시하는데, 종전 `status` 꼬리 절은 `\\[(CLAIM|RELEASE)\\]` 만 grep 해 **`[NOTE]` 가 한 건도 안
나왔다.** 보드에서 NOTE 는 가장 많은 종류다. 재측정:
`grep -cE '^- \\[NOTE\\]' "$BOARD"` vs `'^- \\[(CLAIM|RELEASE)\\]'`.

【★3판이다 — 앞선 두 판이 독립 적대 리뷰에서 무너졌다】
    1판: 작성자 변이 5/5 CAUGHT  → 리뷰어 변이 **10/10 SURVIVED**
    2판: 리뷰어 변이 11/12 CAUGHT → 다른 리뷰어 변이 **15/21 SURVIVED**

★**2판이 실패한 이유가 이 파일의 설계 원리다.** 2판은 «표지 하나 → 표지 전부» 로 일반화했는데,
모집단은 **한 층 위**였다: 읽는 자리가 **셋**(`summary`-CR · `summary`-NOTE · `status`-NOTE)인데
각 축을 **한 칸에서만** 잠갔다. 그래서 같은 결함 클래스가 **옆 칸으로 옮겨가** 5종이 생존했다.
→ **칸을 열거하지 않고 파생**시키고(`_CELLS`) 모든 축을 그 위에 `parametrize` 한다.

【이 파일이 잠그는 축】
  ①NOTE 가시성 ②본문 미덤프 ③제목 정직성 ④절단 표기 ⑤`status` 후방호환(무절단)
  ⑥환경변수 배선 ⑦순서(최신) ⑧행두 앵커 — ⑥⑦⑧은 **세 칸 전부**
  ⑨절단이 **문자 단위**(바이트 절단 회귀를 잡는다) ⑩`SUMMARY_N` 게이트(파티션)
  ⑪조회기 사망 vs 진짜 0건 ⑫유령 보드 ⑬★**생산자↔소비자 왕복**(`note`/`claim` 이 쓴 것을 읽는가)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scan_guard import assert_absent  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "coord.sh"
_LIMIT = 240   # truncate_chars 의 문자 상한 — 코드와 같은 값을 여기서 못 박는다

# ★**읽는 자리 = 파생된 칸.** 손으로 열거하면 그 목록이 곧 상한이 된다(2판이 그래서 뚫렸다).
#   `status`-CR 은 **의도적으로 무절단·무앵커**(후방호환)라 ⑥⑦⑧의 대상이 아니다 — ⑤가 그것을 잠근다.
_CELLS = [("summary", "cr"), ("summary", "note"), ("status", "note")]

_NOTE_CANARY = "노트카나리_zzz_must_surface"
_CONT_CANARY = "이어붙은줄카나리_zzz_note_body"
_BODY_CANARY = "무관본문카나리_zzz_never_surface"
_LONG_KO = "가나다라마바사아자차" * 40


def _board(tmp_path: Path, *, notes: int = 1, pairs: int = 0, long_note: bool = False,
           pollute: str | None = None) -> Path:
    d = tmp_path / "coordination"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["# 합성 보드", "", _BODY_CANARY]
    for i in range(pairs):
        lines.append(f"- [CLAIM] 영역{i} <- br (2026-09-03 09:{i % 60:02d})")
        lines.append(f"- [RELEASE] 영역{i} <- br (2026-09-03 09:{i % 60:02d})")
    lines.append("- [CLAIM] 살아있는영역 <- br (2026-09-03 10:00)")
    for i in range(1, notes + 1):
        lines.append(f"- [NOTE] 2026-09-03 10:{i % 60:02d} br: 노트{i:03d}")
    if long_note:
        lines.append(f"- [NOTE] 2026-09-03 11:00 br: {_LONG_KO}")
    lines.append(f"- [NOTE] 2026-09-03 11:59 br: {_NOTE_CANARY}")
    lines.append(_CONT_CANARY)
    if pollute:
        # ★오염 줄은 **NOTE 에 인접하지 않게** 맨 뒤 빈 줄 뒤에 둔다 — 「이어지는 줄」 부채를
        #   갚는 구현이 이 줄을 집지 않도록(2판은 인접해 있어 상환 경로가 이 락과 충돌했다).
        lines += ["", pollute]
    p = d / "BOARD.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _run(cmd: str, board: Path, *, env_extra: dict | None = None, expect_rc: int | None = 0,
         path_prefix: str | None = None):
    env = {"PATH": (f"{path_prefix}:" if path_prefix else "") + "/usr/bin:/bin:/usr/local/bin",
           "COORD_DIR": str(board.parent), "HOME": str(Path.home()), "LANG": "en_US.UTF-8"}
    env.update(env_extra or {})
    p = subprocess.run(["bash", str(_SCRIPT), cmd], cwd=str(_REPO), env=env,
                       capture_output=True, timeout=120)
    if expect_rc is not None:
        assert p.returncode == expect_rc, (
            f"coord.sh {cmd} rc={p.returncode}(기대 {expect_rc})\n{p.stderr.decode(errors='replace')[:600]}")
    return p


def _out(cmd: str, board: Path, **kw) -> str:
    return _run(cmd, board, **kw).stdout.decode("utf-8")


_HEAD = {("summary", "cr"): "=== CLAIM/RELEASE 로그",
         ("summary", "note"): "=== 최근 NOTE",
         ("status", "cr"): "=== 미해제 CLAIM",
         ("status", "note"): "=== 최근 NOTE"}


def _section(out: str, cmd: str, section: str) -> str:
    """지정 칸만 잘라 낸다.

    ★`rindex` 를 쓴다 — `status` 는 보드 **전문을 먼저 덤프**하므로, 절 제목과 같은 문자열이
      본문에 있으면 `index` 는 **본문에서** 자른다. 이 저장소가 실제로 그 함정을 밟았다
      (동료가 `sed -n '/제목/,$p'` 로 잘라 엉뚱한 구간을 읽고 건수를 틀리게 보고했다).
    """
    start = out.rindex(_HEAD[(cmd, section)])
    if section == "cr":
        return out[start:out.rindex(_HEAD[(cmd, "note")])]
    return out[start:]


def _note_entries(seg: str) -> list[str]:
    return re.findall(r"^\s*\d+:- \[NOTE\].*$", seg, re.MULTILINE)


# ───────────── 공허 진리 방지 ─────────────

def test_fixture_actually_contains_every_canary(tmp_path: Path) -> None:
    t = _board(tmp_path, long_note=True).read_text(encoding="utf-8")
    for c in (_NOTE_CANARY, _CONT_CANARY, _BODY_CANARY, _LONG_KO):
        assert c in t, f"픽스처에 {c[:18]} 가 없다 — 그 축의 단언이 공허해진다"


# ───────────── ① NOTE 가시성 (원결함) ─────────────

@pytest.mark.parametrize("cmd", ["summary", "status"])
def test_note_is_visible(cmd: str, tmp_path: Path) -> None:
    assert _NOTE_CANARY in _section(_out(cmd, _board(tmp_path)), cmd, "note"), \
        "NOTE 가 요약 절에 없다 — 종전 결함 그대로다"


# ───────────── ② 본문 미덤프 · ⑤ status 후방호환 ─────────────

def test_summary_does_not_dump_board_body(tmp_path: Path) -> None:
    assert_absent(_out("summary", _board(tmp_path)),
                  pattern=_BODY_CANARY, positive_control=_NOTE_CANARY,
                  reason=("summary 가 보드 본문을 덤프했다. 본문에는 절 제목이 인용돼 있어 하류의 "
                          "절 자르기가 엉뚱한 구간을 읽는다."),
                  where="coord.sh summary")


def test_status_section_is_not_truncated(tmp_path: Path) -> None:
    """⑤`status` 는 **전량 무절단**이다 — 인계서들이 *"자르지 마라"* 를 명시한다."""
    b = _board(tmp_path, pairs=30)
    out = _out("status", b)
    want = sum(1 for ln in b.read_text(encoding="utf-8").splitlines()
               if re.search(r"\[(CLAIM|RELEASE)\]", ln))
    assert want > 12, f"★픽스처 CLAIM/RELEASE 가 {want}건 — 절단 축이 공허해진다"
    got = len(re.findall(r"\[(?:CLAIM|RELEASE)\]", _section(out, "status", "cr")))
    assert got == want, f"★status 가 종전 절을 절단했다({want} → {got}) — 후방호환 위반"
    assert _BODY_CANARY in out, "★status 가 보드 전문을 안 뱉는다 — 기존 소비자 회귀"


# ───────────── ③ 제목 정직성 ─────────────

def test_summary_never_claims_unreleased(tmp_path: Path) -> None:
    """짝짓기를 안 하면서 「미해제」라고 말하지 않는다(`summary` 출력 **전체**)."""
    assert_absent(_out("summary", _board(tmp_path)),
                  pattern="미해제", positive_control="CLAIM/RELEASE 로그",
                  reason=("요약이 「미해제」를 표방한다. 짝짓기는 2026-08-27 에 자기 양성 대조군에 "
                          "실패했고 파생 수치가 철회됐다. 계산하지 않는 것을 계산한다고 말하지 마라."),
                  where="coord.sh summary 전체")


# ───────────── ④ 절단 표기 (두 절 모두) ─────────────

def test_both_truncating_sections_disclose_how_to_read_the_rest(tmp_path: Path) -> None:
    out = _out("summary", _board(tmp_path, notes=20, pairs=20))
    for section in ("cr", "note"):
        seg = _section(out, "summary", section)
        assert "전문:" in seg, f"★{section} 절이 절단해 놓고 전문 조회 방법을 안 알려 준다"


# ───────────── ⑥⑦⑧ 세 칸 전부 (★2판이 한 칸씩만 잠갔다) ─────────────

@pytest.mark.parametrize("cmd,section", _CELLS)
def test_env_knob_is_wired_in_every_cell(cmd: str, section: str, tmp_path: Path) -> None:
    """⑥`COORD_SUMMARY_N` 배선. ★두 값이 **다른 결과**를 내야 한다."""
    b = _board(tmp_path, notes=20, pairs=20)

    def n_shown(n: str) -> int:
        seg = _section(_out(cmd, b, env_extra={"COORD_SUMMARY_N": n}), cmd, section)
        pat = r"^\s*\d+:- \[NOTE\]" if section == "note" else r"^\s*\d+:- \[(?:CLAIM|RELEASE)\]"
        return len(re.findall(pat, seg, re.MULTILINE))

    few, many = n_shown("3"), n_shown("15")
    assert few == 3 and many == 15, f"★{cmd}-{section} 에 환경변수가 배선되지 않았다(3→{few} · 15→{many})"


@pytest.mark.parametrize("cmd,section", _CELLS)
def test_newest_not_oldest_in_every_cell(cmd: str, section: str, tmp_path: Path) -> None:
    """⑦순서 — `tail`→`head` 반전이 **어느 칸에서도** 통과하지 않는다.

    ★두 모집단: **꼬리는 나오고 머리는 안 나온다.** (2판은 `summary`-NOTE 한 칸만 봤다)
    """
    b = _board(tmp_path, notes=20, pairs=20)
    seg = _section(_out(cmd, b), cmd, section)
    tag = r"노트(\d{3})" if section == "note" else r"영역(\d+)"
    shown = re.findall(tag, seg)
    assert shown, f"★{cmd}-{section} 에 항목이 하나도 없다 — 순서 단언이 공허해진다"
    nums = sorted(int(x) for x in shown)
    assert nums[0] > 1, f"★{cmd}-{section} 에 가장 오래된 항목이 나온다 — head/tail 반전: {shown[:5]}"


@pytest.mark.parametrize("cmd,section", _CELLS)
def test_anchors_reject_mid_line_matches_in_every_cell(cmd: str, section: str, tmp_path: Path) -> None:
    """⑧행두 앵커 — 본문이 표지를 **인용**하면 오염된다. (2판은 `status`-NOTE 를 안 봤다)"""
    marker = "NOTE" if section == "note" else "CLAIM"
    b = _board(tmp_path, pollute=f"규약대로 - [{marker}] 표기로 남기라는 인용줄 오염카나리_zzz")
    assert_absent(_section(_out(cmd, b), cmd, section),
                  pattern="오염카나리_zzz", positive_control="↳" if cmd == "summary" else r"\[",
                  reason=f"행두 앵커가 없어 본문 중간에 인용된 [{marker}] 표지까지 집었다.",
                  where=f"coord.sh {cmd} · {section} 절")


# ───────────── ⑨ 절단이 문자 단위인가 (★바이트 절단 회귀) ─────────────

def test_truncation_is_by_characters_not_bytes(tmp_path: Path) -> None:
    """★2판은 **디코드 가능**만 단언했다. 그래서 `ln.encode()[:240].decode(errors="ignore")` 로
    되돌리는 변이가 **생존**했다 — 파손은 없지만 240자를 약속하고 **80자**를 준다.
    → **문자 수 자체**를 단언한다. 이 한 단언이 양방향(과절단·과소절단)을 같이 닫는다.
    """
    raw = _run("summary", _board(tmp_path, long_note=True)).stdout
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        pytest.fail(f"★절단이 UTF-8 을 깼다 — 바이트 단위로 자르고 있다: {e}")
    hit = [ln for ln in text.splitlines() if "…[잘림]" in ln]
    assert hit, "★잘라 놓고 표식이 없다 — 잘렸는지조차 알 수 없다"
    # ★상한은 **줄 전체**에 걸린다(payload 가 아니다 — 첫 판 단언이 그것을 헷갈려 틀렸다).
    body = hit[0].replace(" …[잘림]", "")
    assert len(body) == _LIMIT, (
        f"★절단 길이가 {len(body)}자다(기대 {_LIMIT}). 바이트로 자르면 한글은 약 {_LIMIT // 3}자가 된다")
    assert len(body.encode("utf-8")) > _LIMIT, "★픽스처가 바이트 상한을 넘지 않는다 — 축이 공허하다"


# ───────────── ⑩ SUMMARY_N 게이트 (파티션) ─────────────

@pytest.mark.parametrize("value,ok", [
    ("7", True), ("12", True), ("999", True),
    ("0", False), ("00", False), ("000", False), ("007", False),
    ("abc", False), ("+5", False), ("-3", False), ("1e3", False), ("1000", False),
])
def test_summary_n_gate_is_a_shape_not_a_blacklist(value: str, ok: bool, tmp_path: Path) -> None:
    """⑩★열거형이던 첫 판은 `00` 이 새어 **rc=141 · stdout·stderr 둘 다 빈** 무성 사망을 냈다.

    ★**파티션으로 잠근다** — 거부만 단언하면 «전부 거부»가 만점이다.
    """
    b = _board(tmp_path, notes=3)
    p = _run("summary", b, env_extra={"COORD_SUMMARY_N": value}, expect_rc=None)
    if ok:
        assert p.returncode == 0, f"★정상값 {value!r} 을 거부했다(위양성) rc={p.returncode}"
        assert _NOTE_CANARY in p.stdout.decode("utf-8"), f"★{value!r} 에서 출력이 비었다"
    else:
        assert p.returncode == 2, f"★{value!r} 을 거부하지 않았다 rc={p.returncode}(무성 사망 위험)"
        assert b"" in p.stderr and "판정 거부" in p.stderr.decode("utf-8", "replace"), \
            f"★{value!r} 거부 사유가 stderr 에 없다"


# ───────────── ⑪ 조회기 사망 vs 진짜 0건 ─────────────

def test_dead_scanner_branch_is_reachable_and_refuses(tmp_path: Path) -> None:
    """⑪★첫 판은 이 분기를 *"재현 수단이 없다"* 고 **주석으로** 넘겼다 — **거짓이었다.**

    적대 리뷰가 `PATH` 앞에 `exit 2` 짜리 `grep` 스텁을 놓아 3줄로 재현했다.
    ★*"재현할 수 없다"* 도 측정 대상이다 — 못 한다고 적으면 아무도 다시 재지 않는다.
    """
    stub = tmp_path / "bin"; stub.mkdir()
    (stub / "grep").write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
    os.chmod(stub / "grep", 0o755)
    p = _run("summary", _board(tmp_path, notes=3), expect_rc=None, path_prefix=str(stub))
    assert p.returncode == 3, f"★조회기가 죽었는데 rc={p.returncode} — 「0건」과 뭉갰다"
    assert "없음" not in p.stdout.decode("utf-8", "replace"), \
        "★조회기 사망을 「실제로 0건」으로 보고했다(위음성 · 이 저장소가 ScannerDeadError 를 만든 이유)"


def test_true_zero_is_distinguishable(tmp_path: Path) -> None:
    """★반대편 — **진짜 0건**은 정상 종료하고 그렇게 말한다(파티션)."""
    d = tmp_path / "coordination"; d.mkdir(parents=True)
    (d / "BOARD.md").write_text("# 빈 보드\n", encoding="utf-8")
    assert "없음" in _out("summary", d / "BOARD.md")


# ───────────── ⑫ 유령 보드 ─────────────

@pytest.mark.parametrize("cmd", ["summary", "status"])
def test_explicit_coord_dir_typo_is_refused_not_reported_empty(cmd: str, tmp_path: Path) -> None:
    """⑫★2판은 `status` 에서 이것이 **뚫려 있었다**(`ensure_board` 호출).

    유령 보드를 만들고 rc=0 으로 *"조회기는 생존했고 실제로 0건이다"* 라고 **단정**했다 —
    CLAUDE.md 가 세션 시작에 시키는 명령이라 그 위음성의 값이 가장 크다.
    """
    ghost = tmp_path / "nope" / "coordination" / "BOARD.md"
    p = _run(cmd, ghost, expect_rc=None)
    assert p.returncode != 0, f"★{cmd}: 보드가 없는데 성공했다"
    assert not ghost.exists(), f"★{cmd}: 조회 명령이 유령 보드를 만들었다"
    assert "없음" not in p.stdout.decode("utf-8", "replace"), \
        f"★{cmd}: 대상 부재를 「0건」으로 보고했다"


# ───────────── ⑬ ★생산자↔소비자 왕복 (2판에 전혀 없던 축) ─────────────

def test_round_trip_writer_to_reader(tmp_path: Path) -> None:
    """⑬★**이 PR 의 전제 자체**를 잠근다 — 읽는 앵커가 **쓰는 쪽 형식과 맞는가.**

    2판까지는 모든 픽스처를 **손으로** 만들어, `printf -- '- [NOTE] …'` 를 `'* NOTE …'` 로 바꾸는
    변이가 **생존**했다. 즉 «`^- \\[NOTE\\]` 가 writer 의 출력과 일치한다»는 전제가 무잠금이었다.
    ★그리고 계획서가 *"`claim` 이 세션 이름을 함께 적어야 한다"* 를 **예정된 후속**으로 적어 뒀다 —
      이 리더가 의존하는 그 형식을 앞으로 **고칠 계획이 이미 있다.**
    """
    d = tmp_path / "coordination"; d.mkdir(parents=True)
    board = d / "BOARD.md"
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "COORD_DIR": str(d),
           "HOME": str(Path.home()), "LANG": "en_US.UTF-8"}
    for args in (["note", "왕복카나리_note_zzz"],
                 ["claim", "왕복영역_zzz"],
                 ["release", "왕복영역_zzz"]):
        r = subprocess.run(["bash", str(_SCRIPT), *args], cwd=str(_REPO), env=env,
                           capture_output=True, timeout=60)
        assert r.returncode == 0, f"★writer 실패: {args} — {r.stderr.decode(errors='replace')[:300]}"
    assert board.exists(), "★writer 가 보드를 안 만들었다"
    out = _out("summary", board)
    assert "왕복카나리_note_zzz" in _section(out, "summary", "note"), \
        "★`coord.sh note` 가 쓴 줄을 `summary` 의 NOTE 절이 못 읽는다 — 생산자↔소비자 계약 파손"
    cr = _section(out, "summary", "cr")
    assert "왕복영역_zzz" in cr, "★`claim`/`release` 가 쓴 줄을 CR 절이 못 읽는다"
    assert cr.count("왕복영역_zzz") == 2, f"★claim·release 두 줄이 다 안 보인다: {cr.count('왕복영역_zzz')}건"


# ────────── ★부채 — 초록 안에 · **상환 가능하게** ──────────

def test_debt_precondition_released_area_is_in_the_board(tmp_path: Path) -> None:
    """★공허 방지를 **부채 표식에서 분리**한다.

    2판은 이 단언(`"영역0" in seg`)을 xfail 테스트 **안**에 두어, 바로 다음 줄의
    `"영역0" not in seg` 와 **같은 seg 에 대해 모순**이었다 — 어떤 출력도 만족할 수 없으니
    짝짓기를 **정확히 구현해도 XPASS 가 안 나고**, 그 표식은 영구히 초록인 장식이었다.
    ★CLAUDE.md 「완결 가능한 구현계획」 — 도달 불가 지표를 만들지 않는다.
    """
    b = _board(tmp_path, pairs=2)
    assert "영역0" in b.read_text(encoding="utf-8"), "픽스처에 해제된 영역이 없다"
    assert "영역0" in _section(_out("summary", b), "summary", "cr"), \
        "★짝짓기 미구현 상태에서는 해제된 영역도 덤프에 보여야 한다(아래 부채의 전제)"


@pytest.mark.xfail(reason="★미구현 부채: 짝짓기(진짜 미해제 계산). 2026-08-27 구현이 자기 양성 "
                          "대조군에 실패했다(확실한 자기 쌍조차 못 맺음 · RELEASE 1줄이 CLAIM 둘을 "
                          "닫음). 되살리려면 **그 대조군부터** 통과시켜라. ★상환하면 이 표식이 "
                          "XPASS(strict) 로 **발화한다** — 전제는 앞 테스트로 분리했다.",
                   strict=True)
def test_debt_unreleased_claims_are_actually_computed(tmp_path: Path) -> None:
    seg = _section(_out("summary", _board(tmp_path, pairs=2)), "summary", "cr")
    assert "살아있는영역" in seg and "영역0" not in seg


@pytest.mark.xfail(reason="★미해소 부채: 여러 줄 NOTE 의 이어지는 줄이 요약에 안 나온다(그 줄에 "
                          "`- [NOTE]` 표지가 없다). ★상환 경로: `- [NOTE]` 다음 줄부터 다음 `- [` "
                          "전까지를 함께 낸다. **단 표지 문자열을 품은 줄은 제외**해야 ⑧앵커 락과 "
                          "충돌하지 않는다 — 2판은 이 제약을 안 적어 상환 경로가 락을 깼다.",
                   strict=True)
def test_debt_multiline_note_continuation_is_visible(tmp_path: Path) -> None:
    assert _CONT_CANARY in _section(_out("summary", _board(tmp_path)), "summary", "note")


@pytest.mark.xfail(reason="★미측정 부채: 6개 세션이 동시에 `>>` 로 추가한다. 4KiB 미만 단일 "
                          "`printf` 는 실무상 원자적이나 **재지 않았다**. 긴 NOTE 는 초과할 수 있다. "
                          "이 표식은 동시 추가 무결성을 재는 테스트가 생기면 발화한다.",
                   strict=True)
def test_debt_concurrent_append_atomicity(tmp_path: Path) -> None:
    pytest.fail("동시 추가 원자성은 아직 측정하지 않았다")
