"""★`scripts/coord.sh` 의 요약이 **실제로 요약하는지** 잠근다.

【왜 생겼나 · 2026-09-03 실측】
`CLAUDE.md` 와 `coordination/PROTOCOL.md` 는 **인계 공유를 `coord.sh note` 로 하라**고 지시한다.
그런데 종전 `status` 의 꼬리 절은 `grep -nE '\\[(CLAIM|RELEASE)\\]'` 라서 **`[NOTE]` 가 한 건도
안 나왔다.** 보드에서 NOTE 는 **가장 많은 종류**인데도(실측 NOTE 1,772 · CLAIM 641 · RELEASE 547)
요약에서 통째로 사라졌다. 즉 **규약이 시키는 공유가 요약 화면에 도달하지 못했다.**

실제 피해(같은 날, 서로 다른 두 세션):
  · 내 인계 수령 노트 → `status` 출력에 **0건**
  · 동료 세션의 무주인 부채 **3건** → 전부 0건. 그 세션은 그걸 모르고 *"공유했다"* 고 여기고 있었다.

【이 파일이 잠그는 것】
  1. NOTE 가시성          — 두 모집단(NOTE 는 보이고, 본문 전용 문자열은 안 보인다)
  2. 공허 진리 방지        — 단언 **앞에** 대상 존재를 먼저 단언한다
  3. ★제목 정직성          — 요약 제목에 **「미해제」가 없다**
  4. 절단 표기             — 자르는 절은 **전문 조회 방법**을 함께 인쇄한다
  5. `summary` 는 본문 미덤프 — 하류 슬라이싱이 본문과 충돌할 수 없게
  6. `status` 후방호환     — 기존 소비자가 보던 전문 덤프는 그대로다

★**3 이 핵심 강제다.** 종전 제목은 `미해제 CLAIM(편집 중인 공유영역)` 이었고 **주석은 필터를
선언했는데 코드에 필터가 없어** RELEASE 까지 전부 덤프했다(실측 1,224줄). 누군가 짝짓기 없이
다시 「미해제」라고 쓰면 이 테스트가 빨개진다 — **계산하지 않는 것을 계산한다고 말하지 않기 위해서다.**
★짝짓기 자체를 되살리지 마라: 2026-08-27 에 구현됐고 **자기 양성 대조군에 실패**했다
(확실한 자기 쌍조차 못 맺음 · **RELEASE 1줄이 CLAIM 둘을 닫는** 실례). 파생 수치는 8개 세션에
뿌려진 뒤 **철회**됐다. 아래 `xfail` 로 그 부채를 초록 안에 드러내 둔다.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scan_guard import ScannerDeadError, assert_absent  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "coord.sh"

# 본문에만 있고 CLAIM/RELEASE/NOTE 표지가 **없는** 줄 — `summary` 가 본문을 덤프하는지 가르는 카나리.
_BODY_CANARY = "본문전용카나리_zzz_do_not_surface"
# NOTE 본문에 넣는 표식 — 가시성 본판정.
_NOTE_CANARY = "노트카나리_zzz_must_surface"


def _board(tmp_path: Path, *, extra_claims: int = 0) -> Path:
    """합성 보드. ★두 모집단을 같은 파일에 담는다 — 보여야 할 것과 보이면 안 될 것."""
    d = tmp_path / "coordination"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["# 합성 보드", ""]
    for i in range(extra_claims):
        lines.append(f"- [CLAIM] 영역{i} <- br (2026-09-03 09:{i % 60:02d})")
        lines.append(f"- [RELEASE] 영역{i} <- br (2026-09-03 09:{i % 60:02d})")
    lines += [
        "- [CLAIM] 살아있는영역 <- br (2026-09-03 10:00)",
        f"- [NOTE] 2026-09-03 10:10 br: {_NOTE_CANARY}",
        _BODY_CANARY,  # ★[NOTE] 표지가 없는 본문 줄 — 이어붙은 여러 줄 노트와 같은 형태
    ]
    p = d / "BOARD.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _run(cmd: str, board: Path) -> str:
    p = subprocess.run(
        ["bash", str(_SCRIPT), cmd],
        cwd=str(_REPO),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "COORD_DIR": str(board.parent), "HOME": str(Path.home())},
        capture_output=True, text=True, timeout=120,
    )
    assert p.returncode == 0, f"coord.sh {cmd} 가 rc={p.returncode} — stderr:\n{p.stderr[:800]}"
    return p.stdout


def test_scanner_alive_board_actually_contains_the_note(tmp_path: Path) -> None:
    """★공허 진리 방지 — 단언 **앞에** 대상이 실재하는지부터 본다."""
    b = _board(tmp_path)
    text = b.read_text(encoding="utf-8")
    assert _NOTE_CANARY in text, "합성 보드에 NOTE 가 없다 — 아래 가시성 단언이 공허해진다"
    assert _BODY_CANARY in text, "합성 보드에 본문 카나리가 없다 — 음성 축이 공허해진다"


@pytest.mark.parametrize("cmd", ["summary", "status"])
def test_note_is_visible_in_summary(cmd: str, tmp_path: Path) -> None:
    """①NOTE 가시성. ★원래 결함(=NOTE 가 안 보임)을 되살리는 변이가 여기서 빨개진다."""
    out = _run(cmd, _board(tmp_path))
    tail = out.split("=== 최근 NOTE", 1)
    assert len(tail) == 2, f"'최근 NOTE' 절 자체가 없다 — 절이 사라지면 이 락은 무의미하다:\n{out[-500:]}"
    assert _NOTE_CANARY in tail[1], f"NOTE 가 요약 절에 없다 — 종전 결함 그대로다:\n{tail[1][:500]}"


def test_summary_does_not_dump_board_body(tmp_path: Path) -> None:
    """⑤`summary` 는 본문을 안 뱉는다 — 하류 슬라이싱이 본문과 충돌할 수 없게.

    ★대조군: NOTE 카나리는 **반드시 있다**(조회기 생존). 본문 카나리만 없어야 한다.
    """
    out = _run("summary", _board(tmp_path))
    assert_absent(
        out,
        pattern=_BODY_CANARY,
        positive_control=_NOTE_CANARY,
        reason=(
            "summary 가 보드 본문을 덤프했다. 본문에는 절 제목이 그대로 인용돼 있어("
            "실측: 문자열 '미해제 CLAIM' 이 본문에 11회) 하류의 sed 절 자르기가 첫 발생에서 잘려 "
            "엉뚱한 구간을 읽는다 — 동료 세션이 실제로 그렇게 틀린 수를 읽었다."
        ),
        where="coord.sh summary",
    )


def test_status_still_dumps_full_board_backward_compat(tmp_path: Path) -> None:
    """⑥후방호환 — `status` 는 종전대로 전문을 덤프한다(기존 소비자를 깨지 않는다)."""
    out = _run("status", _board(tmp_path))
    assert _BODY_CANARY in out, "status 가 더 이상 보드 전문을 안 뱉는다 — 기존 소비자 회귀다"


@pytest.mark.parametrize("cmd", ["summary", "status"])
def test_summary_does_not_claim_to_compute_unreleased(cmd: str, tmp_path: Path) -> None:
    """③★제목 정직성 — 짝짓기를 안 하면서 「미해제」라고 말하지 않는다.

    종전 제목 `=== 미해제 CLAIM(편집 중인 공유영역) ===` 은 **거짓**이었다: 코드에 필터가 없어
    RELEASE 까지 전부 덤프했다(실측 1,224줄). ★짝짓기는 2026-08-27 에 **자기 양성 대조군에 실패**
    했으므로 되살리지 마라 — 되살릴 거라면 **먼저 그 대조군을 통과시켜라.**
    """
    out = _run(cmd, _board(tmp_path))
    head = out.split("=== 최근 NOTE", 1)[0]
    assert_absent(
        head,
        pattern="미해제",
        positive_control="CLAIM/RELEASE 로그",
        reason=(
            "요약이 「미해제」를 표방한다. 이 절은 CLAIM 과 RELEASE 를 짝짓지 않고 시간순 덤프만 "
            "한다 — 짝짓기는 2026-08-27 에 구현돼 자기 양성 대조군에 실패했고(RELEASE 1줄이 CLAIM "
            "둘을 닫는 실례) 파생 수치가 8개 세션에 뿌려진 뒤 철회됐다. 계산하지 않는 것을 "
            "계산한다고 말하지 마라."
        ),
        where=f"coord.sh {cmd} · CLAIM/RELEASE 절",
    )


def test_truncated_sections_disclose_how_to_read_the_rest(tmp_path: Path) -> None:
    """④절단 표기 — 자르는 절은 **전문 조회 방법**을 함께 인쇄한다.

    ★두 모집단: 절단이 **실제로 일어나는** 보드(항목 > N)를 만들어 태운다. 안 자르는 보드로
    재면 이 단언은 아무것도 안 본다.
    """
    n = 12
    out = _run("summary", _board(tmp_path, extra_claims=n + 5))
    seg = out.split("=== CLAIM/RELEASE 로그", 1)[1].split("=== 최근 NOTE", 1)[0]
    shown = [ln for ln in seg.splitlines() if ln.strip() and ln.strip()[0].isdigit()]
    assert len(shown) == n, f"절단 건수가 {n} 이 아니다({len(shown)}) — SUMMARY_N 이 안 먹는다"
    assert "전문:" in seg, f"절단해 놓고 전문 조회 방법을 안 알려 준다:\n{seg}"


# ────────── ★부채 — 초록 안에 보이게 둔다(커밋 메시지에만 적으면 안 드러난다) ──────────

@pytest.mark.xfail(reason="★미구현 부채: 짝짓기(진짜 미해제 계산). 2026-08-27 구현이 자기 양성 "
                          "대조군에 실패했다(확실한 자기 쌍조차 못 맺음 · RELEASE 1줄이 CLAIM "
                          "둘을 닫음). 되살리려면 **그 대조군부터** 통과시켜라.", strict=True)
def test_debt_unreleased_claims_are_actually_computed(tmp_path: Path) -> None:
    # ★해제된 영역이 **실제로 존재하는** 보드를 쓴다. extra_claims=0 으로 재면 "영역0" 이 애초에
    #   없어서 단언이 **공허하게 참**이 된다 — 첫 판이 그래서 XPASS 로 잘못 통과했다(strict 가 잡음).
    out = _run("summary", _board(tmp_path, extra_claims=2))
    seg = out.split("=== CLAIM/RELEASE 로그", 1)[1].split("=== 최근 NOTE", 1)[0]
    assert "영역0" in seg, "★공허 방지: 해제된 영역이 덤프에 있어야 아래 단언이 의미를 갖는다"
    assert "살아있는영역" in seg and "영역0" not in seg, "짝짓기가 구현되면 해제된 영역은 빠져야 한다"


@pytest.mark.xfail(reason="★미해소 부채: 여러 줄 NOTE 의 2번째 줄 이후는 요약에 안 나온다"
                          "(이어지는 줄에 `- [NOTE]` 표지가 없다). 근본 해소는 엔트리 정규화이며 "
                          "이 PR 범위 밖 — 지금은 행번호와 전문 조회 방법으로 완화했다.", strict=True)
def test_debt_multiline_note_body_is_visible(tmp_path: Path) -> None:
    out = _run("summary", _board(tmp_path))
    assert _BODY_CANARY in out, "여러 줄 노트의 이어지는 줄이 요약에 나와야 한다"
