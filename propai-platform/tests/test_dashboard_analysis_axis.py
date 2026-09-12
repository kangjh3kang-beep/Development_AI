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
    reasons = [m.analysis_verdict(s, "0")[1] for s in inputs]
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
    dedicated = m.analysis_verdict(m.ASTATE_MISSING, "0")[1]
    generic = m.analysis_verdict("zzz_probe_control", "0")[1]
    # 폴백 템플릿을 «값만 바꾼」 형태로 재구성했을 때 전용 사유와 같으면 = 분기가 죽었다.
    faked = generic.replace("zzz_probe_control", m.ASTATE_MISSING)
    assert dedicated != faked, "★필드없음 분기가 폴백으로 떨어졌다(전용 설명이 없다)"
    assert m.analysis_verdict(m.ASTATE_MISSING, "0")[0] == "unknown"


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
