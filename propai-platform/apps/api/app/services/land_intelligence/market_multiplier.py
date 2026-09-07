"""지역별 공시지가→시세 보정계수 SSOT — 값과 **그 값을 말하는 방식**을 한 곳에 둔다.

★왜 이 모듈이 생겼나(2026-09-07)
종전에는 같은 로직이 두 곳에 복제돼 있었고(`comprehensive_analysis_service._get_market_multiplier`
· `land_price_estimator._market_multiplier`), **둘 다 같은 거짓 문장을 인쇄**했다:

    f"{district} 지역의 공시지가 현실화율(약 {100/mult:.0f}%)을 반영한 보정계수 {mult}배..."

이 「현실화율」은 **측정값이 아니라 계수를 뒤집은 수**다. 계수를 먼저 고르고 사유를 역산했으므로
인과가 뒤집혀 있다 — 산출물을 근거처럼 말한 것이다. 남양주 `1.2` → `100/1.2 = 83.3` → "약 83%".

★그리고 이 저장소는 **같은 금지를 자기 언어로 이미 적어 두고 있었다**
  (`app/services/ai/market_interpreter.py` GROUNDING_RULE 5항):
    "그 비율(현실화율)은 지역·연도별로 상이하므로 '70~80%' 같은 일반비율을
     데이터 근거 없이 확정 단정하지 않는다"
형제 검사 `verification/field_audit/invariants/market_methodology.py` 도 같은 화면에
"실거래로 검증되지 않음" 배지를 상시 띄우고 있었다. 즉 **한 화면의 두 표면이 모순**했고,
구체적으로 들려서 더 신뢰받는 「83%」 쪽이 거짓이었다.

★고친 것은 **값이 아니라 「왜」에 대한 거짓 주장**이다.
계수의 근거는 **문서화돼 있지 않다**. 다만 «잴 수 없다» 는 뜻이 아니다 — 개별공시지가↔실거래
대조는 가능하고(`external_api/molit_service.py` · `market/comparable_sample.py`), 형제 세션이 실제로
쟀다: `_workspace/PLAN_desk_appraisal_market_reality_2026-09-07.md` §1 표 9~10행 —
남양주 화도읍 일반상업지역 12개월 3,291건에서 **1.448배(현실화율 69%)**, 이 표의 남양주 값
**1.2배(83%)** 와 어긋난다. **미확보인 것은 데이터원이 아니라 전국 계수를 갱신할 표본이다**(n=3·1개 읍면).
근거 없이 값을 바꾸는 것은 고치려는 그 죄의 반복이므로, 계수는 그대로 두고 **사전 설정된
휴리스틱 상수**라고 있는 그대로 말한다.

⇒ 이 모듈이 계수의 SSOT 다. 두 소비처 모두 여기를 경유하므로 한 곳을 고치면 전역이 따라온다.
"""

from __future__ import annotations

from typing import NamedTuple

# 지역별 공시지가 대비 시세 보정계수(사전 설정 휴리스틱 · **측정된 현실화율이 아니다**).
#
# ★종전 주석은 여기에 "서울 강남권: 현실화율 약 50~65% → 1.5~2.0배" 같은 밴드를 적어 두었으나
#   걷어냈다. 두 가지가 틀렸다:
#     ① 밴드가 역수관계와 **가장자리에서 어긋난다** — "기타 지방 80~90% → 1.0~1.2" 인데
#        1.0 은 100%(밴드 밖) · "경기 70~85% → 1.1~1.4" 인데 1.1 은 90.9%(밴드 밖).
#     ② 같은 주석이 계수를 "현실화율의 역수 **+ 지역 프리미엄**" 이라 했다. 프리미엄이
#        더해졌다면 `100/계수` 는 **애초에 현실화율이 아니다** — 코드가 자기 모델과 모순했다.
#   근거 없는 밴드를 주석에 남기면 다음 사람이 **재검증하지 않고 신뢰한다.**
#
# ★계수의 근거·정확도는 모듈 독스트링 참조(«잴 수 없다» 가 아니라 «표본이 없다» 다).
#   ★★2026-09-07 정정 이력: 종전에 이 파일이 «대조 데이터원이 이 저장소에 없다» 고 **두 곳에서**
#     단정했는데 거짓에 가까웠다(독립 리뷰 M-5). 그리고 1차 정정 때 **한 곳만 고쳐** 같은 파일이
#     자기모순했다(R2 HIGH-2) — 이 PR 이 고치는 결함(«두 표면이 모순») 그 자체의 재발이었다.
#     ⇒ 이제 그 명제는 **모듈 독스트링 한 곳**에만 있다. 늘리지 말 것.
MARKET_MULTIPLIER_MAP: dict[str, float] = {
    # 서울 강남권 (공시지가 대비 시세 괴리가 큰 지역)
    "강남구": 1.8, "서초구": 1.7, "송파구": 1.6, "용산구": 1.6,
    # 서울 주요 주거·상업지역
    "마포구": 1.5, "성동구": 1.5, "광진구": 1.4, "영등포구": 1.4,
    "동작구": 1.4, "강동구": 1.4,
    # 서울 기타
    "관악구": 1.3, "구로구": 1.3, "금천구": 1.2,
    "노원구": 1.3, "도봉구": 1.2, "중랑구": 1.2, "강북구": 1.2,
    "성북구": 1.3, "은평구": 1.2, "서대문구": 1.3,
    "종로구": 1.5, "중구": 1.5, "양천구": 1.3, "강서구": 1.3,
    # 경기 주요시
    "성남시": 1.4, "분당": 1.5, "판교": 1.6,
    "수원시": 1.3, "용인시": 1.3, "화성시": 1.2,
    "고양시": 1.3, "일산": 1.3,
    "의정부시": 1.2, "남양주시": 1.2, "구리시": 1.3,
    "파주시": 1.1, "양주시": 1.1,
    "안양시": 1.3, "안산시": 1.2, "시흥시": 1.2,
    "김포시": 1.2, "광명시": 1.4, "하남시": 1.4,
    "부천시": 1.2, "광주시": 1.2,
    # 광역시
    "해운대구": 1.4, "수영구": 1.3,
    "연수구": 1.3, "송도": 1.4,
}

MARKET_MULTIPLIER_REGION: dict[str, float] = {
    "서울특별시": 1.4, "서울": 1.4,

    "인천광역시": 1.2, "인천": 1.2,
    "부산광역시": 1.2, "부산": 1.2,
    "대구광역시": 1.15, "대전광역시": 1.15,
    "광주광역시": 1.1, "울산광역시": 1.15,
    "세종특별자치시": 1.2, "제주특별자치도": 1.15,
}

# 지역이 하나도 매칭되지 않을 때의 기본 계수.
DEFAULT_MULTIPLIER: float = 1.2

# ★★출처 판정용 **안정 코드** — 표시 문구와 **분리**한다(2026-09-07 · 독립 리뷰 M-2).
#   왜: 종전에는 한정어 **문자열**이 유일한 판정 근거였다. 그래서 그 상수를
#   `"국토교통부 실거래가 통계로 산출된 지역 계수입니다"` 처럼 **없는 출처를 지어내는 문구**로
#   바꿔도 락이 전부 초록이었다(리뷰어가 변이로 실증). 낱말을 잠그면 **속성이 아니라 어휘**를
#   잠그는 것이라, 다른 낱말로 같은 거짓이 재발한다.
#   ★이 처방은 이 저장소에 **이미 있었다** — `field_audit/invariants/market_methodology.py` 가
#   같은 이유로 `source_kind` 를 도입했다("표시 문구가 유일한 판정 근거라, 출처 문구를 쉬운 말로
#   바꾸면 이 상시 배지가 아무 에러 없이 영구 침묵했다"). 형제를 따른다.
PROVENANCE_UNVERIFIED_PRESET = "UNVERIFIED_PRESET"

# 표시용 한정어(문구는 다듬을 수 있다 — 계약은 위 코드다).
UNVERIFIED_CAVEAT = "실거래로 검증된 현실화율이 아닌 사전 설정 참고 계수입니다"

# ★수식 안에 끼워 넣는 **짧은 형태**(2026-09-07 · 독립 리뷰 M-4).
#   왜 둘이 필요한가: `desk_appraisal_service` 는 사유를 **곱셈식의 연산 항 주석**으로 쓴다
#   (`… × 그밖의요인 1.2({사유})`). 거기에 문장형(마침표 포함)을 넣었더니 51~62자가 102~104자가
#   되고 **괄호가 3중 중첩**되며 수식 한가운데 **문장 종결 마침표**가 박혔다. 한정어가 정직해도
#   그 자리는 문장이 아니라 **항**을 기대한다. ⇒ 표현을 자리에 맞게 나눈다.
SHORT_CAVEAT = "실거래 미검증"

# ★★표시 문구를 **템플릿 상수**로 꺼낸다(2026-09-07 · 독립 리뷰 R3 HIGH-A).
#   왜: 종전 락은 «한정어를 담고 있는가»(`SHORT_CAVEAT in text`)라는 **포함** 검사였다. 그래서
#   한정어를 **지우지 않고 덧붙이면** 통과했다 — 리뷰어가 `f"{district} 국토부 실거래 검증 계수 ·
#   {SHORT_CAVEAT}"` 로 바꿔 36건 전부 생존시켰고, **그 문자열은 감정평가 PDF 에 도달한다**.
#   ★내가 테스트 독스트링에 «거짓으로 바꾸려면 한정어를 지워야 한다» 고 적은 것은 **거짓 면역
#   주장**이었다(§C-11). 포함은 «거짓을 말하지 않는가» 를 함의하지 않는다.
#   ⇒ 문구를 f-string 자유 리터럴에서 **템플릿 상수**로 꺼내고, 테스트가 그 템플릿을
#     **리터럴로 못 박는다**(계수표를 얼린 것과 같은 방식). 감정평가 표면에 나가는 문구를 바꾸려면
#     테스트도 함께 고쳐야 하고, 그것이 **의도된 마찰**이다.
SHORT_TEMPLATE_DISTRICT = "{key} 사전설정 계수 · {caveat}"
SHORT_TEMPLATE_REGION = "{key} 광역 사전설정 계수 · 시군구 미등록 · {caveat}"
SHORT_TEMPLATE_DEFAULT = "전국 기본 계수 · 지역 미등록 · {caveat}"
SHORT_TEMPLATE_UNKNOWN = "주소 미상 · 전국 기본 계수 · {caveat}"

SENTENCE_TEMPLATE_DISTRICT = "{key}에 대해 사전 설정된 지역 시세보정계수 {mult}배를 적용했습니다({caveat})."
SENTENCE_TEMPLATE_REGION = (
    "{key} 광역 단위의 사전 설정 시세보정계수 {mult}배를 적용했습니다"
    "(시·군·구 세부 계수 미등록 · {caveat})."
)
SENTENCE_TEMPLATE_DEFAULT = (
    "지역별 보정계수가 미등록되어 전국 기본 보정계수 {mult}배를 적용했습니다({caveat})."
)
SENTENCE_TEMPLATE_UNKNOWN = (
    "주소가 확인되지 않아 전국 기본 보정계수 {mult}배를 적용했습니다"
    "(지역별 계수의 미등록 여부는 확인되지 않았습니다 · {caveat})."
)

# 매칭 층위 — 사유 문자열과 별개의 **안정 식별자**(표시 문구를 다듬어도 판정이 안 죽게).
SCOPE_DISTRICT = "DISTRICT"
SCOPE_REGION = "REGION"
SCOPE_DEFAULT = "DEFAULT"
# ★주소 자체가 없을 때 — 「미등록」과 **다른 사실**이다(2026-09-07 · 독립 리뷰 m-2).
#   SSOT 통합의 부수효과로 `comprehensive` 경로가 `None` 주소에 TypeError 대신 폴백하게 됐는데,
#   그것을 SCOPE_DEFAULT 로 뭉치면 «주소를 모른다» 가 «지역별 계수가 미등록이다» 라는
#   **다른 주장**으로 렌더된다(모름을 유효값으로 표현 — 이 저장소가 반복해 데인 형태).
SCOPE_UNKNOWN = "UNKNOWN_ADDRESS"


class MultiplierVerdict(NamedTuple):
    """계수와 **그것을 말하는 세 가지 방식**을 함께 나른다.

    · `multiplier` — 곱해지는 값
    · `short`      — 수식 안 연산 항 주석용(짧다 · 마침표 없다)
    · `sentence`   — 독립 문장용(주석·근거 줄)
    · `scope`      — 어느 층위에서 매칭됐나(기계 판독 축)
    · `provenance` — **출처 판정용 안정 코드**(표시 문구와 분리 — 문구를 바꿔도 안 죽는다)
    """

    multiplier: float
    short: str
    sentence: str
    scope: str
    provenance: str


def resolve_market_multiplier(address: str) -> MultiplierVerdict:
    """주소 → 계수와 사유. **계수로부터 어떤 통계도 역산하지 않는다.**

    종전에는 `100/계수` 를 「현실화율」이라 인쇄해, 고른 값을 고른 이유처럼 말했다. 지금은
    «사전 설정 계수를 적용했다» 는 사실과 «검증된 현실화율이 아니다» 라는 한정어만 말한다.

    네 층위가 **서로 다른** 문자열을 낸다 — 사용자가 "이 지역이 실제로 등록돼 있는가" ·
    "광역으로 떨어졌는가" · "전국 기본값인가" · "주소를 아예 모르는가" 를 구별해야 하기 때문이다.
    """
    if not (address or "").strip():
        return MultiplierVerdict(
            DEFAULT_MULTIPLIER,
            SHORT_TEMPLATE_UNKNOWN.format(caveat=SHORT_CAVEAT),
            SENTENCE_TEMPLATE_UNKNOWN.format(mult=DEFAULT_MULTIPLIER, caveat=UNVERIFIED_CAVEAT),
            SCOPE_UNKNOWN,
            PROVENANCE_UNVERIFIED_PRESET,
        )

    addr = address

    for district, mult in MARKET_MULTIPLIER_MAP.items():
        if district in addr:
            return MultiplierVerdict(
                mult,
                SHORT_TEMPLATE_DISTRICT.format(key=district, caveat=SHORT_CAVEAT),
                SENTENCE_TEMPLATE_DISTRICT.format(key=district, mult=mult, caveat=UNVERIFIED_CAVEAT),
                SCOPE_DISTRICT,
                PROVENANCE_UNVERIFIED_PRESET,
            )

    for region, mult in MARKET_MULTIPLIER_REGION.items():
        if region in addr:
            return MultiplierVerdict(
                mult,
                SHORT_TEMPLATE_REGION.format(key=region, caveat=SHORT_CAVEAT),
                SENTENCE_TEMPLATE_REGION.format(key=region, mult=mult, caveat=UNVERIFIED_CAVEAT),
                SCOPE_REGION,
                PROVENANCE_UNVERIFIED_PRESET,
            )

    return MultiplierVerdict(
        DEFAULT_MULTIPLIER,
        SHORT_TEMPLATE_DEFAULT.format(caveat=SHORT_CAVEAT),
        SENTENCE_TEMPLATE_DEFAULT.format(mult=DEFAULT_MULTIPLIER, caveat=UNVERIFIED_CAVEAT),
        SCOPE_DEFAULT,
        PROVENANCE_UNVERIFIED_PRESET,
    )
