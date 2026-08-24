"""`platform_insights.insight_type` 의 **선언 카탈로그**(SSOT).

## 왜 필요한가 (쉬운 설명)

인사이트는 여러 모듈이 각자 INSERT 한다 — `analyzer`(5종) · `heal_actions`(1종) ·
`healing_rules`(1종) · `improvement_agent`(2종). 그런데 화면(`GrowthDashboard.tsx`)은
**손으로 쓴 라벨 표**로 그 타입을 한글로 옮긴다.

**두 목록이 갈라졌다**(2026-08-24 실측):

  · 백엔드가 실제 내보내는 타입      **11종**
  · 화면 라벨표                      **7종** — 그중 3종은 백엔드가 **한 번도 안 내보내는 유령**
                                     (`funnel` · `usage_pattern` · `churn_risk`)
  · 즉 **7종이 라벨 없이 raw 문자열**로 떴다. 그중 `heal_escalation` 은
    *"자동치유가 반복 발화했는데 효과가 없다 — 사람 점검 필요"* 라는 **critical** 이다.

★규율 §A-4 그대로다: *"목록형이 아니라 전수/파생형으로 쓴다. 사람이 센 목록이 곧 상한이 된다."*
  실제로 **목록 7 vs 실제 11** 이었다.

## 이 파일이 하는 일

카탈로그를 **한 곳에** 두고, 양쪽을 여기에 결속시킨다.

  · `tests/test_insight_type_catalog.py` — growth 패키지를 스윕해 **새 타입이 카탈로그에
    빠지면** 실패한다(백엔드가 몰래 늘어나는 것을 막는다).
  · `apps/web/.../GrowthDashboard.catalog.test.ts` — 이 파일을 읽어 **화면 라벨표가
    카탈로그를 덮는지** 확인한다(화면이 몰래 뒤처지는 것을 막는다).

즉 카탈로그 자체는 손으로 적지만, **비어 있거나 낡으면 반드시 빨개진다.**
"""
from __future__ import annotations

# ── analyzer.analyze_window 가 산출 ──────────────────────────────────────────
_ANALYZER = frozenset({
    "error_cluster",            # js_error/api_error 시그니처 군집
    "fallback_rate",            # service별 LLM 폴백률
    "quality_drop",             # verify fail + feedback down 결합
    "recurring_verify_error",   # 동일 (service, issue_type) 재발
    "latency_regression",       # p95 가 baseline 대비 회귀
    "latency_baseline",         # ★회귀가 **아닌** 기록(조치 대상 아님 — 기계 참조용)
    "selection_contamination",  # 다필지 선택이 "하나의 부지"가 아닌 관측 빈도
})

# ── 자가치유 계열이 산출 ────────────────────────────────────────────────────
_HEALING = frozenset({
    "stale_reanalysis",   # heal_actions._do_stale_reanalysis — 재분석 제안 큐잉
    "heal_escalation",    # healing_rules._escalate — ★자동치유 무효, 사람 점검 필요(critical)
})

# ── 개선 에이전트가 산출(사람 검토용 아티팩트) ──────────────────────────────
_IMPROVEMENT = frozenset({
    "improvement_proposal",
    "prompt_candidate",
})

#: 저장소가 산출할 수 있는 `insight_type` 전체.
INSIGHT_TYPES: frozenset[str] = _ANALYZER | _HEALING | _IMPROVEMENT

#: **조치 대상이 아닌** 타입 — 화면이 "확인 필요"로 세면 진짜 신호가 묻힌다.
#:  · `latency_baseline` : 회귀가 아닌 기록(2026-08-23 에 2,059건이 쌓여 실제 조치 대상을 가렸다)
#:  · `selection_contamination` + `info` : 원거리 혼합은 **후보지 비교라는 정당한 사용**일 수 있다
NON_ACTIONABLE: frozenset[str] = frozenset({"latency_baseline"})

__all__ = ["INSIGHT_TYPES", "NON_ACTIONABLE"]
