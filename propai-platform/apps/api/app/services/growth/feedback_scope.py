"""사용자 피드백(`ai_feedback`)의 **출처 축** SSOT — 어떤 출처가 **자동 효과기**를 움직여도 되는가.

## 왜 (2026-09-12 실측 — 저장소가 **빌드로 막아 둔** 사고)

`apps/web/eslint.config.mjs` 가 자가검증(field_audit) 표면에 피드백 위젯 임포트를 **물리적으로
금지**하면서 이유를 적어 두었다:

> 성장엔진은 사용자 👎(`ai_feedback`)를 모아 품질저하로 판정하고, 그 판정이 임계를 넘으면
> **서술기능(`llm_narrative`)을 자동으로 끈다.** … 자가검증 배지 옆에 👍👎를 놓으면
> *"값이 이상하다고 알려줄수록 그걸 설명하는 기능이 먼저 꺼지는"* **뒤집힌 루프**가 생긴다
> (correctness 판정이 서술 기능을 끄는 **카테고리 오류**).
> **지금 이 사고가 안 나는 유일한 이유는 `VerificationBadge` 가 `FeedbackWidget` 에 `service` 를
> 넘기지 않아서인데, 그건 「우연한 차단」이지 설계된 격리가 아니다(집계 쿼리에 출처 필터 자체가 없다).**

★그 마지막 문장을 **실측으로 확인했다**: `ai_feedback` 을 읽는 곳 5곳 중 `service` 를 키로 쓰는
  **4곳 전부**가 `target_type` 을 **한 번도 언급하지 않는다**(대조군: 같은 파일들이 `service` 를
  42~58회 언급한다 ⇒ 조회기 생존). **출처 필터는 정말 없었다.**

## 무엇을 고치나 — **「전부 제외」가 아니라 「자동만 제외」**

소비처를 두 갈래로 갈랐다(실측 · 각 함수의 선언):

| 경로 | 소비처 | 결과 |
|---|---|---|
| **자동 효과기** | `analyzer._analyze_quality_drop` → `quality_drop` → `feature_toggle`(자동 비활성) · `feature_flags`(버전 자동 채택) | **제외한다** |
| **사람 게이트** | `learning_loop.compute_down_rates` → `improvement_agent` → **PR 제안** · `learning_loop` 후보 등록(*"자동 active 절대 금지 = 사람 승인 게이트"*) · `improvement_agent._failure_samples` | **그대로 둔다** |

★**신호를 버리지 않는다.** 자가검증 표면의 👎 는 사람이 보는 축에는 **계속 들어간다** —
  끊는 것은 **「사람 개입 없이 기능을 끄는」 그 한 갈래**뿐이다.
★이 구분이 없으면 처방이 **결함보다 넓어진다**(전역 §D-20 — 처방 범위 = 결함 범위).

## 남은 가정(숨기지 않는다)

`target_type="analysis"` 를 보내는 렌더 지점은 **현재 정확히 하나**다
(`apps/web/components/common/VerificationBadge.tsx:223` — 파생 조회). 즉 이 제외는
«자가검증 표면» 을 **`target_type` 으로 근사**한다. 두 번째 `analysis` 표면이 생기면 근사가
깨지므로, 그때는 **출처 필드를 따로 두는 것**이 옳다. 그 판단을 여기 적어 둔다.
"""

from __future__ import annotations

#: `ai_feedback.target_type` 닫힌 어휘 — **정본**. 라우터 검증이 이것을 쓴다.
#  ★종전엔 라우터에 손으로 적힌 집합이 따로 있었다(같은 값의 두 정의). 여기로 일원화한다.
FEEDBACK_TARGET_TYPES: frozenset[str] = frozenset({"llm_output", "analysis", "recommendation"})

#: ★**자동 효과기**를 움직이는 집계에서 제외할 출처.
#  ★★계약 어휘다 — 소비처(SQL 파라미터)가 **문자열로** 분기하므로 락이 **리터럴로 못 박는다**
#    (심볼만 비교하면 값을 바꿔도 양쪽이 함께 움직여 **원리적으로 판별 불가**다).
AUTO_EFFECTOR_EXCLUDED_TARGETS: tuple[str, ...] = ("analysis",)


def auto_effector_excluded() -> list[str]:
    """SQL 파라미터로 넘길 제외 목록. **소비처가 상수를 복사하지 않게** 한 자리에서 만든다."""
    return list(AUTO_EFFECTOR_EXCLUDED_TARGETS)
