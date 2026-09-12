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

#: ★`starved` 는 이제 **축 요약 없이는 판정 불가**다(입력 0 과 하한 미달을 가르기 때문).
#:   「입력이 있는 축이 하나라도 있다」 = 정상 유휴.
_AX_IDLE = "lat 0/19 pay 0/1"
#: 모든 축의 입력이 0 = 수집 경로 의심.
_AX_NO_INPUT = "fal 0/0 lat 0/0 qua 0/0"


def _probe_mod():
    """★임포트만으로 DB 에 붙지 않는다 — 순수 함수를 직접 태운다(사본 금지)."""
    spec = importlib.util.spec_from_file_location("_gsp_probe", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _shell(astate: str, ins: str, axes: str = _AX_IDLE) -> str:
    """★**실물 셸 함수**를 태운다 — 파이프라인을 테스트에 복사하지 않는다."""
    out = subprocess.run(
        ["bash", "-c",
         f". '{SCRIPT}' --verdict-lib; analysis_verdict_of '{astate}' '{ins}' '{axes}'"],
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
    kind, why = _probe_mod().analysis_verdict(astate, ins, _AX_IDLE)
    assert kind == expected, (astate, kind, why)
    assert why, "사유가 비면 다음 사람이 무엇을 볼지 모른다"


def test_the_four_are_not_collapsed_into_one():
    """★하나로 접으면 이 함수는 장식이다 — **서로 다른 사유**까지 요구한다."""
    m = _probe_mod()
    reasons = [m.analysis_verdict(s, "0", _AX_IDLE)[1]
               for s in ("starved", "idle", "(행없음)", "(필드없음)")]
    assert len(set(reasons)) == 4, reasons


def test_absent_row_is_not_read_as_idle_normality():
    """★행 부재를 «유휴」로 읽으면 3회 연속 미실행이 「정상」이 된다."""
    m = _probe_mod()
    assert m.analysis_verdict(m.ASTATE_ABSENT, "0", _AX_IDLE)[0] == "obs"
    assert m.analysis_verdict("starved", "0", _AX_IDLE)[0] == "ok"
    # ★두 모집단 대조 — 「부재」와 「굶음」이 같은 답을 내면 이 락은 공허하다.
    assert (m.analysis_verdict(m.ASTATE_ABSENT, "0", _AX_IDLE)[0]
            != m.analysis_verdict("starved", "0", _AX_IDLE)[0])


def test_missing_field_is_unknown_not_zero():
    """★옛 프로브 사본이 돌면 **안 재 봤다**여야 한다 — 0(정상)이 아니다."""
    m = _probe_mod()
    assert m.analysis_verdict(m.ASTATE_MISSING, "0", _AX_IDLE)[0] == "unknown"


def test_judged_with_empty_window_is_a_contradiction():
    """★«판정했다»면서 창이 비면 두 관측이 모순이다. 침묵으로 두지 않는다."""
    m = _probe_mod()
    assert m.analysis_verdict("judged", "0", _AX_IDLE)[0] == "obs"
    assert m.analysis_verdict("judged", "3", _AX_IDLE)[0] == "ok"


def test_unrecognized_state_is_unknown_not_ok():
    """★새 상태 어휘가 생기면 **모른다**고 말해야 한다 — 조용히 초록이 되면 안 된다."""
    assert _probe_mod().analysis_verdict("brand_new_state", "0", _AX_IDLE)[0] == "unknown"


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
        assert m.analysis_verdict(token, "0", _AX_IDLE)[0] != "unknown", token


# ── ④ 변이 감사가 드러낸 **안 태워지던 층** ─────────────────────────────────
#    2026-09-12: 설정 행 → 다섯 값 대응이 `main()` 안에 있어 **DB 없이는 도달 불가**였고
#    `isinstance` 무력화·네 줄 삭제가 **전부 SURVIVED**(변이 6건). 순수 함수로 꺼내 태운다.
def test_fields_from_a_real_snapshot_shape():
    """★라이브 실측 형태(2026-09-12 08:05Z)를 그대로 태운다."""
    m = _probe_mod()
    row = {"at": "2026-09-12T08:05:05.549467+00:00",
           "axes": "fal 0/0 lat 0/19 pay 0/1 qua 0/0",
           "state": "starved", "insights": 0}
    astate, aat, aaxes, ains, alast = m.analysis_fields(row, '"2026-09-12T08:02:22Z"')
    assert astate == "starved"
    assert aat == "2026-09-12T08:05:05.549467+00:00"
    assert ains == 0
    assert alast == "2026-09-12T08:02:22Z", "★워터마크의 따옴표가 안 벗겨졌다"


def test_axes_must_not_contain_spaces_or_the_dashboard_truncates_it():
    """★★계기판은 `grep -oE 'aaxes=[^ ]+'` 로 **공백 경계**로 뽑는다.

    원본 `axes` 에는 공백이 있다(`"fal 0/0 lat 0/19"`). 치환을 빼면 **뒤가 통째로 잘려**
    화면에는 `fal` 만 남는다 — 값이 **조용히 반쪽**이 된다.
    """
    m = _probe_mod()
    _, _, aaxes, _, _ = m.analysis_fields(
        {"state": "starved", "axes": "fal 0/0 lat 0/19"}, None)
    assert " " not in aaxes, aaxes
    # ★두 모집단 — 내용이 실제로 실려 있어야 한다(공백만 지우고 값을 버리면 안 된다).
    assert "fal" in aaxes and "lat" in aaxes and "0/19" in aaxes


def test_absent_and_non_dict_rows_both_become_absent():
    """★`None` 과 «dict 가 아닌 값» 은 **같은 처방**이다 — 둘 다 부재로 본다."""
    m = _probe_mod()
    for row in (None, "some string", 42, []):
        astate, aat, aaxes, ains, _ = m.analysis_fields(row, None)
        assert astate == m.ASTATE_ABSENT, row
        assert (aat, aaxes, ains) == ("-", "-", "-"), row
    # ★대조군 — 정상 dict 는 부재가 **아니어야** 한다(위 단언이 공허하지 않다).
    assert m.analysis_fields({"state": "judged"}, None)[0] == "judged"


def test_missing_watermark_is_dash_not_empty():
    """★빈 문자열이면 계기판의 `[^ ]+` 가 **다음 토큰을 끌어온다**(값이 밀려 들어온다)."""
    m = _probe_mod()
    assert m.analysis_fields({"state": "starved"}, None)[4] == "-"
    assert m.analysis_fields({"state": "starved"}, "")[4] == "-"


def test_five_populations_give_five_distinct_reasons():
    """★★사유 문구는 잠그지 않지만 **「각자 자기 사유를 낸다」는 잠근다**.

    이것이 `astate == ASTATE_MISSING` 분기의 **무력화를 잡는다** — 그 분기를 끄면
    미지 어휘 폴백과 **같은 사유**로 떨어지기 때문이다(변이 실측 2026-09-12: 종전엔 생존).
    """
    m = _probe_mod()
    inputs = ["starved", "idle", m.ASTATE_ABSENT, m.ASTATE_MISSING, "brand_new_state"]
    reasons = [m.analysis_verdict(s, "0", _AX_IDLE)[1] for s in inputs]
    assert len(set(reasons)) == 5, list(zip(inputs, reasons))


def test_probe_emits_every_key_the_dashboard_extracts_from_the_probe_line():
    """★**목록이 아니라 파생**으로 대조한다 — 계기판이 `$G` 에서 뽑는 **모든** 키.

    손으로 센 목록은 곧 상한이 된다. 계기판 소스에서 `grep -oE '<키>=…' "$G"` 패턴을
    긁어 그 전부를 프로브 출력에 요구한다 — 새 키가 생겨도 자동으로 감시망에 든다.
    ★이것이 프로브 `print` 형식 문자열 변이를 잡는다(종전 생존 2건).
    """
    import re as _re
    dash = SCRIPT.read_text(encoding="utf-8")
    # ★**어느 프로브의 줄에서 뽑는지**까지 함께 파생시킨다. 첫 판은 변수를 안 보고
    #   키만 긁어 **버스트 프로브의 키 3개를 성장 프로브에 요구**했다(위양성) —
    #   *«파생으로 바꿔도 축이 틀리면 틀린다»*. 축은 «키» 가 아니라 «(출처 변수, 키)» 다.
    # ★공백에 관대하게 — 첫 판은 `echo  "$B"`(두 칸) 때문에 13개 중 8개만 집었고,
    #   그 절단이 **하한 단언을 빨갛게 만들어** 드러났다(조용히 반쪽이 되지 않았다).
    pairs = _re.findall(
        r"""echo\s+"\$([A-Z])"\s*\|\s*grep -oE ['"]([a-z_]+)=""", dash)
    assert len(pairs) >= 13, f"★키 수집기가 죽었다(공허 방지) — {sorted(set(pairs))}"
    sources = {"G": PROBE, "B": MON / "latency_burst_probe.py"}
    assert set(v for v, _ in pairs) <= set(sources), f"★모르는 출처 변수: {set(v for v, _ in pairs)}"
    missing = []
    for var, key in sorted(set(pairs)):
        if f"{key}=%s" not in sources[var].read_text(encoding="utf-8"):
            missing.append(f"${var}:{key}")
    assert missing == [], f"★계기판이 뽑는데 프로브가 안 내보내는 키: {missing}"
    # ★대조군 — 두 출처가 **둘 다** 실제로 쓰였는가(한쪽만 걸리면 반쪽 감시다).
    assert {v for v, _ in pairs} == {"G", "B"}, sorted({v for v, _ in pairs})


def test_watermark_key_is_derived_from_its_producer():
    """★워터마크 키가 갈리면 화면에 조용히 `-` 만 뜬다 — **생산자에서 파생**해 대조한다."""
    m = _probe_mod()
    sched = (REPO / "propai-platform" / "apps" / "api" / "app" / "services"
             / "growth" / "schedule.py").read_text(encoding="utf-8")
    assert 'return f"growth_last_run.{job}"' in sched, "★생산자 형식이 바뀌었다(락이 낡았다)"
    prefix, job = m.ANALYZE_WATERMARK_KEY.rsplit(".", 1)
    assert prefix == "growth_last_run", m.ANALYZE_WATERMARK_KEY
    # ★잡명이 실제 beat 잡과 같아야 한다 — 오타면 영원히 `-` 다.
    beat = (REPO / "propai-platform" / "apps" / "api" / "app" / "tasks"
            / "celery_app.py").read_text(encoding="utf-8")
    assert f"growth_tasks.{job}_growth" in beat or f"growth_tasks.{job}" in beat, job


# ── ⑤ 2차 변이 감사가 남긴 생존 중 **진짜 구멍**만 닫는다 ────────────────────
def test_missing_insights_key_becomes_dash_not_none():
    """★키가 없으면 `%s` 가 **문자열 "None"** 을 찍어 계기판에 `ains=None` 이 뜬다.

    변이 실측(2026-09-12): `if ains is None:` 무력화가 **생존**했다 — 내 픽스처가
    `insights: 0` 을 항상 줘서 **그 분기에 도달하지 못했다**(§«분기를 만들었으면 그 분기를
    태우는 행을 같은 커밋에»).
    """
    m = _probe_mod()
    assert m.analysis_fields({"state": "starved"}, None)[3] == "-"
    assert m.analysis_fields({"state": "starved", "insights": None}, None)[3] == "-"
    # ★대조군 — 0 은 «없음」이 아니라 **0 이어야** 한다(둘을 뭉개면 이 락이 거짓이다).
    assert m.analysis_fields({"state": "starved", "insights": 0}, None)[3] == 0


def test_missing_field_has_a_dedicated_reason_not_the_generic_template():
    """★★«필드 없음» 분기를 끄면 **미지 어휘 폴백**으로 떨어지는데, 그 폴백은 값을
    보간하므로 사유가 **여전히 달라 보인다** — 그래서 «다섯이 서로 다르다» 로는 못 잡는다.

    변이 실측(2026-09-12): `if astate == ASTATE_MISSING:` 무력화가 두 판 연속 생존했다.
    ⇒ 요구를 바꾼다: 이 모집단은 **자기 전용 설명**을 가져야 하고,
      **폴백 템플릿에 값만 끼운 것이어서는 안 된다.**
    """
    m = _probe_mod()
    dedicated = m.analysis_verdict(m.ASTATE_MISSING, "0", _AX_IDLE)[1]
    generic = m.analysis_verdict("zzz_probe_control", "0", _AX_IDLE)[1]
    # 폴백 템플릿을 «값만 바꾼」 형태로 재구성했을 때 전용 사유와 같으면 = 분기가 죽었다.
    faked = generic.replace("zzz_probe_control", m.ASTATE_MISSING)
    assert dedicated != faked, "★필드없음 분기가 폴백으로 떨어졌다(전용 설명이 없다)"
    assert m.analysis_verdict(m.ASTATE_MISSING, "0", _AX_IDLE)[0] == "unknown"


def test_status_query_filters_expired_rows():
    """★TTL 필터가 빠지면 **멈춘 분석기의 낡은 행**이 「현재」로 읽힌다.

    `analyzer.py` 가 TTL 을 두는 이유가 바로 그것이다 — *«TTL 이 없으면 «분석기가
    멈췄다»가 낡은 값으로 남아 «정상»과 구별되지 않는다»*. 형제
    `test_alltime_query_has_no_window` 와 같은 축(질의의 창을 소스로 잠근다).
    """
    import re as _re
    src = PROBE.read_text(encoding="utf-8")
    m = _re.search(r"arow = \(await s\.execute\(text\(\s*(.*?)\)\s*,\s*\n", src, _re.DOTALL)
    assert m, "★분석상태 질의를 못 찾았다 — 락이 낡았다(공허한 초록 방지)"
    q = m.group(1)
    assert "platform_settings" in q, "★다른 표를 읽고 있다"
    assert "ttl_expires_at" in q, "★★TTL 필터가 없다 — 만료된 행을 현재로 읽는다"
    assert "is null" in q, "★TTL 없는 행(영구 플래그)이 통째로 빠진다"
    # ★대조군 — 워터마크 질의는 **의도적으로** TTL 필터가 없다(그 키는 TTL 이 없다).
    m2 = _re.search(r"wm = \(await s\.execute\(text\(\s*(.*?)\)\s*,\s*\n", src, _re.DOTALL)
    assert m2 and "ttl_expires_at" not in m2.group(1), "★두 질의가 같아졌다(축이 뭉개졌다)"


# ── ⑥ `starved` 가 **두 사실을 덮고 있었다**(독립 리뷰 2026-09-12 · MAJOR-1) ──────────
#    생산자 판정식은 `judged_total > 0` 만 본다 → `0/0`(입력 없음)과 `0/19`(하한 미달)이
#    **같은 `starved`** 로 나온다. 가르는 값(`total`)은 **이미 payload 에 실려 있다.**
#    ★이 파일이 고치려던 결함(답이 이미 있는데 판정이 안 읽는다)이 **한 층 안쪽**에 있었다.
def test_parse_axes_reads_both_spacings():
    """★생산자 원본(공백)과 프로브 출력(`_`)을 **같은 함수**로 읽는다."""
    m = _probe_mod()
    a = m.parse_axes("fal 0/0 lat 0/19")
    b = m.parse_axes("fal_0/0_lat_0/19")
    assert a == b == [("fal", 0, 0), ("lat", 0, 19)], (a, b)


def test_parse_axes_returns_empty_when_nothing_parses():
    """★못 읽으면 **빈 목록** — 0 으로 뭉치지 않는다(호출부가 「모른다」로 갈 수 있게)."""
    m = _probe_mod()
    assert m.parse_axes("") == []
    assert m.parse_axes("-") == []
    assert m.parse_axes("쓰레기 값") == []
    # ★대조군 — 정상 입력은 비면 안 된다(위 단언이 공허하지 않다).
    assert m.parse_axes("fal 1/2") == [("fal", 1, 2)]


def test_all_axes_zero_input_is_not_ok():
    """★★**모든 축의 입력이 0** 이면 「표본 부족」이 아니라 **수집 경로**다 — 기다려서 안 풀린다.

    ***사건 미발생이면 기다리면 되고, 장치 정지면 고쳐야 나온다*** — 겉보기엔 둘 다
    「데이터 없음」인데 **다음 행동이 다르다**(이 저장소가 2026-09-12 에 값을 치른 자리).
    """
    m = _probe_mod()
    kind, why = m.analysis_verdict("starved", "0", "fal 0/0 lat 0/0 qua 0/0")
    assert kind == "obs", (kind, why)
    assert "수집" in why, why
    # ★두 모집단 대조 — 입력이 있는 축이 하나라도 있으면 **다른 답**이어야 한다.
    other = m.analysis_verdict("starved", "0", "fal 0/0 lat 0/19 qua 0/0")
    assert other[0] == "ok", other
    assert other[1] != why, "두 모집단이 같은 사유를 낸다"


def test_starved_reason_no_longer_asserts_a_cause():
    """★★사유가 **관측보다 많이 말하지 않는다**.

    종전 문구: 「배치는 돌았고 **모든 축이 표본 하한 미달**이다 — 유휴이지 **고장이 아니다**」
    · 라이브 실측 `fal 0/0 lat 0/0 pay 0/1 qua 0/0` 에서 **전반부가 거짓**이다
      (`0/0` 축은 하한 미달이 아니라 입력이 없다)
    · 후반부(「고장이 아니다」)는 **재지 않은 진단**이다
    ***진단을 못 하는 자리에서 진단을 적으면 그게 다음 사람을 틀린 곳으로 보낸다.***
    """
    m = _probe_mod()
    _, why = m.analysis_verdict("starved", "0", "fal 0/0 lat 0/19")
    assert "고장이 아니다" not in why, why
    assert "모든 축이 표본 하한 미달" not in why, why
    # ★그리고 **관측은 실려야 한다** — 부정만 단언하면 사유를 통째로 지워도 통과한다.
    assert "0/0" in why and "0/19" in why, why


def test_unreadable_axes_under_starved_is_unknown_not_ok():
    """★축 요약을 못 읽으면 **가를 수 없다** — 「유휴」라고 부르지 않는다."""
    m = _probe_mod()
    assert m.analysis_verdict("starved", "0", "-")[0] == "unknown"
    assert m.analysis_verdict("starved", "0", None)[0] == "unknown"
    # ★대조군 — 읽히는 값에서는 unknown 이 아니어야 한다.
    assert m.analysis_verdict("starved", "0", "lat 0/19")[0] == "ok"


def test_dashboard_passes_axes_into_the_judge():
    """★배선 — 계기판이 `aaxes` 를 **실제로 넘긴다**(안 넘기면 위 판별이 전부 죽는다)."""
    out = subprocess.run(
        ["bash", "-c",
         f". '{SCRIPT}' --verdict-lib; analysis_verdict_of 'starved' '0' 'fal_0/0_lat_0/0'"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    assert out.startswith("obs|"), out
    out2 = subprocess.run(
        ["bash", "-c",
         f". '{SCRIPT}' --verdict-lib; analysis_verdict_of 'starved' '0' 'fal_0/0_lat_0/19'"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    assert out2.startswith("ok|"), out2


@pytest.mark.xfail(strict=True, reason=(
    "★부채: **일부 축만 입력 0** 인 상태를 판정하지 않는다. "
    "라이브가 정확히 그 상태다(fal 0/0 lat 0/0 pay 0/1 qua 0/0 — 넷 중 셋이 0). "
    "판정하려면 **시간 축**이 필요한데(하루 0 은 정상, 30일 0 은 아니다) "
    "`analysis_verdict` 는 지속 시간을 받지 않는다. "
    "★임계를 지어내면 굿하트가 그대로 재현된다 — 그래서 **판정하지 않고 사유에 싣기만** 한다. "
    "상환 조건: 스냅샷에 축별 마지막 입력 시각이 실리면 이 xfail 을 깬다."))
def test_partial_zero_input_is_judged():
    m = _probe_mod()
    assert m.analysis_verdict("starved", "0", "fal 0/0 lat 0/19")[0] == "obs"


# ── ⑦ 「안 쟀는데 이상 없음」 모양을 닫는다 (독립 리뷰 MINOR-1 · sid=e739d2a9) ─────
#    `--verdict-lib` 게이트를 **실행**으로 밟으면 종전엔 **출력 0바이트 · rc=0** 이었다.
#    이 파일의 계약에서 `0` 은 「모든 프로브 생존」인데 **그 실행은 아무것도 재지 않았다.**
def test_library_mode_executed_is_dead_not_clean():
    """★★실행 경로는 `3`(검사기 사망)이어야 한다 — `0`(이상 없음)이면 거짓말이다."""
    r = subprocess.run(["bash", str(SCRIPT), "--verdict-lib"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 3, f"rc={r.returncode} (0 이면 「안 쟀는데 깨끗함」)"
    # ★사유가 비면 「사유 없는 경보」다 — 이 PR 이 이미 한 번 데인 자리.
    assert len(r.stderr.strip()) >= 20, repr(r.stderr)
    assert "재지 않" in r.stderr, r.stderr
    # ★그리고 stdout 으로는 아무 판정도 흘리지 않는다(파이프로 읽는 소비자 보호).
    assert r.stdout.strip() == "", repr(r.stdout)


def test_library_mode_sourced_still_works():
    """★반대편 모집단 — source 경로는 **바뀌지 않아야** 한다(한쪽만 잠그면 반대쪽이 무제한)."""
    r = subprocess.run(
        ["bash", "-c",
         f". '{SCRIPT}' --verdict-lib; echo \"rc=$?\"; type -t analysis_verdict_of; type -t delta_verdict"],
        cwd=REPO, capture_output=True, text=True)
    assert "rc=0" in r.stdout, r.stdout
    assert r.stdout.count("function") == 2, r.stdout


def test_no_arg_run_is_not_the_library_gate():
    """★[공허 진리 가드] 인자 없는 실행은 **실제로 잰다** — 아니면 위 둘이 무의미하다.

    ★프로브·SSH 를 타므로 완주는 시키지 않는다. **계기판 머리글이 나오는지**만 본다
      (라이브러리 게이트로 빠지면 그 줄이 **없다**).
    """
    r = subprocess.run(["bash", "-c", f"timeout 25 bash '{SCRIPT}' 2>&1 | head -1"],
                       cwd=REPO, capture_output=True, text=True)
    assert "통합자 계기판" in r.stdout, repr(r.stdout[:200])


#: ★★**판정식 SSOT** — 프로덕션 락과 탐지 락이 **같은 것**을 써야 한다.
#:
#:   ★변이 실측(2026-09-12 R2b): 탐지 락 안에 같은 정규식을 **손으로 복사**해 뒀더니
#:     프로덕션 쪽(:527)만 약화해도 **SURVIVED** 였다(둘 다 약화해야 CAUGHT).
#:     ***나는 「사본이 갈리면 이 락이 장식이 된다」를 그 함수의 독스트링에 적고,
#:       같은 함수 안에서 사본을 만들었다.*** 적어 두는 것과 다음 줄에 지키는 것은 다른 축이다.
#:   ⇒ 한 곳에서 만들고 **양쪽이 호출**한다. 이걸 약화하면 **두 락이 함께** 빨개진다.
def _astate_assign_re(value: str | None = None):
    """셸의 `ASTATE=` **대입**을 잡는 정규식. `value` 를 주면 그 값까지 결속한다.

    ★`echo '…'` 같은 **표시 문구**는 계약이 아니라 대입만 본다(줄 시작 또는 `;`/`&`/`|` 뒤).
    ★따옴표는 `'` 와 `"` 를 **둘 다** 받는다 — 리팩토링이 계약을 안 바꾸면 빨개지면 안 된다.
    """
    import re as _re
    body = _re.escape(value) if value is not None else r"[^\'\"]*"
    return _re.compile(r"""(?:^|[;&|]\s*)ASTATE=(['"])""" + body + r"\1", _re.M)


# ── ⑧ ★셸 리터럴 ↔ 파이썬 상수 **계약**(독립 리뷰 2회가 각각 REQUEST CHANGES 를 냈다) ────
#    동료 세션(sid=e739d2a9)이 자기 PR 에서 찾은 형태를 제 코드에 대 보니 **같은 구멍**이었다:
#      *「락이 전부 **심볼**을 참조하면 값을 바꿔도 **양쪽이 함께 움직여 원리적으로 판별 불가**」*
#    ★**변이로 확인했다**: `ASTATE_MISSING = "(필드없음)"` → `"(no-field)"` 로 바꿔도 **SURVIVED**.
#      리터럴 입력(`("(필드없음)", …)`)조차 못 잡는다 — 값이 바뀌면 그 입력은 **폴백으로 떨어지는데
#      폴백도 `unknown`** 이라 kind 가 같기 때문이다. ***같은 답을 내는 두 경로는 서로를 가리지 못한다.***
#
#    ★★R2 — **초판 락이 두 리뷰에서 각각 뚫렸다.** 둘 다 이 PR 이 고치겠다고 선언한 클래스였다:
#      ① 주석은 배제했는데 **문자열은 안 배제**했다. 셸 리터럴을 바꾸고 `echo '…(필드없음)…'` 한 줄만
#         남기면 **SURVIVED**(계약은 깨져 있는데 초록). ★이 스크립트는 상태 문구를 찍는 것이 본업이라
#         안내문 추가는 **정상 변경**이다 — 억지 예가 아니다.
#      ② 「0건」 단언에 **대조군이 없었다.** 판정기를 `code = []` 로 **파괴해도 SURVIVED**.
#         같은 변이에 형제 락은 **CAUGHT** — 갈라 준 것은 오직 **대조군의 유무**였다.
#      ③ 형태 결속이 과했다: `ASTATE="{값}"` 정확 형태라 `ASTATE=\'…\'`·`${X:-"…"}` 로 리팩토링하면
#         **계약은 그대로인데 빨개진다**(위양성).
#    ⇒ 처방: **정본 `_scan_guard` 를 쓴다**(사본 금지). `assert_absent` 는 `positive_control`·`reason` 이
#      **필수 키워드 인자**라 ②가 **구조적으로 재발 불가**하고, 대조군 파괴는 `ScannerDeadError`,
#      진짜 위반은 `AssertionError` 로 **갈라서** 던진다.
#    ★그리고 **면역을 넓게 주장하지 않는다**: `code_lines()` 는 **줄 주석만** 걷어낸다(정본 독스트링 명문).
#      후행 주석·히어독·문자열은 **여전히 남는다** — 그래서 값 결속을 **대입 모양**으로 좁힌다.
def test_shell_literal_and_python_constant_are_one_contract():
    """★셸의 **대입**과 프로브의 상수가 같은 값이어야 한다(둘 다 소스에서 파생).

    ★`echo '…'` 같은 **표시 문구**는 계약이 아니다 — 대입만 본다.
      그래서 패턴을 «줄 시작/구분자 뒤의 `ASTATE=`» 로 좁히고, 따옴표는 **둘 다** 받는다
      (리팩토링 위양성 방지 · 리뷰 ③).
    """
    import re as _re

    # ★형제 관례를 따른다 — `tests._scan_guard` **패키지 임포트**
    #   (`test_coord_summary_contract.py:32` · `test_deploy_workflow_cannot_deadlock.py:61`)
    from tests import _scan_guard as sg   # ★정본을 쓴다(사본 금지 — 한계가 갈린다)

    probe = PROBE.read_text(encoding="utf-8")
    m = _re.search(r'^ASTATE_MISSING\s*=\s*"([^"]+)"', probe, _re.M)
    assert m, "★ASTATE_MISSING 선언을 못 찾았다 — 조회기가 죽었다(이름이 바뀌었나)"
    py_value = m.group(1)

    dash_code = sg.code_lines(SCRIPT.read_text(encoding="utf-8"))
    # 대입만 본다: 줄 시작 또는 `;`/`&&`/`||`/`&` 뒤 · 따옴표는 ' 와 " 둘 다
    values = [m.group(0).split("=", 1)[1][1:-1] for m in _astate_assign_re().finditer(dash_code)]
    assert values, (
        "★셸에서 `ASTATE=` **대입**을 하나도 못 찾았다 — 조회기 사망(패턴/파일 확인).\n"
        + "\n".join(ln for ln in dash_code.splitlines() if "ASTATE" in ln)[:400]
    )
    assert py_value in values, (
        f"★셸의 ASTATE 대입값 {values!r} 에 프로브 상수 {py_value!r} 가 없다 — "
        "값이 갈리면 «필드 없음」이 전용 사유를 잃고 폴백으로 **조용히 강등**된다"
    )


def test_absent_constant_is_not_silently_shadowed():
    """★형제 `ASTATE_ABSENT` 는 **프로브 안에서만** 쓰인다 — 셸에 새면 그것도 계약이 된다.

    ★부재 단언은 **대조군 없이 하지 않는다**(리뷰 ②). 정본 `assert_absent` 는
      `positive_control`·`reason` 이 **필수 키워드**라 대조군 없는 호출이 **문법적으로 불가능**하고,
      **대조군 파괴는 `ScannerDeadError`**, 진짜 위반은 `AssertionError` 로 갈라 던진다.
    ★한계(정직): `code_lines()` 는 **줄 주석만** 걷어낸다 — 후행 주석·히어독·문자열은 남는다.
      그래서 여기서도 **대입 모양**으로 좁혀 그 잔여를 줄인다.
    """
    import re as _re

    from tests import _scan_guard as sg

    probe = PROBE.read_text(encoding="utf-8")
    m = _re.search(r'^ASTATE_ABSENT\s*=\s*"([^"]+)"', probe, _re.M)
    assert m, "★ASTATE_ABSENT 선언을 못 찾았다 — 조회기가 죽었다"
    absent_value = m.group(1)

    dash_code = sg.code_lines(SCRIPT.read_text(encoding="utf-8"))
    sg.assert_absent(
        dash_code,
        pattern=_astate_assign_re(absent_value),
        # ★대조군 — 셸이 **실제로 하는** 대입. 이게 0건이면 조회기가 죽은 것이다.
        positive_control=_astate_assign_re(),
        reason=(f"★셸이 {absent_value!r} 를 직접 대입하기 시작했다 — 그러면 이것도 계약이므로 "
                "`test_shell_literal_and_python_constant_are_one_contract` 와 같은 락이 필요하다"),
        where="integrator_dashboard.sh",
    )

def test_the_absence_guard_actually_detects_a_violation():
    """★★**탐지 축** — 부재 단언은 「위반이 있으면 정말 터지는가」를 따로 잠가야 한다.

    ★변이 실측(2026-09-12 R2): `assert_absent` 의 **패턴만** 매칭 0 짜리로 약화하면
      **SURVIVED** 였다. `positive_control` 은 «조회기가 살아 있나」를 보지
      «내 패턴이 그 위반을 집는가」를 보지 **않는다** — 둘은 다른 축이다.
      ***특이도(위반 0)만 있고 탐지(위반이 있으면 터진다)가 없으면, 패턴이 죽어도 초록이다.***

    ⇒ **합성 위반**을 만들어 가드가 실제로 터지는지 태운다(저장소 §가드 3축: 탐지·특이도·배선).
    """
    import re as _re

    from tests import _scan_guard as sg

    probe = PROBE.read_text(encoding="utf-8")
    absent_value = _re.search(r'^ASTATE_ABSENT\s*=\s*"([^"]+)"', probe, _re.M).group(1)

    def _guard(text: str):
        """프로덕션 락과 **같은 패턴**을 쓴다 — 사본이 갈리면 이 락이 장식이 된다."""
        return sg.assert_absent(
            sg.code_lines(text),
            # ★★**사본을 만들지 않는다** — 프로덕션 락과 **같은 함수**를 부른다.
            #   사본이면 프로덕션 쪽만 약화해도 이 락이 초록이다(변이로 실측했다).
            pattern=_astate_assign_re(absent_value),
            positive_control=_astate_assign_re(),
            reason="합성 탐지 테스트",
        )

    # ① 위반이 있으면 **AssertionError** 로 터진다(탐지)
    violating = f'ASTATE="ok"\nASTATE="{absent_value}"\n'
    with pytest.raises(AssertionError) as ei:
        _guard(violating)
    assert not isinstance(ei.value, sg.ScannerDeadError), "★위반인데 「조회기 사망」으로 던졌다"

    # ② 위반이 없으면 **통과**한다(특이도 — 위양성도 결함이다)
    _guard('ASTATE="(필드없음)"\nASTATE="starved"\n')

    # ③ ★조회기가 죽으면 **다른 예외**로 갈라 던진다(0 과 뭉치지 않는다)
    with pytest.raises(sg.ScannerDeadError):
        _guard('echo "대입이 하나도 없다"\n')
