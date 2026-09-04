"""산출값의 **정밀도 등급** — 무엇으로 만든 값인가 (2026-08-23).

## 왜 필요한가

프로젝트 허브 화면에서 이런 일이 있었다.

    설계 분석   → "분석 전"
    공사비 분석 → "분석 전"
    수지·사업성 → 총사업비 4,157.7억 · 순이익 -2,936.8억 · **등급 F**

설계가 없는데 수지가 나온다. 그런데 이건 **버그가 아니다** — 백엔드는
`gfa = land_area × effective_far / 100` 로 **개략(rough) 추정**을 하고 있고,
그 모듈 이름도 `rough_feasibility_orchestrator` 다. 계산은 정직하다.

**문제는 화면이 개략치를 확정치와 똑같이 보여 주는 것이다.**
사용자는 "분석 전인데 왜 숫자가 있나" 로 읽고, 그 숫자를 근거로 판단한다.

같은 형태가 여럿이다.
  · 입지 점수 25/100 **등급 D** — 실제로는 **1/6 지표**만 반영
  · 건축가능 연면적 131,858㎡ — 그 아래에 *"용도지역 기본값 추정(신뢰도 낮음)"*
  · 향별 일조 7.8h 까지 정밀 계산 — 그런데 그 부지는 **맹지**

즉 **할루시네이션(없는 것을 지어냄)이 아니라 정밀도 위장**이다.
처방도 다르다 — 값을 지우는 게 아니라 **등급을 붙인다**.

## ★두 축을 혼동하지 않는다

이 저장소에는 이미 `confidence`(109곳)·`data_quality`(11곳)가 있는데
**의미가 섞여** 있다. 이 모듈은 **6번째 개념을 만들지 않고** 축을 가른다.

| 축 | 묻는 것 | 값 | 기존 |
|---|---|---|---|
| **정밀도(precision)** | **무엇으로** 만든 값인가 | E / D / V | (없음 — 이 모듈) |
| 출처 신뢰도(confidence) | 그 입력을 **얼마나 믿나** | verified / press / unavailable … | 기존 유지 |

둘은 **직교**한다. 확인된 조례값(confidence 높음)으로 만든 **개략** 연면적(정밀도 E)이
있을 수 있고, 그 반대도 있다.

## 핵심 규칙 — **하류는 상류의 최저를 넘을 수 없다**

개략 연면적(E)으로 만든 공사비는 아무리 정교해도 **E** 다.
이 한 줄이 "설계 없이 나온 등급 F" 를 자동으로 "개략 등급 F(E)" 로 만든다.
"""

from __future__ import annotations

from enum import StrEnum


class PrecisionGrade(StrEnum):
    """이 값을 **무엇으로** 만들었는가.

    순서가 곧 등급이다 — `ESTIMATED < DESIGNED < VERIFIED`.
    """

    ESTIMATED = "E"
    """부지 정보만으로 추정. 예: `연면적 = 대지면적 × 실효용적률`.

    설계가 없어도 나온다. **개략치**이며 확정 판단의 근거가 될 수 없다.
    """

    DESIGNED = "D"
    """설계 산출물에 기반. 예: 매스 스터디·배치안이 낸 연면적."""

    VERIFIED = "V"
    """실측·조회로 확인. 예: 조례 API 응답, 등기·대장 조회값."""

    @property
    def rank(self) -> int:
        return {"E": 0, "D": 1, "V": 2}[self.value]

    @property
    def label_ko(self) -> str:
        return {"E": "개략(추정)", "D": "설계기반", "V": "확인됨"}[self.value]


def lowest(*grades: PrecisionGrade | None) -> PrecisionGrade | None:
    """상류 등급들 중 **가장 낮은 것**. 하나라도 None 이면 None(=미표기).

    ★이 함수가 이 모듈의 존재 이유다. 개략 입력으로 만든 산출은
      계산이 아무리 정교해도 개략이다. 등급을 올릴 수 있는 것은
      **더 나은 입력**뿐이지 더 나은 계산이 아니다.

    ★None 을 만나면 None 을 돌려준다 — 등급을 모르는 입력이 섞이면
      결과의 등급도 알 수 없다. 낙관적으로 채우지 않는다.
    """
    if not grades or any(g is None for g in grades):
        return None
    return min(grades, key=lambda g: g.rank)  # type: ignore[union-attr]


def from_legacy(data_quality: str | None) -> PrecisionGrade | None:
    """기존 `data_quality` 문자열 → 정밀도 등급(있으면).

    ★기존 표기를 버리지 않고 **읽어 온다** — `assumed_defaults` 는
      가정값으로 만든 것이므로 개략(E)이다.
    """
    if not data_quality:
        return None
    if data_quality == "assumed_defaults":
        return PrecisionGrade.ESTIMATED
    return None


def annotate(value: object, grade: PrecisionGrade | None, *, basis: str = "") -> dict:
    """값에 등급을 붙인 표준 페이로드.

    Args:
        value: 산출값.
        grade: 정밀도 등급. **None 이면 "미표기"** 이고, 화면은 그것을 그대로 알려야 한다
            (모르는 것을 확정으로 보여 주지 않는다).
        basis: 이 등급이 나온 이유(예: "대지면적×실효용적률 — 설계 미반영").
    """
    return {
        "value": value,
        "precision": grade.value if grade else None,
        "precision_label": grade.label_ko if grade else "정밀도 미표기",
        "precision_basis": basis,
    }
