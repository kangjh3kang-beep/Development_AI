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

    @property
    def basis(self) -> str:
        """근거 문자열 — `PracticeLimit.basis` 와 같은 이름으로 읽히게 한다."""
        return self.law

    @property
    def enforceable(self) -> bool:
        """★법정 근거가 있으므로 **부적합(위법)을 단정할 자격이 있다**."""
        return True

    def __str__(self) -> str:
        v = "제한 없음" if self.unlimited else f"{self.value:g}"
        return f"{v} ({self.law})" if not self.note else f"{v} ({self.law} — {self.note})"


# ── 법정이 아닌 기준 — **출처는 필요하되, 부적합을 단정할 수는 없다** ────────────
#
# ★2026-08-23 (형제 스윕). `MAX_FLOORS` 를 고치면서 **같은 파일의 형제 두 표**를
#   그대로 뒀다는 것이 드러났다 — `MIN_LOT_AREA`·`ROAD_REQUIREMENT`.
#   둘 다 원시 숫자였고, 둘 다 `is_blocking=True` 로 **개발유형을 화면에서 죽인다**.
#
#   라이브 실측(2026-08-23, 168 컨테이너):
#     · 4,000㎡ 아파트 부지 → **"부적합"** · blocking `4000m² < 5000m² (최소) — 면적 부족`
#       그 5,000㎡ 가 어느 법에서 왔는지 **아무도 댈 수 없다**.
#     · M03 도로폭 3m·접도 1m → **"접도 제한 없음" 통과** — 건축법 §44① 의 2m 에도 못 미치는데.
#
#   ★두 증상은 **한 뿌리의 양면**이다: 표에 있으면 근거 없이 죽이고, 표에 없으면
#   근거 없이 살린다. `MAX_FLOORS` 가 이미 배운 것 — **미등재는 "제한 없음"이 아니다.**
#
# ## 왜 `LegalLimit` 로 통일하지 않는가
#
# 통일하려면 저 숫자들에 조문을 **붙여야** 하는데, 붙일 조문이 없다. 없는 근거를 지어내는 것은
# 이 축이 막으려던 바로 그 잘못이다. 그래서 **강제력이 다른 두 종류**로 가른다:
#
#   · `LegalLimit`    — 법령·조문. 위반은 **위법** → `부적합`(blocking) 을 낼 자격이 있다
#   · `PracticeLimit` — 실무·사업 기준. 위반은 **불리할 뿐 위법이 아니다** → `조건부` 까지만
#   · **미등재**       — 근거 미확인 → `unknown`(침묵도, 통과도 아니다)


@dataclass(frozen=True, slots=True)
class PracticeLimit:
    """법정이 아닌 실무 기준 하나 — 값 + 출처.

    `LegalLimit` 과 **모양은 같고 강제력만 다르다**(`enforceable=False`).
    소비처가 타입을 보고 판정 강도를 정하게 해서, "관행값이 법처럼 계획을 죽이는"
    일이 구조적으로 불가능하게 한다.

    Args:
        value: 기준 값. `None` 은 "이 유형에는 이 기준을 두지 않는다".
        source: 출처(실무 관행·사업 기준·내부 정책). 비면 생성 실패.
        note: 사람이 읽는 보충 설명(선택).

    Raises:
        MissingLegalBasisError: `source` 가 비었을 때.
    """

    value: float | int | None
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        if not (self.source or "").strip():
            raise MissingLegalBasisError(
                f"실무 기준에 출처가 없다(value={self.value!r}). "
                "어디서 온 값인지 적어라 — 출처 없는 값은 판정에 낄 자격이 없다."
            )

    @property
    def unlimited(self) -> bool:
        """이 유형에 해당 기준이 **없는가**(값이 None)."""
        return self.value is None

    @property
    def basis(self) -> str:
        """근거 문자열 — `LegalLimit.basis` 와 같은 이름으로 읽히게 한다."""
        return self.source

    @property
    def enforceable(self) -> bool:
        """★핵심 — 실무 기준은 **부적합을 단정할 수 없다**."""
        return False

    def __str__(self) -> str:
        v = "기준 없음" if self.unlimited else f"{self.value:g}"
        body = f"{v} ({self.source}"
        return f"{body} — {self.note})" if self.note else f"{body})"


#: 값 + 근거를 함께 지니는 제약 — 소비처는 `enforceable` 로 판정 강도를 가른다.
SourcedLimit = LegalLimit | PracticeLimit
