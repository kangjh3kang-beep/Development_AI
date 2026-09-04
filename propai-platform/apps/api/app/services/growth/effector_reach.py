"""자가성장 **효과기가 실제로 어디까지 닿는가** — 한 곳에 적어 둔 표.

## 왜 이 파일이 필요한가 (2026-08-23)

스케줄러는 돈다(`#758` 로 재시작을 넘게 고쳤다). 그런데 **잡이 만든 결정을 제품이 읽는가**
는 **다른 질문**이고, 재보니 대부분 안 읽고 있었다.

문제는 "안 읽는다"가 아니라 **그 사실이 코드 어디에도 안 적혀 있다**는 것이다.
`heal_actions.py` 만 보면 액션 4종이 모두 살아 있는 것처럼 보이고, `feature_flags.py` 만
보면 L1 액션 3종이 다 동작하는 것처럼 보인다. 그래서 다음 사람이 **"배선 완결"로 오독**한다
(실제로 이 저장소의 조사 기록이 그렇게 읽혔다).

정답 기준선은 이미 저장소 안에 있다 — `integrations/base_client.py:72` 는
*"rate_limit_multiplier 는 클라측 rate limiter 가 없어 미적용(예약 필드)"* 라고 **정직하게**
적어 둔다. 이 파일은 그 관행을 **효과기 전체로 넓히고**, 옆의 계약 테스트가 표와 코드가
어긋나면 실패하게 한다.

## 이 파일이 하지 않는 것

**연결하지 않는다.** 소비처를 만드는 것은 제품 결정이 필요하다(클라측 rate limiter 를 둘
것인가, L2 개선안을 프롬프트에 실제로 주입할 것인가 등). 여기서는 **현재 도달범위를 사실대로
적고**, 그것이 바뀌면 표를 고치도록 강제할 뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Reach(StrEnum):
    """효과기가 닿는 범위."""

    #: 제품 런타임 경로가 이 값을 읽어 **동작이 달라진다**.
    PRODUCT = "product"
    #: 성장엔진이 **자기 자신**만 읽는다(자기 탐지 임계 등). 제품 동작은 안 바뀐다.
    SELF = "self"
    #: 쓰기는 되는데 **읽는 곳이 없다**. 이벤트·로그로만 남는다.
    NONE = "none"


@dataclass(frozen=True)
class Effector:
    key: str
    reach: Reach
    #: 왜 그 범위인지 — **근거가 되는 파일:줄**을 적는다(다음 사람이 재볼 수 있게).
    evidence: str
    #: PRODUCT 가 아니라면 무엇이 있어야 닿는지.
    missing: str = ""


#: 효과기 전수와 **실측된** 도달범위(2026-08-23 기준).
#:
#: ★`reach` 를 낙관적으로 적지 마라. 이 표의 값어치는 **닿지 않는 것을 닿지 않는다고
#:   적는 데** 있다. 옆 테스트가 근거 문자열이 비었는지까지 본다.
EFFECTORS: tuple[Effector, ...] = (
    Effector(
        key="threshold_relax",
        reach=Reach.PRODUCT,
        evidence=(
            "integrations/base_client.py 의 _request 가 relax.{service} 를 읽어 httpx 타임아웃에 "
            "곱한다. BaseAPIClient 는 다수 외부 클라이언트의 공통 상속부라 실런타임 경로다."
        ),
        missing=(
            "★절반만 닿는다 — 같은 값의 rate_limit_multiplier 는 적용 지점이 없다"
            "(base_client.py 주석이 '예약 필드'라고 밝힌다)."
        ),
    ),
    Effector(
        key="cache_warm",
        reach=Reach.NONE,
        evidence=(
            "heal_actions._do_cache_warm 이 params 의 enqueue 여부만 이벤트로 기록한다. "
            "실제로 데워질 캐시 대상을 넘겨받거나 큐에 넣는 경로가 없다."
        ),
        missing="데울 대상(서비스·키)을 정하고 그것을 실제로 채우는 작업 큐.",
    ),
    Effector(
        key="stale_reanalysis",
        reach=Reach.NONE,
        evidence=(
            "설계상 '제안 큐잉만(자동실행 금지)'이고, 승인 경로(routers/growth.py 의 ack)는 "
            "acknowledged/dismissed 만 처리한다."
        ),
        missing="승인 시 재분석을 실제로 태우는 트리거(자동실행 금지 원칙과 함께 설계돼야 한다).",
    ),
    Effector(
        key="circuit_observe",
        reach=Reach.NONE,
        evidence=(
            "heal_actions.py 의 ACTION_CIRCUIT_OBSERVE 옆에 '관측·기록만'이라고 코드가 직접 "
            "밝힌다. 이벤트만 남기고 차단기를 여닫지 않는 것이 설계 의도다."
        ),
        missing="없음 — 이건 결함이 아니라 **의도**다. 차단기를 실제로 여닫는 것은 별개 결정.",
    ),
    Effector(
        key="threshold_autotune",
        reach=Reach.SELF,
        evidence=(
            "feature_flags 가 threshold.{name} 을 쓰고, 읽는 곳은 growth/analyzer 와 "
            "dynamic_config 헬퍼뿐이다(성장엔진의 자기 탐지 임계)."
        ),
        missing="제품 코드가 이 임계를 읽는 지점(현재는 성장엔진 안에서만 순환한다).",
    ),
    Effector(
        key="feature_toggle",
        reach=Reach.SELF,
        evidence=(
            "feature.{name} 의 발견된 독자는 growth/analyzer 의 feature.llm_narrative 하나로, "
            "성장엔진이 자기 서술 기능을 켜고 끄는 용도다."
        ),
        missing="제품 기능 플래그로 쓰려면 제품 코드에 읽는 지점이 있어야 한다.",
    ),
    Effector(
        key="prompt_ab_adopt",
        reach=Reach.NONE,
        evidence=(
            "★채택은 되는데 **본문이 안 바뀐다**. base_interpreter 의 _resolve_prompt_version() "
            "호출처는 _cache_key 와 텔레메트리 라벨 **둘뿐**이고(전수 확인), 실제 전송 본문은 "
            "각 인터프리터의 system_prompt 상수에서 온다."
        ),
        missing=(
            "채택된 버전이 실제 프롬프트 본문을 고르도록 하는 배선. "
            "덧붙여 improvement_agent 가 만드는 improved_prompt_addendum 은 읽는 곳이 0이다."
        ),
    ),
)


def by_reach(reach: Reach) -> tuple[str, ...]:
    """해당 범위의 효과기 키들."""
    return tuple(e.key for e in EFFECTORS if e.reach is reach)


def product_reaching_count() -> int:
    """제품 동작에 닿는 효과기 수 — **이 값이 늘어나는 것이 목표다**."""
    return len(by_reach(Reach.PRODUCT))
