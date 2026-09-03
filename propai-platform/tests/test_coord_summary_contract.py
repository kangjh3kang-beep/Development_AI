"""★`scripts/coord.sh` 의 요약이 **실제로 요약하는지** 잠근다.

【왜 생겼나 · 2026-09-03 실측】
`CLAUDE.md` 와 `coordination/PROTOCOL.md` 는 **인계 공유를 `coord.sh note` 로 하라**고 지시한다.
그런데 종전 `status` 의 꼬리 절은 `\\[(CLAIM|RELEASE)\\]` 만 grep 해 **`[NOTE]` 가 한 건도 안 나왔다.**
보드에서 NOTE 는 가장 많은 종류인데도 요약에서 통째로 사라졌다 — **규약이 시키는 공유가 화면에
도달하지 못했다.** 재측정: `grep -cE '^- \\[NOTE\\]' "$BOARD"` vs `'^- \\[(CLAIM|RELEASE)\\]'`.

【★이 파일의 2판이다 — 1판은 독립 적대 리뷰에서 무너졌다】
1판은 작성자가 고른 변이 5종에 5/5 CAUGHT 를 받았다. 리뷰어가 **자기 변이 10종을 넣었고 10종
전부 SURVIVED** 했다. 그 목록이 아래 각 테스트의 존재 이유다:

    M1  COORD_SUMMARY_N 배선 절단(상수로 고정)      → test_env_knob_is_actually_wired
    M2  NOTE grep 의 **행두 앵커** 제거             → test_anchors_reject_mid_line_matches
    M3  CLAIM/RELEASE 앵커 제거                     → 〃
    M4  절단 안내를 **한쪽 절에서만** 삭제          → test_both_truncating_sections_disclose
    M6  tail → head (**최신↔최고참 반전**)          → test_summary_shows_newest_not_oldest
    M10 「미해제」를 **다른 절 제목**에 넣기        → test_summary_never_claims_unreleased
    +   `cut -c` 가 한글을 **바이트로** 잘라 파손    → test_truncation_never_breaks_utf8
    +   `(없음)` 이 **조회기 사망과 0건을 뭉갬**     → test_dead_scanner_is_not_reported_as_zero
    +   `status` 「후방호환」이 거짓(1,214줄 소실)   → test_status_section_is_not_truncated

★교훈: **「N/N CAUGHT」는 내가 고른 변이에만 참이다.** 특히 M6 이 통과했던 이유는 픽스처가 NOTE 를
**1건만** 넣어 `head` 와 `tail` 의 **차가 0** 이었기 때문이다 — 차가 0인 픽스처는 잠금이 아니다.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scan_guard import assert_absent  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "coord.sh"

# ★세 카나리를 **서로 다른 문자열**로 둔다.
#   1판은 「본문 미덤프」 락과 「여러 줄 노트」 부채가 **같은 카나리**를 정반대로 요구해
#   부채가 **구조적으로 상환 불가**였다(리뷰어 지적). 분리하면 상환 가능해진다.
_NOTE_CANARY = "노트카나리_zzz_must_surface"        # NOTE 첫 줄 — 보여야 한다
_CONT_CANARY = "이어붙은줄카나리_zzz_note_body"      # NOTE 의 **이어지는 줄** — 지금은 안 보인다(부채)
_BODY_CANARY = "무관본문카나리_zzz_never_surface"    # NOTE 와 무관한 본문 줄 — 언제나 안 보인다
_LONG_KO = "가나다라마바사아자차" * 40               # 240자 초과 한글 — 절단 안전성 축


def _board(tmp_path: Path, *, notes: int = 1, pairs: int = 0, long_note: bool = False) -> Path:
    d = tmp_path / "coordination"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["# 합성 보드", "", _BODY_CANARY]   # ★NOTE 뒤가 아닌 무관 본문 줄
    for i in range(pairs):
        lines.append(f"- [CLAIM] 영역{i} <- br (2026-09-03 09:{i % 60:02d})")
        lines.append(f"- [RELEASE] 영역{i} <- br (2026-09-03 09:{i % 60:02d})")
    lines.append("- [CLAIM] 살아있는영역 <- br (2026-09-03 10:00)")
    for i in range(1, notes + 1):
        lines.append(f"- [NOTE] 2026-09-03 10:{i % 60:02d} br: 노트{i:03d}")
    if long_note:
        lines.append(f"- [NOTE] 2026-09-03 11:00 br: {_LONG_KO}")
    lines.append(f"- [NOTE] 2026-09-03 11:59 br: {_NOTE_CANARY}")
    lines.append(_CONT_CANARY)                  # ★바로 위 NOTE 의 이어지는 줄
    p = d / "BOARD.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _run(cmd: str, board: Path, *, env_extra: dict | None = None, expect_rc: int | None = 0):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "COORD_DIR": str(board.parent),
           "HOME": str(Path.home()), "LANG": "en_US.UTF-8"}
    env.update(env_extra or {})
    p = subprocess.run(["bash", str(_SCRIPT), cmd], cwd=str(_REPO), env=env,
                       capture_output=True, timeout=120)
    if expect_rc is not None:
        assert p.returncode == expect_rc, (
            f"coord.sh {cmd} rc={p.returncode}(기대 {expect_rc})\n{p.stderr.decode(errors='replace')[:600]}")
    return p


def _out(cmd: str, board: Path, **kw) -> str:
    return _run(cmd, board, **kw).stdout.decode("utf-8")


def _note_section(text: str) -> str:
    i = text.index("=== 최근 NOTE")
    return text[i:]


# ───────────────────────── 공허 진리 방지 ─────────────────────────

def test_fixture_actually_contains_every_canary(tmp_path: Path) -> None:
    """★단언 **앞에** 대상 실재를 먼저 본다 — 아래가 공허하게 참이 되지 않도록."""
    t = _board(tmp_path, long_note=True).read_text(encoding="utf-8")
    for c in (_NOTE_CANARY, _CONT_CANARY, _BODY_CANARY, _LONG_KO):
        assert c in t, f"픽스처에 {c[:20]} 가 없다 — 그 축의 단언이 공허해진다"


# ───────────────────────── 원결함: NOTE 가시성 ─────────────────────────

@pytest.mark.parametrize("cmd", ["summary", "status"])
def test_note_is_visible(cmd: str, tmp_path: Path) -> None:
    """①원래 결함(NOTE 미가시)을 되살리는 변이가 여기서 빨개진다."""
    assert _NOTE_CANARY in _note_section(_out(cmd, _board(tmp_path))), \
        "NOTE 가 요약 절에 없다 — 종전 결함 그대로다"


def test_summary_does_not_dump_board_body(tmp_path: Path) -> None:
    """⑤`summary` 는 본문을 안 뱉는다 — 하류 슬라이싱이 본문과 충돌할 수 없게."""
    assert_absent(
        _out("summary", _board(tmp_path)),
        pattern=_BODY_CANARY, positive_control=_NOTE_CANARY,
        reason=("summary 가 보드 본문을 덤프했다. 본문에는 절 제목이 그대로 인용돼 있어 하류의 "
                "sed 절 자르기가 첫 발생에서 잘려 엉뚱한 구간을 읽는다."),
        where="coord.sh summary")


# ───────────────── 리뷰어 M6: 순서 — **두 모집단으로** ─────────────────

def test_summary_shows_newest_not_oldest(tmp_path: Path) -> None:
    """★M6 — `tail` → `head` 반전이 1판에서 **생존**했다. 픽스처가 NOTE 1건이라 차가 0이었다.

    ★두 모집단을 같은 실행에서 본다: **꼬리는 나오고 머리는 안 나온다.**
    """
    n = 12
    seg = _note_section(_out("summary", _board(tmp_path, notes=n + 8)))
    shown = re.findall(r"노트(\d{3})", seg)
    assert shown, "★노트가 하나도 안 나왔다 — 아래 순서 단언이 공허해진다"
    assert "001" not in shown, f"★가장 오래된 것이 나온다 — head/tail 이 뒤집혔다: {shown}"
    assert "020" in shown, f"★가장 최신이 안 나온다 — 최근 N건이 아니다: {shown}"


def test_env_knob_is_actually_wired(tmp_path: Path) -> None:
    """★M1 — `SUMMARY_N=12` 상수화가 1판에서 생존했다. **두 값이 다른 결과**를 내야 한다."""
    b = _board(tmp_path, notes=20)
    # ★`노트\d{3}` 만 세면 **꼬리의 카나리 노트가 안 세어져** 1씩 어긋난다(첫 실행에서 실측:
    #   3→2 · 15→14). 모집단은 「출력된 NOTE 항목 전부」다 — 축을 그것에 맞춘다.
    def shown(n: str) -> int:
        seg = _note_section(_out("summary", b, env_extra={"COORD_SUMMARY_N": n}))
        return len(re.findall(r"^\s*\d+:- \[NOTE\]", seg, re.MULTILINE))
    few, many = shown("3"), shown("15")
    assert few == 3 and many == 15, f"★환경변수가 배선되지 않았다(3→{few} · 15→{many})"


# ───────────────── 리뷰어 M2/M3: 행두 앵커 ─────────────────

@pytest.mark.parametrize("marker,section", [("NOTE", "note"), ("CLAIM", "cr")])
def test_anchors_reject_mid_line_matches(marker: str, section: str, tmp_path: Path) -> None:
    """★M2/M3 — 앵커를 지워도 초록이었다. 본문이 표지를 **인용**하면 오염된다.

    ★2판 재실행에서 **M3(CLAIM/RELEASE 앵커 제거)가 또 SURVIVED** 했다 — 1판·2판 모두
    **NOTE 절만** 봤기 때문이다. 파생의 축이 「표지 하나」였고 모집단은 「표지 전부」였다.
    → 두 표지를 모두 태운다.
    """
    b = _board(tmp_path)
    t = b.read_text(encoding="utf-8")
    b.write_text(t + f"규약대로 - [{marker}] 표기로 남기라고 적힌 인용줄 오염카나리_zzz\n",
                 encoding="utf-8")
    out = _out("summary", b)
    seg = _note_section(out) if section == "note" else \
        out[out.index("=== CLAIM/RELEASE 로그"):out.index("=== 최근 NOTE")]
    assert_absent(
        seg, pattern="오염카나리_zzz", positive_control="↳",
        reason=f"행두 앵커가 없어 본문 중간에 인용된 [{marker}] 표지까지 집었다.",
        where=f"coord.sh summary · {section} 절")


# ───────────────── 리뷰어 M10: 제목 정직성(전체 출력) ─────────────────

def test_summary_never_claims_unreleased(tmp_path: Path) -> None:
    """★M10 — 1판은 **첫 절만** 봐서 다른 절 제목에 「미해제」를 넣으면 통과했다.

    ★`summary` 는 보드 본문을 안 뱉으므로 **출력 전체가 스크립트 자신의 문구**다. 그래서
    전체를 볼 수 있다(1판이 첫 절만 본 것은 파생의 축이 한 단계 좁았던 것).
    ★`status` 는 후방호환으로 종전 제목을 **의도적으로 유지**하므로 이 축의 대상이 아니다.
    """
    assert_absent(
        _out("summary", _board(tmp_path)),
        pattern="미해제", positive_control="CLAIM/RELEASE 로그",
        reason=("요약이 「미해제」를 표방한다. 이 절은 짝짓기를 하지 않는다 — 짝짓기는 2026-08-27 에 "
                "구현돼 자기 양성 대조군에 실패했고 파생 수치가 여러 세션에 뿌려진 뒤 철회됐다. "
                "계산하지 않는 것을 계산한다고 말하지 마라."),
        where="coord.sh summary 전체")


# ───────────────── 리뷰어 CRITICAL: 한글 절단 파손 ─────────────────

def test_truncation_never_breaks_utf8(tmp_path: Path) -> None:
    """★`cut -c` 는 GNU 에서 **바이트 기반**이라 한글을 문자 중간에서 자른다.

    실측(라이브 보드): 240바이트로 자르면 NOTE 1,780건 중 1,369건이 잘리고 **533건이 UTF-8 파손**.
    ★이 PR 이 **새로 보이게 만든 바로 그 노트**가 깨지는 것이라 가장 나쁜 형태다.
    """
    raw = _run("summary", _board(tmp_path, long_note=True)).stdout
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        pytest.fail(f"★절단이 UTF-8 을 깼다 — 바이트 단위로 자르고 있다: {e}")
    assert "…[잘림]" in text, "★잘라 놓고 표식이 없다 — 잘렸는지조차 알 수 없다"


def test_long_line_is_actually_truncated(tmp_path: Path) -> None:
    """★공허 방지 — 위 테스트가 **절단이 실제로 일어나는** 입력을 태우는지 못 박는다."""
    seg = _note_section(_out("summary", _board(tmp_path, long_note=True)))
    assert _LONG_KO not in seg, "★긴 줄이 안 잘렸다 — 절단 축의 단언이 공허해진다"


# ───────────────── 리뷰어: 조회기 사망 vs 진짜 0건 ─────────────────

def test_dead_scanner_is_not_reported_as_zero(tmp_path: Path) -> None:
    """★`(없음)` 이 **조회 실패**와 **진짜 0건**을 뭉개면 안 된다.

    이 저장소는 정확히 이것 때문에 `_scan_guard.ScannerDeadError` 를 `AssertionError` 와 **다른
    예외로** 던진다 — "뭉치면 「검사기가 죽었다」가 「깨끗하다」로 읽힌다".
    ★1판은 `COORD_SUMMARY_N=abc` 에서 보드에 노트 수천 건이 있는데 **`(없음)`** 을 rc=0 으로 냈다.
    """
    b = _board(tmp_path, notes=5)
    p = _run("summary", b, env_extra={"COORD_SUMMARY_N": "abc"}, expect_rc=None)
    assert p.returncode != 0, "★비수치 입력인데 조용히 성공했다 — 「0건」으로 뭉갤 위험"
    assert "없음" not in p.stdout.decode("utf-8", "replace"), "★조회 불가를 「없음」으로 보고했다(위음성)"


def test_missing_board_is_refused_not_reported_empty(tmp_path: Path) -> None:
    """★조회 명령이 **유령 보드를 만들고** 자신 있게 「없음」을 보고하면 안 된다(§26)."""
    ghost = tmp_path / "nope" / "coordination" / "BOARD.md"
    p = _run("summary", ghost, expect_rc=None)
    assert p.returncode != 0, "★보드가 없는데 성공했다"
    assert not ghost.exists(), "★조회 명령이 보드를 생성했다 — COORD_DIR 오타 시 유령 보드가 생긴다"


def test_true_zero_is_distinguishable(tmp_path: Path) -> None:
    """★두 모집단의 반대편 — **진짜 0건**은 정상 종료하고 그렇게 말한다."""
    d = tmp_path / "coordination"; d.mkdir(parents=True)
    (d / "BOARD.md").write_text("# 빈 보드\n", encoding="utf-8")
    out = _out("summary", d / "BOARD.md")
    assert "없음" in out, "★진짜 0건인데 아무 말도 없다"


# ───────────────── 리뷰어: status 후방호환(1,214줄 소실) ─────────────────

def test_status_section_is_not_truncated(tmp_path: Path) -> None:
    """★커밋이 「후방호환」이라 선언했는데 1판은 종전 절을 **절단**했다(실측 1,226 → 12줄).

    문서화된 소비자가 실재한다 — 인계서들이 **"★자르지 마라 — NOTE 줄에 배포 요청이 숨는다"** 라고
    명시한다. 그래서 `status` 는 **전량**을 유지하고 요약은 `summary` 로 따로 낸다.
    """
    b = _board(tmp_path, pairs=30)
    out = _out("status", b)
    want = sum(1 for ln in b.read_text(encoding="utf-8").splitlines()
               if re.search(r"\[(CLAIM|RELEASE)\]", ln))
    assert want > 12, f"★픽스처의 CLAIM/RELEASE 가 {want}건 — 절단 축이 공허해진다"
    seg = out[out.index("=== 미해제 CLAIM"):out.index("=== 최근 NOTE")]
    got = len(re.findall(r"\[(?:CLAIM|RELEASE)\]", seg))
    assert got == want, f"★status 가 종전 절을 절단했다({want} → {got}) — 후방호환 위반"
    assert _BODY_CANARY in out, "★status 가 보드 전문을 안 뱉는다 — 기존 소비자 회귀"


def test_both_truncating_sections_disclose_how_to_read_the_rest(tmp_path: Path) -> None:
    """★M4 — 1판은 **한쪽 절에서만** 안내를 찾아, 다른 절의 안내를 지워도 초록이었다."""
    out = _out("summary", _board(tmp_path, notes=20, pairs=20))
    cr = out[out.index("=== CLAIM/RELEASE 로그"):out.index("=== 최근 NOTE")]
    nt = _note_section(out)
    assert "전문:" in cr, f"★CLAIM/RELEASE 절이 절단해 놓고 전문 조회 방법을 안 알려 준다:\n{cr[-300:]}"
    assert "전문:" in nt, f"★NOTE 절이 절단해 놓고 전문 조회 방법을 안 알려 준다:\n{nt[-300:]}"


# ────────── ★부채 — 초록 안에 보이게 (★1판과 달리 **상환 가능**하다) ──────────

@pytest.mark.xfail(reason="★미구현 부채: 짝짓기(진짜 미해제 계산). 2026-08-27 구현이 자기 양성 "
                          "대조군에 실패했다. 되살리려면 **그 대조군부터** 통과시켜라.", strict=True)
def test_debt_unreleased_claims_are_actually_computed(tmp_path: Path) -> None:
    out = _out("summary", _board(tmp_path, pairs=2))
    seg = out[out.index("=== CLAIM/RELEASE 로그"):out.index("=== 최근 NOTE")]
    assert "영역0" in seg, "★공허 방지: 해제된 영역이 덤프에 있어야 아래 단언이 의미를 갖는다"
    assert "살아있는영역" in seg and "영역0" not in seg


@pytest.mark.xfail(reason="★미해소 부채: 여러 줄 NOTE 의 이어지는 줄이 요약에 안 나온다"
                          "(그 줄에는 `- [NOTE]` 표지가 없다). ★1판은 이 부채가 「본문 미덤프」 락과 "
                          "**같은 카나리**를 정반대로 요구해 구조적으로 상환 불가였다 — 카나리를 "
                          "분리해 상환 가능하게 만들었다(NOTE 이어지는 줄만 내보내면 갚아진다).",
                   strict=True)
def test_debt_multiline_note_continuation_is_visible(tmp_path: Path) -> None:
    assert _CONT_CANARY in _note_section(_out("summary", _board(tmp_path)))


def test_summary_header_line_count_is_real(tmp_path: Path) -> None:
    """★M9 — 헤더의 `(N줄)` 을 `echo 0` 으로 바꿔도 초록이었다(2판 재실행에서 SURVIVED).

    ★작은 값이라도 **아무것도 안 잠그면 장식**이다. 게다가 이 수는 사람이 「보드가 얼마나
    자랐나」를 판단하는 데 쓰므로 거짓이면 오도한다.
    """
    b = _board(tmp_path, notes=7, pairs=3)
    want = len(b.read_text(encoding="utf-8").splitlines())
    out = _out("summary", b)
    m = re.search(r"\((\d+)줄", out)
    assert m, f"★헤더에 줄수 표기가 없다:\n{out[:400]}"
    assert int(m.group(1)) == want, f"★헤더 줄수가 거짓이다(표기 {m.group(1)} · 실제 {want})"
