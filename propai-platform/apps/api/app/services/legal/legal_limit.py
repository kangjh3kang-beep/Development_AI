"""법정 제약 상수는 **근거 없이 존재할 수 없다** (2026-08-23).

## 왜 이 타입이 필요한가

`MAX_FLOORS = {"M10": 3, "M11": 3}` — 단독주택·전원주택의 층수 상한을 **3층**으로
박아 둔 상수가 있었다. 어느 법 어느 조문에서 왔는지 코드가 말하지 않았고,
실제로는 **틀린 값**이었다.

  · 건축법 시행령 별표1 제1호 — **3개 층 이하는 다중주택(나목)·다가구주택(다목)** 이다
  · **단독주택(가목)·공관(라목)에는 유형 자체의 층수 제한이 없다**

그 결과 자연녹지(건폐 20%·4층) 부지에서 단독주택 계획이 4층 → 3층으로 깎여
용적률이 80%에서 60%로 내려갔고, 그 손실의 근거를 **아무도 댈 수 없었다**.

★★더 나쁜 것은 이 오류가 **모순을 없애면서** 들어왔다는 점이다.
  종전에는 "4층 계획 > 3층 상한 → **부적합**" 이라는 이상 신호가 있었고,
  그 신호가 사용자에게 "이 계산은 수상하다"고 알려 주었다.
  제약을 계획에 반영하자 신호는 사라졌지만 **값은 여전히 틀렸다** —
  틀린 값이 더 그럴듯해진 것이다.

## 실측 (2026-08-23 전수조사)

규범성 상수 테이블 **48개** 중 **30개(62%)** 가 법·조문 근거 없이 박혀 있었다.
그 값들이 계획을 깎고, 부적합을 만들고, 사업성을 결정한다.

## 이 타입의 계약

**값과 근거는 한 몸이다.** `law` 없이 `LegalLimit` 을 만들 수 없다 —
숫자만 넣는 길이 존재하지 않게 해서, "근거 미확인"을 **사후에 표시하는 대신
애초에 들어오지 못하게** 한다.
"""

from __future__ import annotations

from dataclasses import dataclass


class MissingLegalBasisError(ValueError):
    """근거 없이 법정 제약을 만들려 했을 때. **표시가 아니라 차단**이다."""


@dataclass(frozen=True, slots=True)
class LegalLimit:
    """법정 제약 하나 — 값 + 근거(법령·조문) + 보충 설명.

    Args:
        value: 제약 값. `None` 은 **"이 유형에는 해당 제약이 없다"** 는 뜻이며,
            그 사실 자체도 근거가 필요하다(없다는 것도 법이 정한 것이다).
        law: 법령·조문. 비면 생성 실패.
        note: 사람이 읽는 보충 설명(선택).

    Raises:
        MissingLegalBasisError: `law` 가 비었을 때.
    """

    value: float | int | None
    law: str
    note: str = ""

    def __post_init__(self) -> None:
        if not (self.law or "").strip():
            raise MissingLegalBasisError(
                f"법정 제약에 근거가 없다(value={self.value!r}). "
                "어느 법 어느 조문인지 적어라 — 근거 없는 제약은 계획을 깎을 자격이 없다."
            )

    @property
    def unlimited(self) -> bool:
        """이 유형에 해당 제약이 **없는가**(값이 None)."""
        return self.value is None

    def __str__(self) -> str:
        v = "제한 없음" if self.unlimited else f"{self.value:g}"
        return f"{v} ({self.law})" if not self.note else f"{v} ({self.law} — {self.note})"
