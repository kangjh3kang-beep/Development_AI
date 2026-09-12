"""계기판 ③ 분석상태 축 — **「판정 불가」를 네 갈래로 가른다**.

★왜 이 파일이 있나 (2026-09-12 · sid=7af9eaa2)

  계기판은 인사이트 24h 창이 0 이면 *"★판정 불가 — 시스템 유휴"* 를 찍고 끝냈다.
  **정직하지만 답이 아니었다.** 답은 `analyzer.py` 가 **이미 발행하고 있었다** —
  `growth_analysis` 설정키(`state` ∈ judged/starved/idle · TTL 180분)이고
  프론트(`GrowthDashboard.tsx`)는 그것을 읽는다. 빠진 것은 **이 레인의 소비처**였다.

  ★그 사실을 **소스 grep 으로 못 찾았다.** `INSERT INTO platform_events`(**매체**)로 찾았는데
    생산자는 `platform_settings` 에 쓴다. 물어야 했던 것은
    *"분석기가 자기 실행을 **어디에** 남기는가"*(**목적**)였다.
    전제를 깬 것은 소스가 아니라 **라이브 응답**이었다.

★락의 형태 — **파티션형**. 네 모집단이 **서로 다른 답**을 내야 한다:

    starved   → ok       (돌았고 표본 하한 미달 · 유휴이지 고장이 아니다)
    idle      → obs      (축 자체가 안 돌았다)
    (행없음)  → obs      (TTL 180 > 주기 60 이므로 **3회 연속 미실행**)
    (필드없음)→ unknown  (**안 재 봤다** — 0 과 절대 뭉치지 않는다)

★그리고 **셸이 이 규칙을 다시 구현하지 않는지**까지 태운다. 산문은 여러 구현을 허용하고,
  이 저장소는 큐 정렬을 산문으로 주고받다 **없는 결함을 신고**한 전례가 있다.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MON = REPO / "propai-platform" / "scripts" / "monitor"
SCRIPT = MON / "integrator_dashboard.sh"
PROBE = MON / "growth_stale_producer_probe.py"


def _probe_mod():
    """★임포트만으로 DB 에 붙지 않는다 — 순수 함수를 직접 태운다(사본 금지)."""
    spec = importlib.util.spec_from_file_location("_gsp_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _shell(astate: str, ins: str) -> str:
    """★**실물 셸 함수**를 태운다 — 파이프라인을 테스트에 복사하지 않는다."""
    out = subprocess.run(
        ["bash", "-c",
         f". '{SCRIPT}' --verdict-lib; analysis_verdict_of '{astate}' '{ins}'"],
        cwd=REPO, capture_output=True, text=True,
    )
    return out.stdout.strip()


# ── ① 네 모집단이 서로 다른 판정을 낸다(파티션) ──────────────────────────────
@pytest.mark.parametrize(
    "astate,ins,expected",
    [
        ("starved", "0", "ok"),
        ("idle", "0", "obs"),
        ("(행없음)", "0", "obs"),
        ("(필드없음)", "0", "unknown"),
    ],
)
def test_four_populations_each_map_to_their_kind(astate, ins, expected):
    kind, why = _probe_mod().analysis_verdict(astate, ins)
    assert kind == expected, (astate, kind, why)
    assert why, "사유가 비면 다음 사람이 무엇을 볼지 모른다"


def test_the_four_are_not_collapsed_into_one():
    """★하나로 접으면 이 함수는 장식이다 — **서로 다른 사유**까지 요구한다."""
    m = _probe_mod()
    reasons = [m.analysis_verdict(s, "0")[1]
               for s in ("starved", "idle", "(행없음)", "(필드없음)")]
    assert len(set(reasons)) == 4, reasons


def test_absent_row_is_not_read_as_idle_normality():
    """★행 부재를 «유휴」로 읽으면 3회 연속 미실행이 「정상」이 된다."""
    m = _probe_mod()
    assert m.analysis_verdict(m.ASTATE_ABSENT, "0")[0] == "obs"
    assert m.analysis_verdict("starved", "0")[0] == "ok"
    # ★두 모집단 대조 — 「부재」와 「굶음」이 같은 답을 내면 이 락은 공허하다.
    assert (m.analysis_verdict(m.ASTATE_ABSENT, "0")[0]
            != m.analysis_verdict("starved", "0")[0])


def test_missing_field_is_unknown_not_zero():
    """★옛 프로브 사본이 돌면 **안 재 봤다**여야 한다 — 0(정상)이 아니다."""
    m = _probe_mod()
    assert m.analysis_verdict(m.ASTATE_MISSING, "0")[0] == "unknown"


def test_judged_with_empty_window_is_a_contradiction():
    """★«판정했다»면서 창이 비면 두 관측이 모순이다. 침묵으로 두지 않는다."""
    m = _probe_mod()
    assert m.analysis_verdict("judged", "0")[0] == "obs"
    assert m.analysis_verdict("judged", "3")[0] == "ok"


def test_unrecognized_state_is_unknown_not_ok():
    """★새 상태 어휘가 생기면 **모른다**고 말해야 한다 — 조용히 초록이 되면 안 된다."""
    assert _probe_mod().analysis_verdict("brand_new_state", "0")[0] == "unknown"


# ── ② 계기판이 그 함수를 **실제로** 태운다(배선 축) ──────────────────────────
def test_dashboard_burns_the_probe_function_not_a_copy():
    """★함수만 잠그면 배선은 무잠금이다 — 셸이 같은 답을 내는지 직접 태운다."""
    for astate, expected in (("starved", "ok"), ("idle", "obs"),
                             ("(행없음)", "obs"), ("(필드없음)", "unknown")):
        out = _shell(astate, "0")
        assert out.split("|", 1)[0] == expected, (astate, out)


def test_dashboard_does_not_reimplement_the_rule_in_shell():
    """★산문은 여러 구현을 허용한다 — 셸에 상태 어휘가 **박히면** 두 판정이 갈린다.

    판정 어휘(`starved`)가 셸 쪽 `case`/`if` 에 나타나면 그 순간 규칙이 둘이 된다.
    ★주석은 배제한다 — 이 파일 자신이 «소스 검사는 주석에 뚫린다» 를 아는 저장소에 있다.
    """
    code = [ln for ln in SCRIPT.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#")]
    hits = [ln for ln in code if "starved" in ln]
    assert hits == [], hits
    # ★대조군 — 이 검사기가 살아 있는가(실행 라인에 반드시 있는 문자열).
    assert any("analysis_verdict_of" in ln for ln in code), "조회기 사망"


# ── ③ 프로브 출력 계약(계기판이 이름으로 뽑는다) ────────────────────────────
def test_probe_declares_the_keys_the_dashboard_extracts():
    """★계기판은 `astate=`·`aat=` 처럼 **이름으로** 뽑는다. 이름이 갈리면 조용히 빈다."""
    src = PROBE.read_text(encoding="utf-8")
    for key in ("astate=%s", "aat=%s", "aaxes=%s", "ains=%s", "alast=%s"):
        assert key in src, key
    dash = SCRIPT.read_text(encoding="utf-8")
    for key in ("astate=", "aat=", "aaxes=", "ains=", "alast="):
        assert key in dash, key


def test_probe_setting_key_matches_the_producer():
    """★키를 여기서 다시 정하면 생산자와 갈린다 — **생산자에서 파생**해 대조한다."""
    m = _probe_mod()
    producer = (REPO / "propai-platform" / "apps" / "api" / "app" / "services"
                / "growth" / "analyzer.py").read_text(encoding="utf-8")
    assert f'ANALYSIS_STATUS_SETTING_KEY = "{m.ANALYSIS_SETTING_KEY}"' in producer
    # ★대조군 — 생산자 파일을 실제로 읽었는가(엉뚱한 파일이면 이 줄이 먼저 죽는다).
    assert "def analysis_status_payload(" in producer


def test_probe_state_vocabulary_matches_the_producer():
    """★상태 어휘도 생산자에서 파생시킨다 — 손 목록은 곧 상한이 된다."""
    producer = (REPO / "propai-platform" / "apps" / "api" / "app" / "services"
                / "growth" / "analyzer.py").read_text(encoding="utf-8")
    line = [ln for ln in producer.splitlines()
            if ln.strip().startswith("state = ") and "starved" in ln]
    assert len(line) == 1, line
    m = _probe_mod()
    for token in ("idle", "judged", "starved"):
        assert f'"{token}"' in line[0], token
        assert m.analysis_verdict(token, "0")[0] != "unknown", token
