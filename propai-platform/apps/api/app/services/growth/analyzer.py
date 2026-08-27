"""자가성장 엔진 — 분석 규칙엔진(설계서 §5.1).

`analyze_window(db, window_start, window_end)` 가 platform_events / ai_feedback 를
스캔해 platform_insights 를 생성한다. **규칙 기반이 1차**, LLM narrative 는
선택적·비용가드(기본 off, 키 있고 critical 일 때만 1콜)다.

구현 규칙(DoD 3종 필수 + 보너스 1종):
- error_cluster : js_error/api_error 를 (정규화 스택해시·route·status) 로 group by,
                  top-N 빈발군. 동일 시그니처 ≥20건/시간 → warn, ≥100 → critical.
- fallback_rate : service별 fallback 이벤트 ÷ 총 llm_call. >15% → warn, >30% → critical.
- quality_drop  : service별 verify_result(fail/warn 비율) + ai_feedback(down 비율) 결합.
                  down>20% 또는 fail>15% → warn.
- latency_regression(보너스) : route/service p95 vs 직전 7일 baseline 1.5×.
                  baseline 은 platform_insights 에 저장해 다음 배치가 참조.

설계 §5.1 의 임계는 "초기값·자동보정 대상"이므로 상수로 한곳에 모은다.
판정·계산 로직은 stdlib 만으로 단위검증 가능하도록 순수 함수로 분리한다
(DB·LLM 의존 없는 _classify_*/_pXX 함수군).

결과는 platform_insights 에 INSERT(insight_type/window/metrics_json/severity/
narrative/recommended_action/status='open'). best-effort: 실패해도 배치는 죽지 않는다.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.utils.withheld import INSUFFICIENT_COVERAGE, is_withheld, withheld

logger = logging.getLogger(__name__)

# ── 임계값(설계 §5.1 초기값, 향후 L1 자동보정 대상) ───────────────────────────
# error_cluster: 동일 시그니처 시간당 건수 임계.
ERR_WARN_COUNT = 20
ERR_CRIT_COUNT = 100
ERR_TOP_N = 20  # 인사이트로 승격하는 상위 빈발군 수.

# recurring_verify_error: 동일 (service, issue_type) 시간당 검출 건수 임계.
# verify_issue 는 분석당 1회로 저빈도라 error_cluster(js/api)보다 낮은 임계를 쓴다.
VERIFY_ERR_WARN_COUNT = 3
VERIFY_ERR_CRIT_COUNT = 8
VERIFY_ERR_TOP_N = 10

# fallback_rate: service별 폴백률(%) 임계.
FALLBACK_WARN_PCT = 15.0
FALLBACK_CRIT_PCT = 30.0
FALLBACK_MIN_CALLS = 10  # 분모(llm_call)가 너무 작으면 노이즈 → 판정 보류.

# quality_drop: verify fail 비율 / feedback down 비율 임계(%).
QUALITY_DOWN_PCT = 20.0
QUALITY_FAIL_PCT = 15.0
QUALITY_MIN_SAMPLES = 5  # 표본이 너무 작으면 판정 보류.

# selection_contamination: 선택 오염 관측 빈도 임계(윈도우 내 건수).
# ★`malformed`(주소 칸에 소유자명 등 — 데이터가 깨짐)는 1건도 사람이 봐야 한다.
#   `multi_region`(원거리 혼합)은 **후보지 비교라는 정당한 워크플로우일 수 있어**
#   빈도가 쌓일 때만 알린다 — 이 캠페인의 핵심 결정이 "막지 말고 고지한다"였다.
CONTAM_MALFORMED_WARN_COUNT = 1
CONTAM_MULTI_REGION_INFO_COUNT = 3

# latency_regression: 직전 baseline 대비 배수.
LATENCY_REGRESSION_FACTOR = 1.5
LATENCY_MIN_SAMPLES = 20
LATENCY_BASELINE_DAYS = 7

# LLM narrative 비용가드: critical 인사이트 1배치당 최대 콜 수.
_LLM_NARRATIVE_MAX_CALLS = 3

# ── L1 자동보정 임계의 소비 배선(write-only dead-end 해소) ─────────────────────
# L1 자가수정(feature_flags.apply_threshold_autotune)이 platform_settings 에
# 'threshold.<이름>' 으로 기록한 값을 판정이 실제로 읽는다. 아래 매핑에 등록된
# 이름만 오버레이 대상(모듈상수 = 기본값·안전 폴백).
_TUNABLE_THRESHOLDS: dict[str, float] = {
    "fallback_warn_pct": FALLBACK_WARN_PCT,
    "fallback_crit_pct": FALLBACK_CRIT_PCT,
    "contam_malformed_warn_count": CONTAM_MALFORMED_WARN_COUNT,
    "contam_multi_region_info_count": CONTAM_MULTI_REGION_INFO_COUNT,
}

# 배치 시작 시 캐시에 미리 채울 동적설정 키(임계 + 피처토글).
_DYNAMIC_PRIME_KEYS = (
    *(f"threshold.{name}" for name in _TUNABLE_THRESHOLDS),
    "feature.llm_narrative",
)


def _effective_threshold(name: str, default: float | None = None) -> float:
    """실효 임계값 = 모듈상수 기본값 위에 platform_settings('threshold.<name>') 오버레이.

    sync·캐시 전용 읽기(DB 무접근)라 순수 판정 함수에서 그대로 호출 가능하다.
    캐시가 비어 있으면(프라임 전·단위테스트) 모듈상수 그대로 → stdlib 단독 검증성 유지.
    analyze_window 가 시작 시 _prime_dynamic_config 로 캐시를 채워 두면 그때부터
    L1 자동보정 값이 판정 기준이 된다(설정값 누적수렴의 소비 지점).
    """
    base = default if default is not None else _TUNABLE_THRESHOLDS.get(name, 0.0)
    try:
        from app.services.growth import dynamic_config

        return dynamic_config.as_float(
            dynamic_config.get_cached(f"threshold.{name}"), base
        )
    except Exception:  # noqa: BLE001 — 오버레이 실패는 기본값(판정 비차단).
        return base


async def _prime_dynamic_config(db=None) -> None:
    """분석 배치 시작 시 동적설정을 TTL 캐시에 프라임(이후 판정은 sync 캐시 읽기).

    best-effort: 실패해도 판정은 모듈상수 기본값으로 진행(배치 비차단).
    """
    try:
        from app.services.growth import dynamic_config

        for key in _DYNAMIC_PRIME_KEYS:
            await dynamic_config.get_dynamic(key, db=db)
    except Exception as e:  # noqa: BLE001
        logger.debug("동적설정 프라임 생략: %s", str(e)[:120])

# 스택트레이스 정규화에서 제거할 변동요소(주소·숫자ID·hex 등).
_RE_HEX = re.compile(r"0x[0-9a-fA-F]+")
_RE_NUM = re.compile(r"\b\d+\b")
_RE_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_RE_WS = re.compile(r"\s+")


# ════════════════════════════════════════════════════════════════════════════
# 순수 함수군 (DB/LLM 무의존 — inline 단위검증 대상)
# ════════════════════════════════════════════════════════════════════════════

def normalize_stack(raw: str | None, route: str | None, status: int | None) -> str:
    """스택트레이스/에러메시지를 변동요소 제거 후 시그니처 해시로 정규화한다.

    같은 결함이 호출마다 다른 주소·라인숫자·UUID 를 갖더라도 동일 시그니처로
    묶이도록, hex/숫자/UUID 를 placeholder 로 치환한 뒤 route·status 와 함께
    sha1 12자리 해시를 만든다.
    """
    base = raw or ""
    base = _RE_UUID.sub("<uuid>", base)
    base = _RE_HEX.sub("<hex>", base)
    base = _RE_NUM.sub("<n>", base)
    base = _RE_WS.sub(" ", base).strip().lower()
    # 메시지가 비면 route+status 만으로 군집(엔드포인트 단위 오류).
    key = f"{base}|{route or ''}|{status if status is not None else ''}"
    # ★보안 해시가 아니다 — 12자로 잘라 쓰는 **집계 캐시키**다(충돌해도 통계가 합쳐질 뿐).
    return hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _classify_error_count(count: int) -> str | None:
    """동일 시그니처 시간당 건수 → severity. 임계 미만이면 None."""
    if count >= ERR_CRIT_COUNT:
        return "critical"
    if count >= ERR_WARN_COUNT:
        return "warn"
    return None


def _classify_verify_recurrence(count: int) -> str | None:
    """동일 (service, issue_type) 시간당 검출 건수 → severity. 임계 미만이면 None."""
    if count >= VERIFY_ERR_CRIT_COUNT:
        return "critical"
    if count >= VERIFY_ERR_WARN_COUNT:
        return "warn"
    return None


def _cluster_verify_issues(
    rows: list[tuple[Any, dict[str, Any], Any]], hours: float
) -> list[dict[str, Any]]:
    """verify_issue 이벤트[(service, payload, created_at)] → 재발오류 인사이트 목록(순수·무DB).

    payload.issue_types(리스트)를 평탄화해 (service, issue_type)별로 군집·집계한다.
    severity는 총 검출빈도(per_hour) 기준으로 산정하며, high_count(severities[idx]가
    high/critical인 건수)는 metrics·narrative 표기용(심각도 가시화)이다. 임계 미만은 제외.
    """
    clusters: dict[tuple[str, str], dict[str, Any]] = {}
    for service, payload, _created in rows:
        types = (payload or {}).get("issue_types") or []
        sevs = (payload or {}).get("severities") or []
        if not isinstance(types, list):
            continue
        for idx, t in enumerate(types):
            key = (str(service or "?"), str(t))
            c = clusters.setdefault(key, {
                "service": key[0], "issue_type": key[1], "count": 0, "high": 0,
            })
            c["count"] += 1
            sev_i = sevs[idx] if isinstance(sevs, list) and idx < len(sevs) else None
            if sev_i in ("high", "critical"):
                c["high"] += 1

    out: list[dict[str, Any]] = []
    ranked = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)[:VERIFY_ERR_TOP_N]
    for c in ranked:
        per_hour = c["count"] / hours
        sev = _classify_verify_recurrence(int(round(per_hour)))
        if sev is None:
            continue
        out.append({
            "insight_type": "recurring_verify_error",
            "severity": sev,
            "tenant_id": None,
            "recommended_action": "propose_pr" if sev == "critical" else "none",
            "metrics_json": {
                "service": c["service"], "issue_type": c["issue_type"],
                "count": c["count"], "per_hour": round(per_hour, 2),
                "high_count": c["high"],
            },
        })
    return out


def _classify_contamination(verdict: str, count: int) -> str | None:
    """선택 오염 관측 빈도 → severity. 임계 미만이면 None(인사이트 미발행).

    ★**`multi_region` 은 절대 `warn` 이상으로 올라가지 않는다.** 이 캠페인이 실측으로
      내린 결정이 *"막지 말고 고지한다"* 였다 — 원거리 필지 묶음은 **후보지 비교**라는
      정당한 워크플로우일 수 있다(라이브 290km 건이 그렇게 보인다). 여기서 severity 를
      올리면 자가치유 루프가 정상 사용을 "고칠" 대상으로 오인할 길이 열린다.
      정상 사용을 결함으로 세는 지표는 **지표가 아니라 소음**이다.

    ★`malformed` 은 다르다 — 주소 칸에 소유자명(`◀ 전성결`)이 들어온 것은 **데이터가
      깨진 것**이라 1건도 사람이 봐야 한다.
    """
    if verdict == "malformed":
        if count >= _effective_threshold(
            "contam_malformed_warn_count", CONTAM_MALFORMED_WARN_COUNT
        ):
            return "warn"
        return None
    if verdict == "multi_region":
        if count >= _effective_threshold(
            "contam_multi_region_info_count", CONTAM_MULTI_REGION_INFO_COUNT
        ):
            return "info"
        return None
    # 모르는 verdict 는 판정하지 않는다(수집 엔드포인트는 익명 허용 — 임의 값이 올 수 있다).
    return None


def note_coverage(
    # ★값 타입이 int 만이 아니다 — `judged_pct`(float|None) · `state`(str) 가 함께 들어간다.
    #   종전 `dict[str, int]` 는 거짓이었고 tsc 도 mypy 도 이 자리를 안 봤다.
    coverage: dict[str, dict[str, Any]] | None,
    axis: str, *, judged: int, withheld_count: int, floor: int,
) -> None:
    """이번 분석에서 **몇 개를 판정했고 몇 개를 표본 부족으로 보류했는지** 적는다.

    ## 왜 (라이브 실측 2026-08-26T09:0xZ · 활성 컨테이너)

        latency  키 **825개 중 802개(97%)** 가 표본 하한 미달로 `continue` 되어
                 **행 자체가 사라진다**(이벤트 1,243/3,893)
        fallback 서비스 **5개 전부**(permit·regulation·scenario·site_analysis·verifier)
                 가 하한 미달 → 인사이트 **0건**

    세 자리의 주석은 이미 *"판정 보류"* 라고 **말하고 있었다**. 없던 것은 그 보류가
    **어디에도 남지 않는다**는 사실이다 — 보는 사람은 *"문제가 없었다"* 와
    *"판정할 표본이 없었다"* 를 **구별할 수 없다**.

    ★선례를 그대로 쓴다 — `site_score_service` 의 `GRADE_COVERAGE_FLOOR` 는
      값을 `None` 으로 두고 사유를 문구로 말하며 **발행했을 때도 `covered/total` 을
      항상 싣는다**. 새 설계가 아니라 **의도-구현 격차**를 메우는 것이다.

    ★**행을 새로 만들지 않는다.** 802개를 보류 행으로 발행하면 소음이 늘 뿐이다
      (현재 재고 3,127건 중 `latency_regression` 이 이미 2,308건). 대신
      `run_analysis` 가 **모든 인사이트**에 이 값을 박고, 인사이트가 **0건일 때도**
      로그로 남긴다.
    """
    if coverage is None:
        return
    total = judged + withheld_count
    #: ★판정률의 정의 — **「모든 축이 무언가를 말한다」** 가 100% 다.
    #  `judged_pct` 는 *"임계로 분류할 수 있었던 비율"* 이라 **트래픽이 적으면 영원히 100%
    #  가 못 된다**. 트래픽이 적은 것은 결함이 아니다(라이브 실측: LLM 호출 자체가 적다).
    #  `coverage_pct` 는 *"판정했거나 **왜 판정 못 하는지 말했거나**"* 의 비율이다.
    #  ★둘 다 싣는다 — 한 수로 뭉개면 `coverage_pct=100` 이 *"다 판정했다"* 로 오독된다.
    #: 판정률 — **임계로 분류한** 비율. `total==0`(축이 안 돎)이면 **`None`**:
    #  0.0 으로 두면 *"판정률 0%"* 가 되어 **축이 안 도는 것을 결함으로 오독**시킨다.
    judged_pct = round(100.0 * judged / total, 1) if total else None
    #: 축이 아예 안 돈 것(`total==0`)과 표본이 부족한 것(`withheld_count>0`)은 **다른 사실**이다.
    #  종전엔 둘 다 `judged=0` 이라 뭉개졌다. 이 세 값이 그 구분을 나른다.
    #
    #  ★**`coverage_pct` 는 넣지 않는다** — 독립 적대 리뷰(2026-08-27)가 반증했다.
    #    `100.0 if total else None` 은 `total>0` 인 모든 입력에서 **상수 100.0** 이고,
    #    유일한 비상수 거동(`total==0` → `None`)은 `state=="axis_idle"` 와 **완전 중복**이라
    #    독립 정보량이 0이다. 계획서의 식 `(judged + withheld_reported)/total` 에서
    #    `withheld_reported`(보류의 인사이트 승격)가 **이 PR 에 없으므로** 그 식은 아직
    #    성립하지 않는다. **소비처 0인 상수를 싣지 않는다.**
    state = "axis_idle" if total == 0 else ("judged" if withheld_count == 0 else "partial")
    coverage[axis] = {
        # ★발행 키는 `withheld` 그대로다 — 이건 `metrics_json.analysis_coverage` 의
        #   **계약**이라 개명하면 화면·API·기존 재고 행과 어긋난다. 파라미터만 바꿨다.
        "judged": judged, "withheld": withheld_count,
        "total": total, "floor": floor,
        "judged_pct": judged_pct,
        "state": state,
    }


def _classify_fallback(fallback: int, total_calls: int) -> tuple[str | None, float]:
    """폴백률(%) 산출 + severity. 분모 부족 시 (None, pct).

    임계는 모듈상수가 아니라 실효값(_effective_threshold — L1 자동보정 오버레이)을
    읽는다. 캐시가 비어 있으면 모듈상수 그대로(순수 검증성 유지).
    """
    if total_calls < FALLBACK_MIN_CALLS:
        return None, 0.0
    pct = round(100.0 * fallback / total_calls, 2)
    crit_pct = _effective_threshold("fallback_crit_pct", FALLBACK_CRIT_PCT)
    # warn 이 crit 위로 자동보정되는 역전 방지(항상 warn ≤ crit).
    warn_pct = min(_effective_threshold("fallback_warn_pct", FALLBACK_WARN_PCT), crit_pct)
    if pct > crit_pct:
        return "critical", pct
    if pct > warn_pct:
        return "warn", pct
    return None, pct


def _classify_quality(
    fail: int, warn: int, verify_total: int, down: int, feedback_total: int
) -> tuple[str | None, dict[str, Any]]:
    """verify fail 비율 + feedback down 비율 결합 → severity.

    down>20% 또는 fail>15% → warn. 표본 부족(둘 다 MIN 미만)이면 None.

    ## ★한 번도 재지 않은 축을 **0.0 으로 발행하지 않는다** (2026-08-26 독립 리뷰 적발)

    종전엔 `if verify_total else 0.0` 이라 **verify 표본이 0건인데 `fail_pct=0.0`** 이
    나갔다. 그 행은 `severity='warn'` 으로 **실제 발행돼 화면까지 간다**:

        _classify_quality(fail=1, warn=0, verify_total=5, down=0, feedback_total=0)
          → ('warn', {'fail_pct': 20.0, 'warn_pct': 0.0, 'down_pct': **0.0**})
            ★feedback 을 한 번도 안 쟀는데 "down 0%" 라고 말한다

    *"재 보니 0%"* 와 *"잴 표본이 없었다"* 는 **다른 사실**이다. 저장소 표준 보류 계약
    (`utils/withheld.py` · 닫힌 어휘 `INSUFFICIENT_COVERAGE`)으로 값을 `None` 으로 두고
    **사유를 함께 싣는다** — 그래야 `tests/test_withheld_value_contract.py` 의 파생형
    전역 스윕이 이 생산자도 자동으로 센다.

    ★소비처 안전(실측): `feature_flags.py:480` 이 `float(m.get("down_pct") or 0.0)` 로
      읽으므로 `None` 이 와도 죽지 않고, **미측정이 비활성 트리거가 되지 않는** 쪽으로
      의미가 정확해진다.
    """
    enough_verify = verify_total >= QUALITY_MIN_SAMPLES
    enough_feedback = feedback_total >= QUALITY_MIN_SAMPLES

    metrics: dict[str, Any] = {}
    if enough_verify:
        metrics["fail_pct"] = round(100.0 * fail / verify_total, 2)
        metrics["warn_pct"] = round(100.0 * warn / verify_total, 2)
    else:
        _why = (f"판정 보류 — verify 표본 {verify_total}건으로 최소 "
                f"{QUALITY_MIN_SAMPLES}건에 미달합니다(미측정이며 0% 가 아닙니다).")
        metrics.update(withheld(INSUFFICIENT_COVERAGE, _why, field="fail_pct"))
        metrics.update(withheld(INSUFFICIENT_COVERAGE, _why, field="warn_pct"))
    if enough_feedback:
        metrics["down_pct"] = round(100.0 * down / feedback_total, 2)
    else:
        metrics.update(withheld(
            INSUFFICIENT_COVERAGE,
            f"판정 보류 — feedback 표본 {feedback_total}건으로 최소 "
            f"{QUALITY_MIN_SAMPLES}건에 미달합니다(미측정이며 0% 가 아닙니다).",
            field="down_pct",
        ))

    fail_pct = metrics.get("fail_pct") or 0.0
    down_pct = metrics.get("down_pct") or 0.0

    if not enough_verify and not enough_feedback:
        return None, metrics

    severity: str | None = None
    if (enough_feedback and down_pct > QUALITY_DOWN_PCT) or (
        enough_verify and fail_pct > QUALITY_FAIL_PCT
    ):
        severity = "warn"
    return severity, metrics


def _percentile(values: list[float], pct: float) -> float:
    """단순 백분위(보간 없는 nearest-rank). p95 등 baseline 산출용."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[rank]


def _classify_latency(p95: float, baseline_p95: float) -> str | None:
    """현재 p95 가 baseline 의 1.5배 초과면 warn. baseline 없으면 None(첫 배치)."""
    if baseline_p95 <= 0:
        return None
    if p95 > baseline_p95 * LATENCY_REGRESSION_FACTOR:
        return "warn"
    return None


#: baseline 을 읽어 올 insight_type 들.
#  ★`latency_regression` 을 반드시 포함한다 — 2026-08-23 이전 데이터(2,059건)가 그 타입이라
#    빼면 baseline 이 0 이 되어 `_classify_latency` 가 **영원히 None**(회귀 미탐지)이 된다.
from app.services.growth import stale_build_guard  # noqa: E402  (생산자 표식용)

LATENCY_BASELINE_SOURCE_TYPES = ("latency_regression", "latency_baseline")


def insight_type_for_latency(sev: str | None) -> str:
    """회귀면 `latency_regression`, 아니면 `latency_baseline`.

    ★왜 나누나(2026-08-23 실측): baseline 저장소로 insights 테이블을 재사용한 탓에
      **회귀가 없어도** 매 배치마다 모든 route 에 행이 쌓였다 — `latency_regression`
      2,059건 중 최신 6건이 전부 `p95_ms == baseline_p95`(회귀 아님)였고,
      `status=open` 2,248건이 실제 조치 대상(critical 57 + warn 352)을 가렸다.
      **"사람이 볼 것"과 "기계가 참조할 것"을 타입으로 가른다.**
    """
    return "latency_regression" if sev else "latency_baseline"


def _severity_rank(sev: str | None) -> int:
    """정렬용 severity 가중치(critical 최상위)."""
    return {"critical": 3, "warn": 2, "info": 1}.get(sev or "", 0)


# ════════════════════════════════════════════════════════════════════════════
# DB 스캔 + 인사이트 생성
# ════════════════════════════════════════════════════════════════════════════

async def analyze_window(
    db, window_start: datetime, window_end: datetime, *, use_llm: bool | None = None
) -> list[dict[str, Any]]:
    """윈도우 내 platform_events/ai_feedback 를 스캔해 인사이트를 생성·INSERT.

    반환: 생성한 인사이트 dict 목록(테스트·로깅용). best-effort.
    """
    from sqlalchemy import text

    # L1 자동보정 임계·피처토글을 캐시에 프라임 → 이하 판정이 실효값을 소비.
    await _prime_dynamic_config(db)

    insights: list[dict[str, Any]] = []
    # ★표본 하한으로 **판정하지 못한 것**을 세어 둔다 — 아래에서 모든 인사이트에 박고,
    #   인사이트가 0건이어도 로그로 남긴다(라이브 실측: latency 키의 97%가 여기 해당).
    coverage: dict[str, dict[str, Any]] = {}
    try:
        insights.extend(await _analyze_error_cluster(db, window_start, window_end))
        insights.extend(await _analyze_recurring_verify_errors(db, window_start, window_end))
        insights.extend(await _analyze_fallback_rate(db, window_start, window_end, coverage))
        insights.extend(await _analyze_selection_contamination(db, window_start, window_end))
        insights.extend(await _analyze_quality_drop(db, window_start, window_end, coverage))
        insights.extend(await _analyze_latency_regression(db, window_start, window_end, coverage))
    except Exception as e:  # noqa: BLE001 — 스캔 실패는 배치를 죽이지 않는다.
        logger.warning("growth analyze 스캔 실패: %s", str(e)[:160])
        return insights

    # narrative: 규칙 기반이 기본. critical 인사이트에 한해 비용가드 LLM 1콜.
    do_llm = _llm_enabled() if use_llm is None else use_llm
    llm_budget = _LLM_NARRATIVE_MAX_CALLS if do_llm else 0
    for ins in insights:
        narrative = _rule_narrative(ins)
        if llm_budget > 0 and ins.get("severity") == "critical":
            llm_narr = _llm_narrative(ins)
            if llm_narr:
                narrative = llm_narr
                llm_budget -= 1
        ins["narrative"] = narrative

    # INSERT(개별 best-effort — 한 건 실패가 전체를 막지 않게 커밋은 마지막 일괄).
    inserted = 0
    insert_sql = text(
        "INSERT INTO platform_insights "
        "(tenant_id, insight_type, window_start, window_end, metrics_json, "
        " severity, narrative, recommended_action, status) "
        "VALUES (:tenant_id, :insight_type, :window_start, :window_end, "
        " CAST(:metrics_json AS jsonb), :severity, :narrative, "
        " :recommended_action, 'open')"
    )
    try:
        for ins in insights:
            await db.execute(insert_sql, {
                "tenant_id": ins.get("tenant_id"),
                "insight_type": ins["insight_type"],
                "window_start": window_start,
                "window_end": window_end,
                # ★생산자 표식(2026-08-25) — 어느 빌드가 이 행을 썼는지 남긴다.
                #   왜: 낡은 스택이 병렬로 쓴 129건을 특정하는 데 **created_at 초 단위
                #   지문**을 써야 했다(158 배치는 분 :15~:20, 168 은 :05/:30). 그 우회는
                #   다음 사람이 못 한다. ★특정 타입만이 아니라 **모든 인사이트**에 박는다 —
                #   타입별 손수 분기는 새 타입을 자동으로 누락시킨다.
                "metrics_json": json.dumps(
                    {**(ins.get("metrics_json") or {}),
                     "producer_build_id": stale_build_guard.running_build_id(),
                     # ★생산자 표식과 **같은 자리**에 박는다 — 이 자리의 주석이 이미
                     #   "타입별 손수 분기는 새 타입을 자동으로 누락시킨다"고 말한다.
                     #   커버리지도 같은 이유로 전 타입에 박는다.
                     "analysis_coverage": coverage},
                    ensure_ascii=False, default=str,
                ),
                "severity": ins.get("severity"),
                "narrative": ins.get("narrative"),
                "recommended_action": ins.get("recommended_action") or "none",
            })
            inserted += 1
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("growth insight INSERT 실패(%d/%d): %s",
                       inserted, len(insights), str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()

    # ★종전엔 `if insights:` 라 **0건인 실행이 아무 로그도 남기지 않았다** — 배치가
    #   돌지 않은 것과 구별이 안 됐다. 커버리지는 **0건일 때가 가장 중요하다**
    #   (라이브: fallback 은 서비스 5개 전부 하한 미달이라 인사이트가 0건이다).
    logger.info(
        "growth analyze: 인사이트 %d건 생성(INSERT %d) · 커버리지 %s",
        len(insights), inserted,
        {k: f"{v['judged']}/{v['total']}(하한 {v['floor']})" for k, v in coverage.items()}
        or "축 없음",
    )
    return insights


async def _analyze_error_cluster(db, w0, w1) -> list[dict[str, Any]]:
    """js_error/api_error 를 정규화 시그니처로 군집해 빈발 top-N 을 인사이트화."""
    from sqlalchemy import text

    rows = (await db.execute(text(
        "SELECT route, status_code, severity, payload, created_at "
        "FROM platform_events "
        "WHERE event_type IN ('js_error','api_error') "
        "  AND created_at >= :w0 AND created_at < :w1"
    ), {"w0": w0, "w1": w1})).fetchall()

    # 시간 정규화 계수: 윈도우가 1시간이 아니면 "시간당 건수"로 환산해 임계 비교.
    hours = max((w1 - w0).total_seconds() / 3600.0, 1e-9)

    clusters: dict[str, dict[str, Any]] = {}
    for r in rows:
        payload = _as_dict(r[3])
        raw = (payload.get("message") or payload.get("stack")
               or payload.get("error") or "")
        sig = normalize_stack(str(raw), r[0], r[1])
        c = clusters.setdefault(sig, {
            "signature": sig, "route": r[0], "status": r[1],
            "count": 0, "sample": str(raw)[:300],
        })
        c["count"] += 1

    out: list[dict[str, Any]] = []
    ranked = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)[:ERR_TOP_N]
    for c in ranked:
        per_hour = c["count"] / hours
        sev = _classify_error_count(int(round(per_hour)))
        if sev is None:
            continue
        out.append({
            "insight_type": "error_cluster",
            "severity": sev,
            "tenant_id": None,
            "recommended_action": "propose_pr" if sev == "critical" else "none",
            "metrics_json": {
                "signature": c["signature"], "route": c["route"],
                "status_code": c["status"], "count": c["count"],
                "per_hour": round(per_hour, 2), "sample": c["sample"],
            },
        })
    return out


async def _analyze_recurring_verify_errors(db, w0, w1) -> list[dict[str, Any]]:
    """verify_issue 를 (service, issue_type) 로 군집해 반복 검출 오류를 인사이트화.

    verifier 가 자동 검출한 오류 '유형'이 특정 분석에서 반복되면 재발오류로 승격(개선 대상).
    capture(_emit_growth_issues)가 적재한 verify_issue 를 소비하는 폐루프의 분석 단계.
    """
    from sqlalchemy import text

    rows = (await db.execute(text(
        "SELECT service, payload, created_at FROM platform_events "
        "WHERE event_type='verify_issue' AND created_at >= :w0 AND created_at < :w1"
    ), {"w0": w0, "w1": w1})).fetchall()
    hours = max((w1 - w0).total_seconds() / 3600.0, 1e-9)
    parsed = [(r[0], _as_dict(r[1]), r[2]) for r in rows]
    return _cluster_verify_issues(parsed, hours)


async def _analyze_fallback_rate(db, w0, w1, coverage: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """service별 폴백률 인사이트.

    분자(fallback): base_interpreter 는 LLM 호출 실패 시 별도 'fallback' 이벤트를
    발행하지 않고 event_type='llm_call' + payload.ok=false 로 기록한다(설계 정합).
    따라서 폴백 건수 = (event_type='fallback' 이벤트) + (llm_call 중 payload->>'ok'='false').
    분모(llm_call): service별 총 llm_call 수(성공/실패 모두 포함).
    """
    from sqlalchemy import text

    rows = (await db.execute(text(
        "SELECT service, "
        "  SUM(CASE WHEN event_type='fallback' THEN 1 "
        "           WHEN event_type='llm_call' AND payload->>'ok'='false' THEN 1 "
        "           ELSE 0 END) AS fb, "
        "  SUM(CASE WHEN event_type='llm_call' THEN 1 ELSE 0 END) AS calls "
        "FROM platform_events "
        "WHERE event_type IN ('fallback','llm_call') "
        "  AND created_at >= :w0 AND created_at < :w1 "
        "  AND service IS NOT NULL "
        "GROUP BY service"
    ), {"w0": w0, "w1": w1})).fetchall()

    # ★사유 분포 — 같은 창에서 (service, reason) 로 센다.
    #   왜 새 인사이트 타입을 만들지 않았나: **비율과 사유는 같은 자리에 있어야** 판단이 된다.
    #   "80.77% 폴백"만으로는 절단인지 타임아웃인지 스키마 위반인지 모르고, 그 셋은 처방이 다르다.
    #   타입을 늘리면 카탈로그·대시보드가 따라와야 하는데 얻는 것이 없다.
    #   ★`reason` 이 없는 옛 이벤트는 `unlabeled` 로 센다 — 0으로 감추면 분포가 거짓이 된다.
    reason_rows = (await db.execute(text(
        "SELECT service, COALESCE(NULLIF(payload->>'reason',''), 'unlabeled') AS reason, "
        "  COUNT(*) AS n "
        "FROM platform_events "
        "WHERE created_at >= :w0 AND created_at < :w1 AND service IS NOT NULL "
        "  AND (event_type='fallback' "
        "       OR (event_type='llm_call' AND payload->>'ok'='false')) "
        "GROUP BY service, reason"
    ), {"w0": w0, "w1": w1})).fetchall()

    by_service: dict[str, dict[str, int]] = {}
    for svc, reason, n in reason_rows:
        by_service.setdefault(svc, {})[str(reason)] = int(n or 0)

    out: list[dict[str, Any]] = []
    judged = withheld = 0
    for r in rows:
        service, fb, calls = r[0], int(r[1] or 0), int(r[2] or 0)
        # ★판정 가능 여부를 **분류 결과가 아니라 표본으로** 센다 — `sev is None` 은
        #   "표본 부족"과 "표본 충분하고 정상"을 뭉갠다(둘 다 None 이다).
        if calls < FALLBACK_MIN_CALLS:
            withheld += 1
        else:
            judged += 1
        sev, pct = _classify_fallback(fb, calls)
        if sev is None:
            continue
        reasons = dict(sorted(by_service.get(service, {}).items(),
                              key=lambda kv: (-kv[1], kv[0])))
        top = next(iter(reasons), None)
        out.append({
            "insight_type": "fallback_rate",
            "severity": sev,
            "tenant_id": None,
            "recommended_action": "heal",
            "metrics_json": {
                "service": service, "fallback": fb,
                "llm_call": calls, "fallback_pct": pct,
                # 사유별 건수(많은 순) + 최다 사유. 개선 착수 지점을 이 두 값이 정한다.
                "reasons": reasons, "top_reason": top,
            },
        })
    note_coverage(coverage, "fallback_rate", judged=judged, withheld_count=withheld,
                  floor=FALLBACK_MIN_CALLS)
    return out


# 선택 오염 집계 SQL — 모듈 상수로 둬서 테스트가 **런타임 문자열**을 검사할 수 있게 한다.
# ★파이썬 이스케이프가 한 번 더 먹으면 정규식이 조용히 안 맞고, 그러면 숫자꼴 판정이
#   전부 거짓이 되어 `max_spread_km` 이 **항상 NULL** 이 된다(빈 지표인데 초록).
_CONTAM_SQL = (
    "SELECT payload->>'verdict' AS verdict, COUNT(*) AS n, "
    # 숫자꼴만 캐스팅 — 수집 엔드포인트가 익명 허용이라 임의 문자열이 올 수 있다.
    r"  MAX(CASE WHEN payload->>'spread_km' ~ '^[0-9]+(\.[0-9]+)?$' "
    "           THEN (payload->>'spread_km')::numeric END) AS max_spread, "
    "  SUM(CASE WHEN payload->>'malformed_rows' ~ '^[0-9]+$' "
    "           THEN (payload->>'malformed_rows')::int ELSE 0 END) AS malformed_rows "
    "FROM platform_events "
    "WHERE event_type='selection_contamination_observation' "
    "  AND created_at >= :w0 AND created_at < :w1 "
    # 아는 verdict 만 — 임의 값이 카디널리티를 늘리지 못하게 한다.
    "  AND payload->>'verdict' IN ('multi_region','malformed') "
    "GROUP BY 1"
)


async def _analyze_selection_contamination(db, w0, w1) -> list[dict[str, Any]]:
    """선택 오염 관측(`selection_contamination_observation`)을 verdict 별로 집계한다.

    이 이벤트는 프론트(`lib/growth/selection-contamination.ts`)가 다필지 선택이
    "하나의 개발 부지"가 아닐 때 보낸다. 화면은 이미 고지하고 있었지만 **빈도는
    아무도 몰랐다** — 빈도를 모르면 "이미 오염된 프로젝트를 정리할지"를 근거 없이
    결정하게 된다. 여기서 그 빈도를 사람이 보는 인사이트로 만든다.

    ★**숫자 캐스팅을 방어적으로 한다.** 수집 엔드포인트(`POST /growth/events`)는
      **익명 허용**이라 `spread_km` 에 숫자가 아닌 값이 들어올 수 있다. 그대로
      `::numeric` 하면 예외가 나고, `analyze_window` 의 광역 except 가 그것을 삼켜
      **그 윈도우의 인사이트가 전부 사라진다**(내 지표가 남의 지표를 죽인다).
      숫자꼴일 때만 캐스팅한다.
    """
    from sqlalchemy import text

    rows = (await db.execute(
        text(_CONTAM_SQL), {"w0": w0, "w1": w1}
    )).fetchall()

    out: list[dict[str, Any]] = []
    for r in rows:
        verdict, n = r[0], int(r[1] or 0)
        sev = _classify_contamination(verdict, n)
        if sev is None:
            continue
        out.append({
            "insight_type": "selection_contamination",
            "severity": sev,
            "tenant_id": None,
            # ★**자동조치 금지** — 원거리 묶음은 정당할 수 있고, 깨진 행은 소유자 정보가
            #   유실될 수 있어 임의 삭제가 금지돼 있다. 사람이 본다.
            "recommended_action": "none",
            "metrics_json": {
                "verdict": verdict,
                "count": n,
                # 좌표가 없으면 **미상이지 0이 아니다**(무좌표 프로젝트가 실재한다).
                "max_spread_km": float(r[2]) if r[2] is not None else None,
                "malformed_rows": int(r[3] or 0),
            },
        })
    return out


async def _analyze_quality_drop(db, w0, w1, coverage: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """service별 verify_result(fail/warn) + ai_feedback(down) 결합 품질저하 인사이트."""
    from sqlalchemy import text

    # verify_result: severity 또는 payload.verdict 에 fail/warn 기록(수집측 정합).
    verify_rows = (await db.execute(text(
        "SELECT service, severity, payload FROM platform_events "
        "WHERE event_type='verify_result' "
        "  AND created_at >= :w0 AND created_at < :w1 AND service IS NOT NULL"
    ), {"w0": w0, "w1": w1})).fetchall()

    fb_rows = (await db.execute(text(
        "SELECT service, "
        "  SUM(CASE WHEN verdict='down' THEN 1 ELSE 0 END) AS down, "
        "  COUNT(*) AS total "
        "FROM ai_feedback "
        "WHERE created_at >= :w0 AND created_at < :w1 AND service IS NOT NULL "
        "GROUP BY service"
    ), {"w0": w0, "w1": w1})).fetchall()

    agg: dict[str, dict[str, int]] = {}
    for r in verify_rows:
        service = r[0]
        verdict = (r[1] or _as_dict(r[2]).get("verdict") or "").lower()
        a = agg.setdefault(service, {"fail": 0, "warn": 0, "vtotal": 0, "down": 0, "ftotal": 0})
        a["vtotal"] += 1
        if verdict == "fail":
            a["fail"] += 1
        elif verdict == "warn":
            a["warn"] += 1
    for r in fb_rows:
        service = r[0]
        a = agg.setdefault(service, {"fail": 0, "warn": 0, "vtotal": 0, "down": 0, "ftotal": 0})
        a["down"] += int(r[1] or 0)
        a["ftotal"] += int(r[2] or 0)

    out: list[dict[str, Any]] = []
    judged = withheld = 0
    for service, a in agg.items():
        # ★`sev is None` 으로 세면 "표본 부족"과 "표본 충분·정상"이 뭉개진다.
        #   `_classify_quality` 와 **같은 판정식**을 쓴다(하나를 고치면 다른 하나가 어긋나는
        #   것을 막기 위해 두 값 모두 QUALITY_MIN_SAMPLES 에 결속한다).
        if a["vtotal"] < QUALITY_MIN_SAMPLES and a["ftotal"] < QUALITY_MIN_SAMPLES:
            withheld += 1
        else:
            judged += 1
        sev, metrics = _classify_quality(
            a["fail"], a["warn"], a["vtotal"], a["down"], a["ftotal"]
        )
        if sev is None:
            continue
        out.append({
            "insight_type": "quality_drop",
            "severity": sev,
            "tenant_id": None,
            "recommended_action": "correct",
            "metrics_json": {
                "service": service,
                "verify_total": a["vtotal"], "fail": a["fail"], "warn": a["warn"],
                "feedback_total": a["ftotal"], "down": a["down"], **metrics,
            },
        })
    note_coverage(coverage, "quality_drop", judged=judged, withheld_count=withheld,
                  floor=QUALITY_MIN_SAMPLES)
    return out


#: ★4xx 는 latency 모집단에서 뺀다(5xx 는 남긴다).
#:
#: ## 왜 (라이브 실측 2026-08-27 · platform_events 7일 전수)
#:
#: 이 검출기의 커버리지가 낮아 보인 것은 **analyzer 결함이 아니라 모집단 정의 결함**이었다.
#: 판정률(1시간 key-시간 기준)과 고유 key 수:
#:
#:     현행(전건)    judged 347 / 6,735 =   5.2%   고유 key **2,462**
#:     4xx 제외      judged 332 / 1,946 = **17.1%**  고유 key **401**
#:
#: ★**judged 는 347→332 로 거의 안 준다.** 분모가 붕괴할 뿐이다 — 판정을 잃는 것이 아니라
#:   **애초에 판정될 수 없던 key 를 모집단에서 빼는 것**이다.
#:
#: ★**빠지는 key 는 2,062개다**(하한 무관 전수). 종전 주석의 *"8개"* 는 `n>=20` 을 통과한
#:   것만 센 수라 **분모를 감췄다**(독립 리뷰 F6). 성격 판정은 유지된다 — `/api/` 로
#:   시작하는 것까지 열어 봐도 `/api/.env` · `/api/mcp` · `/api/graphql` ·
#:   `/api/vendor/phpunit/.../eval-stdin.php` 같은 **스캐너 프로브**다.
#: ★★단 **전건 4xx 인 진짜 라우트도 사라진다** — 오늘은 표본이 1건이라 어차피 하한 미달이다
#:   (`/api/v1/deliberation/health`{401:1} · `/api/v1/regulation/gosi/coverage`{422:1}).
#:   **그 라우트가 인증 실패로만 호출되기 시작하면 지연을 못 본다.** 미봉합 부채.
#:
#: ★★**5xx 절은 「장래 대비 방어」다 — 지금 무엇을 지키고 있지 않다.**
#:
#:   ★2026-08-27 독립 리뷰 F1 이 내 종전 주석을 반증했다. 나는 *"`status<400` 으로 자르면
#:   타임아웃 라우트가 사라진다"* 고 적었는데, **그 라우트는 애초에 이 모집단에 없다**:
#:   `growth_telemetry.py:139` 가 `status_code >= 500` 을 **`api_error` 로** 보내고,
#:   이 함수는 `event_type IN ('api_call','llm_call')` 만 읽는다.
#:
#:       라이브 전 기간(2026-06-14~08-27) 실측
#:         api_call  중 5xx = **0건**  ← 데이터 우연이 아니라 미들웨어가 구조적으로 보장
#:         api_error 중 5xx = **4,720건**
#:
#:   → `>= 500` 절은 **구조적 死코드**다. 그래도 **남긴다**: 미들웨어가 바뀌거나 다른
#:     생산자가 5xx 를 `api_call` 로 넣기 시작하면 그때 지연이 조용히 사라지기 때문이다.
#:     **다만 그것이 "지금 5xx 지연이 커버된다"는 뜻은 아니다**(§C-11 — 거짓 면역 금지).
#:
#: ★★**부채(별건)**: **5xx 의 지연은 지금 어떤 검출기에도 없다.** `_analyze_error_cluster`
#:   는 **건수**만 세고(`api_error`) p95 를 보지 않으며, 이 함수는 `api_error` 를 안 읽는다.
#:   라이브에 `api_error /api/v1/auth/login 500 latency 60,069ms` 같은 행이 실재한다.
#:
#: ★`status_code IS NULL` 도 남긴다 — `llm_call` 은 HTTP 상태가 없다(실측 73건 · p95 90초).
#:
#: ## ★이것이 **고치지 않는** 것 (섞어 읽지 말 것)
#:
#: 1. **baseline 이 자기참조**라 **점진적 회귀는 구조적으로 탐지 불가**(반감기 ≈ 2일). 별건.
#: 2. **tenant 혼입** — 같은 key 안 tenant 별 p95 **62배** 차이
#:    (`/api/v1/store/projects` 3,766 vs 61). 지연을 안 바꾸고 **구성비만 옮겨도 발화 86~98.7%**.
#: 3. **n=20 에서 p95 는 잡음** — 회귀가 없어도 발화율 23~36%(nearest-rank 소표본 편향).
#:
#: ## ★검토했으나 **하지 않은 것**
#:
#: · **접두 정규화로 `/api/v1/X` 와 `/X` 병합** → **철회.** 둘은 **다른 것을 잰다**
#:   (백엔드 `perf_counter` 핸들러 시간 vs 프론트 fetch **왕복**). p95 격차 최대 **16.4배**,
#:   8쌍 중 **4쌍이 회귀 임계(1.5배) 초과** — 병합하면 **구성비만 바뀌어도 발화**한다.
#: · **`surface` 를 key 에 포함** → **보류.** 한 route 문자열에 surface 가 섞인 key 가
#:   라이브 **0건**이라 지금 넣으면 **공허한 락**이다. ★단 그 분리는 **우연**이다 —
#:   프론트가 절대 URL 을 보내는 경우가 실재한다(124건).


async def _analyze_latency_regression(db, w0, w1, coverage: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """route/service p95 vs **직전 배치** p95. 4xx 는 모집단에서 제외한다.

    ★종전 독스트링은 *"직전 7일 baseline"* 이라 적었는데 **사실이 아니다** — 7일은
      *"마지막 저장 행을 찾는 lookback"* 이고, 실제 baseline 은
      `metrics_json["baseline_p95"] = p95`(**이번 배치 자기 p95**)다. 문장을 사실로 낮춘다.
      (라이브 확증 2026-08-27: `baseline_p95 == p95_ms` 인 행이 **200/200**.)
    """
    from sqlalchemy import text

    rows = (await db.execute(text(
        "SELECT COALESCE(route, service) AS k, latency_ms FROM platform_events "
        "WHERE event_type IN ('api_call','llm_call') "
        "  AND latency_ms IS NOT NULL "
        "  AND created_at >= :w0 AND created_at < :w1 "
        "  AND COALESCE(route, service) IS NOT NULL "
        # ★★2026-08-27 — **4xx 를 모집단에서 뺀다**(5xx·NULL 은 남긴다). 위 주석 참조.
        "  AND (status_code IS NULL OR status_code < 400 OR status_code >= 500)"
    ), {"w0": w0, "w1": w1})).fetchall()

    by_key: dict[str, list[float]] = {}
    for r in rows:
        by_key.setdefault(r[0], []).append(float(r[1]))

    # 직전 baseline(latest latency_regression insight per key) 조회.
    base_rows = (await db.execute(text(
        "SELECT DISTINCT ON (metrics_json->>'key') "
        "  metrics_json->>'key' AS k, "
        "  (metrics_json->>'baseline_p95')::float AS bp95 "
        "FROM platform_insights "
        "WHERE insight_type = ANY(:types) "
        "  AND created_at >= :since "
        "ORDER BY metrics_json->>'key', created_at DESC"
    ), {"since": w1 - timedelta(days=LATENCY_BASELINE_DAYS),
        "types": list(LATENCY_BASELINE_SOURCE_TYPES)})).fetchall()
    baselines = {r[0]: float(r[1] or 0.0) for r in base_rows}

    out: list[dict[str, Any]] = []
    judged = withheld = 0
    for key, vals in by_key.items():
        if len(vals) < LATENCY_MIN_SAMPLES:
            # ★행을 만들지 않는 것은 옳다(802개를 발행하면 소음이 는다). 다만
            #   **몇 개를 못 봤는지는 말해야** 한다 — 안 그러면 커버리지 3% 가 100% 로 읽힌다.
            withheld += 1
            continue
        judged += 1
        p95 = round(_percentile(vals, 95.0), 2)
        baseline_p95 = baselines.get(key, 0.0)
        sev = _classify_latency(p95, baseline_p95)
        # baseline 없으면(첫 관측) 정보성 baseline 적재만(트리거 없음).
        out.append({
            # ★회귀가 아니면 `latency_baseline` — 사람이 보는 인사이트 목록을 오염시키지 않는다.
            #   (baseline 조회는 LATENCY_BASELINE_SOURCE_TYPES 로 두 타입을 모두 읽는다.)
            "insight_type": insight_type_for_latency(sev),
            "severity": sev or "info",
            "tenant_id": None,
            "recommended_action": "heal" if sev else "none",
            "metrics_json": {
                "key": key, "p95_ms": p95, "samples": len(vals),
                # 다음 배치가 baseline 으로 참조(자가보정 기반): 이번 p95 를 저장.
                "baseline_p95": p95,
                "prev_baseline_p95": baseline_p95,
            },
        })
    note_coverage(coverage, "latency_regression", judged=judged, withheld_count=withheld,
                  floor=LATENCY_MIN_SAMPLES)
    return out


# ════════════════════════════════════════════════════════════════════════════
# narrative (규칙 기본 + 선택적 LLM)
# ════════════════════════════════════════════════════════════════════════════

def _metric_text(m: dict[str, Any], field: str, *, unit: str = "%") -> str:
    """지표 한 칸 — **보류된 값을 숫자 자리에 그대로 흘리지 않는다.**

    ★`#861` 이 `down_pct` 를 거짓 `0.0` 대신 `None` + 사유로 바꿨는데, 사람이 읽는
      이 층이 그 `None` 을 **f-string 에 그대로** 넣어 `feedback down None%` 를 출력했다.
      값을 정직하게 만든 수정이 **마지막 한 층에서 거짓말로 되돌아간** 것이다.
      (형제 정답 기준선: `tests/test_rfi_register.py` 의 `assert "None%" not in …`)
    """
    if is_withheld(m, field):
        return "미측정"
    v = m.get(field)
    return "미상" if v is None else f"{v}{unit}"


def _withheld_note(m: dict[str, Any]) -> str:
    """보류된 지표들의 **사유를 문장 끝에 한 번** 싣는다(같은 사유는 합친다).

    ★사유는 이미 만들어져 DB 에 저장까지 된다(`<field>_basis`). 그런데 화면이 읽는
      유일한 층인 narrative 에 **한 번도 실리지 않았다** — 「사유를 버렸다」(유료·비가역
      산출물 규율의 세 번째 얼굴)와 같은 형태다. 진단 불가는 그 자체로 장애다.
    """
    by_basis: dict[str, list[str]] = {}
    for key in list(m):
        if not key.endswith("_absent") or not m.get(key):
            continue
        field = key[: -len("_absent")]
        if not is_withheld(m, field):
            continue
        basis = str(m.get(f"{field}_basis") or m.get(key))
        by_basis.setdefault(basis, []).append(field)
    if not by_basis:
        return ""
    parts = [f"{'·'.join(fields)} {basis}" for basis, fields in by_basis.items()]
    return "  ※ " + " / ".join(parts)


def _rule_narrative(ins: dict[str, Any]) -> str:
    """규칙 기반 narrative(LLM 없이도 항상 채워지는 한국어 요약).

    ★**보류 사유 부착은 여기 단일 길목에서 한 번만** 한다. 본문은 반환 지점이
      일곱이라 거기에 손으로 붙이면 **반드시 하나를 빠뜨리고, 그 하나가 곧
      사유가 사라지는 경로**가 된다(`#886` 이 같은 이유로 호출부 단일 길목을 골랐다).
    """
    return _rule_narrative_body(ins) + _withheld_note(ins.get("metrics_json") or {})


def _rule_narrative_body(ins: dict[str, Any]) -> str:
    """타입별 본문(사유 부착 전). 직접 부르지 말 것 — `_rule_narrative` 를 쓴다."""
    m = ins.get("metrics_json") or {}
    t = ins["insight_type"]
    sev = ins.get("severity")
    if t == "error_cluster":
        return (f"[{sev}] 오류 군집 {m.get('signature')} — route={m.get('route')} "
                f"status={m.get('status_code')} 시간당 {m.get('per_hour')}건"
                f"(총 {m.get('count')}건).")
    if t == "recurring_verify_error":
        return (f"[{sev}] {m.get('service')} 재발 검증오류 '{m.get('issue_type')}' — "
                f"시간당 {m.get('per_hour')}건(총 {m.get('count')}건, 심각 {m.get('high_count')}건). "
                f"반복 검출 오류 — 원인 점검·개선 권장.")
    if t == "fallback_rate":
        # ★사유를 **헤드라인에** 넣는다. metrics_json 에만 있으면 목록을 훑는 사람은
        #   "80.77%" 만 보고 무엇부터 고칠지 모른다 — 비율과 사유가 같은 자리에 있어야
        #   판단이 된다(#816 이 세운 원칙을 이 문장에도 적용).
        #   ★`unlabeled` 는 **감추지 않고 그대로 말한다** — "사유 미분류"는 그 자체가
        #   조치 신호다(쓰기 경로가 사유를 안 싣고 있다는 뜻).
        top = m.get("top_reason")
        why = f" 최다 사유 {top}." if top else ""
        return (f"[{sev}] {m.get('service')} 폴백률 {m.get('fallback_pct')}% "
                f"(폴백 {m.get('fallback')}/{m.get('llm_call')}콜).{why}")
    if t == "selection_contamination":
        v = m.get("verdict")
        if v == "malformed":
            return (f"[{sev}] 선택 목록에 **주소가 아닌 값**이 들어온 관측 {m.get('count')}건 "
                    f"(문제 행 누적 {m.get('malformed_rows')}행) — 엑셀 소유자 칸이 주소로 "
                    f"읽혔을 수 있습니다. 통합 면적·용도지역 판정을 신뢰할 수 없습니다.")
        spread = m.get("max_spread_km")
        where = f"최대 {spread}km 떨어짐" if spread is not None else "거리 미상(좌표 없음)"
        return (f"[{sev}] 서로 다른 지역이 한 선택에 묶인 관측 {m.get('count')}건({where}) — "
                f"**후보지 비교라면 정상입니다.** 통합 대지면적으로 계산되지 않도록 "
                f"화면이 고지하고 있는지만 확인하세요.")
    if t == "quality_drop":
        return (f"[{sev}] {m.get('service')} 품질저하 — verify fail "
                f"{_metric_text(m, 'fail_pct')}/warn {_metric_text(m, 'warn_pct')}, "
                f"feedback down {_metric_text(m, 'down_pct')}.")
    if t == "latency_regression":
        return (f"[{sev}] {m.get('key')} p95 {m.get('p95_ms')}ms "
                f"(이전 baseline {m.get('prev_baseline_p95')}ms, 표본 {m.get('samples')}).")
    # ★분기가 없는 타입의 기본 narrative. 종전엔 `{t}` 가 **영문 enum 그대로** 나갔다
    #   (예: `[info] improvement_proposal`). 분기 없는 타입일수록 이 문장이 유일한 설명이라
    #   여기서 raw 가 새면 그 카드는 **아무 말도 하지 않는 것과 같다.**
    from app.services.growth.insight_types import insight_label

    return f"[{sev}] {insight_label(t)}"


def _llm_enabled() -> bool:
    """LLM narrative 활성 여부 — env 기본값 위에 L1 토글(feature.llm_narrative) 오버레이.

    기본 off(GROWTH_LLM_NARRATIVE=1 일 때만 on). L1 자가수정이 품질급락 시 기록한
    platform_settings('feature.llm_narrative')의 enabled 가 env 를 덮는다
    (자동 비활성 토글의 소비 지점 — 과거엔 기록만 하고 읽는 곳이 없었다).
    단, ANTHROPIC_API_KEY 가 없으면 어떤 경우에도 off(호출 자체가 불가).
    """
    enabled = os.getenv("GROWTH_LLM_NARRATIVE", "0").strip() in ("1", "true", "True")
    try:
        from app.services.growth import dynamic_config

        val = dynamic_config.get_cached("feature.llm_narrative")
        if isinstance(val, dict) and "enabled" in val:
            enabled = bool(val["enabled"])
    except Exception:  # noqa: BLE001 — 오버레이 실패는 env 기본값 유지.
        pass
    if not enabled:
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _llm_narrative(ins: dict[str, Any]) -> str | None:
    """critical 인사이트 1건을 LLM 1콜로 요약(base_interpreter LLM 경로 재사용).

    실패/미설치/타임아웃은 None 반환 → 호출처가 규칙 narrative 로 폴백.
    """
    try:
        from app.services.ai.llm_provider import get_llm

        llm = get_llm(service="growth_analyze", timeout=20, max_tokens=200)
        prompt = (
            "다음 플랫폼 운영 인사이트를 한국어 2문장으로 요약하고 권고조치를 덧붙여라. "
            "과장 금지, 지표 근거만.\n"
            + json.dumps(ins.get("metrics_json") or {}, ensure_ascii=False, default=str)
        )
        resp = llm.invoke(prompt)
        # 계측: 동기 호출도 토큰·과금 기록(실행 루프 있으면 예약, 없으면 생략·best-effort)
        from app.services.ai.base_interpreter import record_llm_response_billing_sync
        record_llm_response_billing_sync(llm, resp, service="growth_analyze")
        text_out = getattr(resp, "content", None) or str(resp)
        return str(text_out).strip()[:1000] or None
    except Exception as e:  # noqa: BLE001
        logger.debug("growth LLM narrative 폴백: %s", str(e)[:120])
        return None


def _as_dict(v: Any) -> dict[str, Any]:
    """payload(JSONB → dict 또는 문자열)를 안전하게 dict 로."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v:
        try:
            d = json.loads(v)
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001
            return {}
    return {}


def default_window(hours: int = 1) -> tuple[datetime, datetime]:
    """기본 분석 윈도우(now-기준 직전 N시간). 태스크 진입점 편의."""
    now = datetime.now(UTC)
    return now - timedelta(hours=hours), now


__all__ = [
    "analyze_window",
    "normalize_stack",
    "default_window",
    # 순수 판정 함수(단위검증용 공개).
    "_classify_error_count",
    "_classify_fallback",
    "_classify_quality",
    "_classify_latency",
    "_percentile",
    # L1 자동보정 소비 배선(실효 임계 리더).
    "_effective_threshold",
]
