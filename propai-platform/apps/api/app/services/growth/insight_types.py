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


# ── 표시명(한국어) — **백엔드 SSOT** ────────────────────────────────────────
#
# ★왜 백엔드에 두나(2026-08-25 라이브 실측). 백엔드가 **사용자에게 보이는 산문**을 조립하는데
#   표시명을 몰라서, 폴백이 **영문 enum 을 그대로 끼워** 내보내고 있었다:
#
#     improvement_agent.py: f"critical 인사이트({itype}) — 사람 진단 필요."
#     analyzer.py         : f"[{sev}] {t}"
#
#   라이브 「성장 분석」 화면에서 *"critical 인사이트(recurring_verify_error) — 사람 진단 필요."*
#   가 실제로 관측됐다(동료 세션 제보 · 본 세션에서 소스로 확증).
#
# ★왜 프론트 표만으로는 못 고치나: 그 문구는 **백엔드가 만들어 저장**한다(`narrative`·
#   `diagnosis`). 프론트는 그것을 그대로 렌더할 뿐이라, 프론트에 라벨이 아무리 많아도
#   백엔드가 조립한 산문 안의 raw enum 은 손댈 수 없다.
#
# ★`#808` 이 세운 것은 **타입 목록** SSOT 였고 **표시명은 아니었다.** 여기서 그 축을 채운다.
#   프론트 `GrowthDashboard.tsx` 의 `TYPE_LABELS` 는 이제 이 표에서 **파생**돼야 하고,
#   두 표가 갈리면 `tests/unit/test_insight_label_ssot.py` 가 잡는다.
INSIGHT_LABELS: dict[str, str] = {
    "error_cluster": "오류 군집",
    "fallback_rate": "폴백률",
    "quality_drop": "품질 저하",
    "recurring_verify_error": "검증오류 재발",
    "latency_regression": "지연 회귀(p95)",
    "latency_baseline": "지연 기준선(기록)",
    "selection_contamination": "선택 오염 관측",
    "stale_reanalysis": "재분석 제안",
    "heal_escalation": "자동치유 무효(사람 점검)",
    "improvement_proposal": "개선 제안",
    "prompt_candidate": "프롬프트 후보",
}


# ── 정체 필드 — **무엇이 "같은 인사이트"인가** ──────────────────────────────
#
# ★왜 이 축이 필요한가 (라이브 실측 2026-08-26T16:xxZ · 활성 컨테이너)
#
#   `platform_insights` 에 **정리 경로가 하나도 없다** — `status` 분포가
#   `open 3,127 / acknowledged 16` 이고 `expired`·`superseded` 는 **0** 이다.
#   그래서 같은 지표가 매 실행마다 새 행으로 쌓이고 옛 행이 영원히 열려 있다:
#
#       latency_regression  open 2,298  ← 그중 **30일 초과 1,212건**
#       ★같은 키에 더 새 행이 있는 옛 행(= 승계됨) = 전 타입 **2,678**
#         승계분만 닫으면 open 3,127 → **449** (86% 감소)
#
# ★**목록이 아니라 선언이다.** 이 표에 빠진 타입은 정리 대상에서 **조용히 제외**되므로,
#   `tests/test_growth_insight_retention.py` 가 `INSIGHT_TYPES` 전수와 대조해 **빠지면 실패**한다.
#   ★2026-08-27 정정 — 종전 주석은 `test_insight_type_catalog.py` 를 가리켰는데 그 파일엔
#     이 표를 보는 단언이 **0건**이다. 매달린 참조는 후임을 엉뚱한 곳으로 보낸다.
#   값이 `None` 인 것은 *"정체를 정의할 수 없다"* 는 **명시적 선언**이지 누락이 아니다.
#
# ★손으로 고르면 상한이 된다(실증): 이 표를 만들기 전 조사에서 `error_cluster` 를
#   `key` 로 물었는데 실제 정체는 `signature` 였다 — 112행(고유 12)이 **승계 0** 으로
#   과소계상됐다. 그래서 필드명을 **코드에 선언**하고 락에 결속한다.
IDENTITY_FIELDS: dict[str, tuple[str, ...] | None] = {
    # metrics_json 안의 **이 필드들이 모두 같으면** 같은 대상에 대한 관측이다.
    #
    # ★★단일 필드로는 부족하다(2026-08-27 독립 리뷰 적발). 처음엔
    #   `recurring_verify_error` 의 정체를 `service` **하나**로 적었는데, 생산자
    #   `_cluster_verify_issues`(`analyzer.py:191`)는 **`(service, issue_type)` 복합키**로
    #   군집한다. 즉 **한 번의 `analyze_window` 가 같은 service 에 issue_type 개수만큼
    #   행을 발행**하는데, 정체가 `service` 뿐이면 그것들이 **서로를 승계**한다 —
    #   닫히는 것이 *옛 관측*이 아니라 **같은 순간에 발행된 서로 다른 결함**이 된다.
    #   게다가 한 윈도우의 INSERT 가 한 트랜잭션이라 `created_at` 이 전부 같아
    #   무엇이 살아남을지가 **uuid 정렬 = 사실상 난수**였다.
    #   ★이것은 이 커밋이 자랑한 바로 그 실수(`error_cluster` 를 `key` 로 물었던 것)의
    #     **재발**이다 — 그때 얻은 교훈은 *"필드를 선언하라"* 였는데 부족했다.
    #     **선언의 존재는 그 선언이 옳은지 말해 주지 않는다.**
    "error_cluster": ("signature",),                       # 라이브: 112행 → 고유 12
    "fallback_rate": ("service",),                         # 21행 → 3
    "quality_drop": ("service",),                          # 4행 → 1
    "recurring_verify_error": ("service", "issue_type"),   # ★복합 — 위 참조
    "latency_regression": ("key",),                        # 2,298행 → 189
    "latency_baseline": ("key",),                          # 577행 → 84
    "selection_contamination": ("verdict",),               # 2행 → 1
    # ★아래는 **정리하지 않는다** — 정체가 없거나, 있어도 승계 개념이 맞지 않는다.
    "stale_reanalysis": None,               # 대상마다 1회성 제안
    "heal_escalation": None,                # critical — 사람이 닫아야 한다
    "improvement_proposal": None,           # PR 아티팩트(source_insight_id 로 추적)
    "prompt_candidate": None,               # 사람 승인 대기 자산
}


def identity_fields(insight_type: str | None) -> tuple[str, ...] | None:
    """이 타입의 정체 필드들. 선언되지 않은 타입은 **정리 대상이 아니다**(안전 기본값)."""
    return IDENTITY_FIELDS.get(insight_type or "")


def insight_label(insight_type: str | None) -> str:
    """타입 → 한국어 표시명. **모르면 감추지 않고 원문 그대로** 돌려준다.

    ★raw 를 숨기려고 "알 수 없음" 같은 것으로 바꾸지 않는다 — 그러면 *"새 타입이 생겼다"* 는
      가장 중요한 신호가 사라지고, 대신 **어느 타입인지 모르는 문장**이 남는다.
      카탈로그에 있는 타입은 계약 테스트가 라벨을 강제하므로, 여기로 떨어지는 것은
      **카탈로그 밖의 새 타입**뿐이다.
    """
    if not insight_type:
        return "알 수 없는 인사이트"
    return INSIGHT_LABELS.get(insight_type, insight_type)

__all__ = ["INSIGHT_TYPES", "NON_ACTIONABLE"]
