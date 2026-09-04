"""주변 실거래 표본 선별 — 집계의 단일 통로(SSOT).

## 왜 이 모듈이 있는가

`NearbyMapService.build()` 의 `categories[*].groups` 는 **두 종류가 섞인** 리스트다:

- `location_status="located"`  — 좌표가 확인됐고, 반경 필터가 적용됐다면 그 반경을 통과한 그룹
- `location_status="unlocated"` — 지오코딩 실패로 **어디인지 모르는** 그룹(반경 밖으로 단정하지
  않기 위해 버리지 않고 보존한다 — 무날조 계약)

혼합 리스트를 그냥 순회해 평균을 내면 "위치를 모르는 거래"가 값에 섞이고, 그 값에 "반경 1km"
같은 라벨이 붙는 순간 **거짓 진술**이 된다. 2026-08-02 라이브 실측:

- 호미곶 대보리 산1-1: 전 카테고리 located 0건 / 표시 67건 → 표시된 평균가는 전부 20~30km 밖
  오천읍 거래에서 나왔다. 탁상감정 거래사례비교 단가가 공시지가 기준의 **36배**로 튀었다.
- 강남 역삼동 736: 아파트 located 18 / 105건, 토지 located 0 / 47건. 같은 오염이 감정단가를
  거꾸로 **38.5% 낮추기도** 했다 — 오염 방향은 일정하지 않아 "보수적이라 안전"이 성립하지 않는다.
- 강동 암사동 467: located 2,264 / 5,601건(40%).

즉 위치 미확인은 예외가 아니라 **상시 상태**(측정 범위에서 표본의 60~100%)다.

## 계약

1. 집계(평균·합계·단가·분위수)는 **`select_located_groups()` 가 돌려준 그룹으로만** 한다.
2. 표면 라벨은 **`SampleBasis.label()`** 로만 만든다. 요청 `radius_m` 을 직접 문자열에 넣지 않는다
   (반경 필터가 실제로 적용됐는지는 요청값이 아니라 응답의 `scope` 가 말해준다).
3. 표본이 0이면 값을 만들지 않고 **`no_sample_reason(basis)`**(모듈 함수)로 사유를 고지한다.
   "거래가 없다"와 "반경 안에서 위치가 확인된 거래가 없다"는 다른 상태다.
   `SampleBasis.no_sample_reason()` 은 그 함수로 위임하는 얇은 껍데기다 — 정의는 한 곳이다.

프론트 미러: `apps/web/lib/market/comparable-sample.ts` (같은 계약·같은 문구).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "SampleBasis",
    "is_masked_jibun",
    "no_sample_reason",
    "select_located_groups",
    "weighted_avg_price_10k",
    "weighted_unit_price_per_sqm",
]


def is_masked_jibun(jibun: str | None) -> bool:
    """MOLIT 이 **가려서 준 지번**인가(`"5*"` · `"1**"` · `"산1**"`).

    ★라이브 실측(2026-08-05 역삼동 3km·6개월): 건물명이 없는 카테고리는 지번이 **전부**
    마스킹돼 온다 — `land_trade` 13/13 · `house_trade` 12/12 · `commercial_trade` 6/34.
    그 결과 `"강남구 논현동 5*"` 같은 질의는 **원천적으로 필지 매칭이 불가능**하고,
    두 카테고리의 `located` 는 **구조적으로 0** 이 된다(탁상감정 거래사례비교의 진짜 병목).

    ★이건 **고칠 수 없는 데이터 한계**다 — 원천이 안 주는 것을 만들어낼 수는 없다.
    고칠 수 있는 것은 (a)매칭 불가한 질의에 예산을 쓰지 않는 것 (b)좌표를 **아는 척하지
    않는 것** (c)실패 계측을 오염시키지 않는 것 (d)소비처가 **"왜 표본이 0인지"** 를
    말할 수 있게 하는 것이다.

    ★★R1 리뷰(m-5) — 정의가 여기 하나여야 한다. 종전엔 `nearby_map_service._is_masked_jibun`
    과 이 모듈의 `"*" in str(...)` 리터럴이 **독립 정의** 둘이었고, 판정을 넓히자 한쪽만
    따라와 갈렸다(CLAUDE.md 전역 전파방지 위반). 생산처가 이 함수를 임포트해 쓴다.

    한국 지번 표기에 `*` 가 쓰이는 경우는 없으므로 판정은 문자 존재만으로 충분하다.
    """
    return "*" in (jibun or "")


@dataclass(frozen=True)
class SampleBasis:
    """집계값에 붙일 라벨의 **근거**. 라벨 문자열은 반드시 여기서만 만든다."""

    # "radius"(반경 적용) | "sigungu"(반경 미적용임을 **안다**) | "unknown"(알 수 없다)
    scope: str
    radius_applied: bool
    radius_m: int | None
    located_count: int
    approximate_count: int
    unlocated_count: int
    capped_count: int
    # ★원천(MOLIT)이 지번을 가려서 준 **거래 건수** — 이 물건들은 질의를 만들 수 없어
    #   좌표가 없고, 따라서 `located_count` 에 들어오지 못한다. "거래가 없다"와 "거래는
    #   있는데 위치를 못 잡는다"를 소비처가 구분하려면 이 수가 필요하다.
    #   ★단위는 이 dataclass 의 다른 카운트와 같은 **거래 건수**다(R1 리뷰 M-1 — 초판은
    #   그룹 수를 넣고 "거래 N건"이라 렌더해 H-4 단위 혼입을 재생산했다). 물건 수는
    #   `masked_jibun_group_count` 로 따로 보존한다. 구버전 페이로드엔 없으므로 기본 0.
    #   ★★R5 리뷰(F-8) 정직 표기 — 실제 계산값은 "원천이 지번을 가려서 준 거래 건수"가
    #   아니라 **"대표 지번이 마스킹인 그룹의 전체 거래 수"** 다. 두 방향으로 어긋난다:
    #     · 과대 — 그 그룹이 `jibun=""` 행을 흡수하면 그 행까지 센다.
    #     · 과소 — 그룹이 비마스킹 지번으로 확정되면(`_resolve_group_queries`) 그 안의
    #              마스킹 행은 빠진다.
    #   ★그럼에도 **현재 계산이 옳다**. 이 값의 유일한 소비처는 `no_sample_reason` 이고
    #   그건 `located == 0` 일 때만 발화한다. 지번이 확정된 그룹은 표본 부재의 원인이
    #   아니고(좌표를 잡았거나, 못 잡았다면 원인은 마스킹이 아니라 지오코딩 실패다),
    #   여기서 세야 할 것은 "**질의조차 만들지 못해** 표본에서 빠진 거래"이기 때문이다.
    #   → 코드가 아니라 **이 설명**을 계산값에 맞춘다.
    masked_jibun_count: int = 0
    masked_jibun_group_count: int = 0
    # ★2026-08-06 — 표본에 섞인 **지분거래** 건수. 원천(`shareDealingType`)이 주는 구분인데
    #   파서가 버려서 종전엔 관측 자체가 불가능했다. 라이브 실측(3지역·30개월 3,113건)에서
    #   지분/일반 단가 비가 **지역마다 방향까지 다르다**(강남 0.27배 · 해운대 0.65배 ·
    #   포항북 2.14배). 섞인 채로 대표값을 말하면 그 값이 무엇인지 아무도 모른다.
    #   구버전 페이로드엔 없으므로 기본 0.
    share_deal_count: int = 0

    @property
    def has_sample(self) -> bool:
        return self.located_count > 0

    def label(self) -> str:
        """이 표본이 실제로 무엇인지 한 구절로. 반경을 적용하지 않았으면 반경을 말하지 않는다."""
        if self.scope == "radius" and self.radius_m:
            km = self.radius_m / 1000.0
            # 1000m → "1km", 1500m → "1.5km" (불필요한 소수점 제거)
            km_txt = f"{km:g}km"
            return f"반경 {km_txt} 내 위치 확인 거래"
        if self.scope == "sigungu":
            return "시군구 전체(반경 미적용)"
        # ★W1-b 리뷰(M-1) — 구버전 페이로드는 반경 적용 여부를 **알 수 없다**. 종전엔 이때도
        #   "반경 미적용"이라 단정했는데, 실제로는 구 백엔드도 반경을 적용하고 있었다.
        #   이 모듈의 존재 이유가 "모르는 것을 단정하지 마라"인데 그 원칙을 어기는 자리였다.
        return "표본 범위 확인 불가"

    def exclusion_note(self) -> str | None:
        """집계에서 빠진 것을 밝힌다. 빠진 게 없으면 None(없는 말을 지어내지 않는다)."""
        parts: list[str] = []
        if self.unlocated_count > 0:
            parts.append(f"위치 미확인 {self.unlocated_count:,}건")
        if self.approximate_count > 0:
            parts.append(f"위치 개략(동 단위) {self.approximate_count:,}건")
        if self.capped_count > 0:
            parts.append(f"표시 상한 초과 {self.capped_count:,}건")
        if not parts:
            return None
        return " · ".join(parts) + " 집계 제외"

    def no_sample_head(self) -> str:
        """표본 0 사유의 **서두**. `label()` 은 명사구라 "~가 없습니다"를 붙이면 비문이 된다.

        ★R1 리뷰(m-4) — 초판은 `f"{label()}가 없습니다"` 로 조립해
        `"시군구 전체(반경 미적용)가 없습니다"` · `"표본 범위 확인 불가가 없습니다"` 같은
        문장을 만들었다(현재 호출부가 `scope=="radius"` 가지뿐이라 잠복 상태였다).
        범위별로 **문장을 통째로** 만든다.
        """
        if self.scope == "radius" and self.radius_m:
            return f"반경 {self.radius_m / 1000.0:g}km 내에서 위치가 확인된 거래가 없습니다"
        if self.scope == "sigungu":
            return "시군구 전체에서 위치가 확인된 거래가 없습니다"
        return "위치가 확인된 거래가 없습니다"

    def no_sample_reason(self) -> str:
        """표본 0일 때의 사유.

        ★R1 리뷰(M-4) — 정의는 **모듈 함수 하나**다. 종전엔 이 메서드와 모듈 함수가
        독립 구현이라 **같은 근거에 다른 답**을 냈고, 유일한 기존 소비처
        (`ai/assistant_agent`)는 메서드를 쓰고 있어 **AI 비서는 마스킹 사유를 영영
        말하지 못했다**(CLAUDE.md 전역 전파방지 미이행). 여기서는 위임만 한다.
        """
        return no_sample_reason(self) or "해당 조건에서 수집된 실거래가 없습니다."


def _masked_from_groups(cat: dict[str, Any]) -> tuple[int, int]:
    """`groups` 에서 마스킹 (거래 건수, 물건 수) 를 직접 센다 — 신형 키가 없을 때의 복원 경로."""
    deals = 0
    groups = 0
    for g in cat.get("groups") or []:
        if is_masked_jibun(g.get("jibun")):
            groups += 1
            deals += int(g.get("count") or 0)
    return deals, groups


def _basis_from_category(cat: dict[str, Any] | None) -> SampleBasis:
    cat = cat or {}
    raw = cat.get("sample_basis")
    if isinstance(raw, dict):
        # ★★R1 리뷰(M-5) — 키 **부재**와 값 **0** 을 구분한다.
        #   초판이 방어한 것은 `sample_basis` **자체가 없는** 아주 옛 응답인데, 그 필드는
        #   W1-b 이후 상시 존재하므로 실제 배포 스큐는 **"`sample_basis` 는 있고 마스킹
        #   키만 없는"** 형태다. 초판은 그 경우 `or 0` 으로 **0 이라고 단정**했다 —
        #   "모르는 것을 0 으로 단정하지 않는다"는 이 모듈의 선언이 정작 실제 스큐 구간에서
        #   거짓이 되고, 그 구간 내내 마스킹 사유가 **조용히 사라진다**.
        _md = raw.get("masked_jibun_count")
        _mg = raw.get("masked_jibun_group_count")
        if _md is None or _mg is None:
            _fd, _fg = _masked_from_groups(cat)   # 이 갈래에서만 필요하므로 여기서 센다
            _md = _fd if _md is None else _md
            _mg = _fg if _mg is None else _mg
        return SampleBasis(
            scope=str(raw.get("scope") or "sigungu"),
            radius_applied=bool(raw.get("radius_applied")),
            radius_m=raw.get("radius_m"),
            located_count=int(raw.get("located_count") or 0),
            approximate_count=int(raw.get("approximate_count") or 0),
            unlocated_count=int(raw.get("unlocated_count") or 0),
            capped_count=int(raw.get("capped_count") or 0),
            masked_jibun_count=int(_md or 0),
            masked_jibun_group_count=int(_mg or 0),
            # ★신형 페이로드에만 있다 — 구버전엔 축 자체가 없으므로 0(모르는 것을 세지 않는다).
            share_deal_count=int(raw.get("share_deal_count") or 0),
        )
    _legacy_masked = _masked_from_groups(cat)   # ★L-5 — 분기마다 두 번 세지 않는다.
    # ★구버전 페이로드(캐시·배포 스큐) 폴백 — sample_basis 가 없던 시절의 응답도 안전하게
    #   다룬다. 이때는 카운트 필드에서 복원하고, 알 수 없으면 보수적으로 "반경 미적용"으로 본다
    #   (모르면 반경을 주장하지 않는다 = 이 모듈의 존재 이유와 같은 방향).
    return SampleBasis(
        # ★단정하지 않는다 — 반경을 적용했는지 **모르는** 상태다(label() 주석 참조).
        scope="unknown",
        radius_applied=False,
        radius_m=None,
        located_count=int(cat.get("count_in_radius") or 0),
        approximate_count=int(cat.get("count_approximate") or 0),
        unlocated_count=int(cat.get("count_unresolved") or 0),
        capped_count=int(cat.get("capped_count") or 0),
        # 구버전 페이로드엔 이 축이 없다 — **모르는 것을 0 으로 단정하지 않고** 그룹에서 센다.
        masked_jibun_count=_legacy_masked[0],
        masked_jibun_group_count=_legacy_masked[1],
        # ★구버전 페이로드엔 이 축이 없다 — masked 와 같은 규율로 **그룹에서 센다**
        #   (0 으로 단정하지 않는다). 그룹에도 없으면 그때는 진짜 0이다.
        share_deal_count=sum(
            int(g.get("share_deal_count") or 0) for g in (cat.get("groups") or [])
        ),
    )


def no_sample_reason(basis: SampleBasis) -> str | None:
    """표본이 **왜** 0인지 한 구절로. 표본이 있으면 None.

    ★이 함수가 없던 동안 탁상감정은 `scope=="radius"` 인데 `located` 가 0 이면 **아무 사유
    없이** 공시지가 기준으로 폴백했다. 사용자는 "왜 거래사례비교를 안 썼는지" 알 수 없었다.

    ★"거래가 없다"와 "거래는 있는데 원천이 지번을 가려 위치를 못 잡는다"는 **전혀 다른 상태**다.
      후자는 우리가 고칠 수 없는 **데이터 한계**이고, 그 사실을 말해 주는 것이 정직이다.
    """
    if basis.has_sample:
        return None

    # ★★R1 리뷰(M-3) — **배타 분기가 아니라 누적 서술**이다.
    #   초판은 `masked > 0` 이 **크기와 무관하게** 선점해, 마스킹 1건이 위치 미확인 80건을
    #   가리고 그 80건이 문장에서 통째로 사라졌다 — 사용자에게 **틀린 이유**를 말하는 것이고,
    #   틀린 이유는 침묵보다 나쁠 수 있다. 전부 나열하면 우선순위 논쟁 자체가 사라진다.
    # ★m-3 — 0 인 항목은 문장에 넣지 않는다("위치 미확인 0건" 같은 잡음 제거).
    # ★★R2 리뷰(M-2) — 카운트 항과 **이유 문장을 분리**한다.
    #   초판은 이유를 항 안에 넣어 세 가지를 한꺼번에 만들었다:
    #     (a) 이중계수 — "위치 미확인 1건 · 지번이 가려진 거래 3건 · 동 단위 2건"이
    #         실거래 3건을 **6건으로** 읽히게 했다(M-3 이 없애려던 그 문제를 폴백 갈래가 재생산).
    #     (b) `—` 가 한 문장에 두 번 나와 절 구조가 무너졌다.
    #     (c) `…확인할 수 없습니다은 단가 산정에…` 비문 — m-4 가 고친 "명사구+조사" 결합
    #         결함을 다른 자리에서 재생산했다.
    #   → 항은 **명사구+건수**만, 마스킹 이유는 **문장 끝에 한 번**.
    _why = "공개 실거래 자료가 지번을 가려서 제공해(예: 5*, 1**) 위치를 확인할 수 없습니다"
    _masked = basis.masked_jibun_count

    bits: list[str] = []
    # ★m-3 — 0 인 항목은 넣지 않는다("위치 미확인 0건" 같은 잡음 제거).
    if basis.unlocated_count > 0:
        bits.append(f"위치 미확인 {basis.unlocated_count:,}건")
    if basis.approximate_count > 0:
        bits.append(f"동 단위까지만 확인 {basis.approximate_count:,}건")

    # ★마스킹은 **위치 미확인의 부분집합이자 그 원인**이다(질의를 만들 수 없어 좌표가 없다).
    #   그래서 카운트를 항으로 더하지 않는다 — 더하면 같은 거래를 두 번 세는 것이다.
    #   스큐로 두 수가 어긋나면 포함 관계를 **주장할 수 없으므로** 그 사실을 말한다.
    tail = ""
    if _masked > 0:
        if _masked <= basis.unlocated_count:
            tail = f" 위치 미확인 중 {_masked:,}건은 {_why}."
        else:
            # ★R3 리뷰(F-5) — "그 밖에"는 **서로소를 적극 주장**한다. 독자는 앞 건수와
            #   더해서 읽고, 그러면 M-2 가 없앤 이중계수가 **어법으로** 되살아난다.
            #   이 갈래의 사실은 "포함 관계를 **모른다**"이므로 그렇게 쓴다.
            # ★★R4 리뷰(M-1·M-2) — "위 건수"는 지시 대상이 **없거나 틀렸다**.
            #   `u=0 a=0 m>0` 이면 앞에 건수가 하나도 없어 가리킬 것이 없고,
            #   `u=0 a>0 m>0` 이면 앞의 유일한 건수가 "동 단위 확인분"이라 그쪽을 가리키는
            #   것으로 읽힌다 — 마스킹은 **위치 미확인**의 부분집합이지 동 단위 확인분과는
            #   무관하다. 오독 하나를 없애고 다른 오독을 넣은 셈이라 **대상을 명시**하고,
            #   앞 건수가 없으면 그 괄호를 **아예 생략**한다.
            _rel = (
                "(위 '위치 미확인' 건수에 포함되는지는 확인할 수 없습니다)"
                if basis.unlocated_count > 0
                else ""
            )
            tail = f" 지번이 가려진 거래는 {_masked:,}건으로 집계됐습니다{_rel} — {_why}."

    # ★2026-08-06 — 지분거래 고지는 여기 넣지 않는다(작성 중 자체 반증).
    #   ① `no_sample_reason` 은 **표본이 0일 때만** 발화한다. 아무것도 안 쓴 상태에서
    #      "지분이 섞였다"고 말해 봐야 무엇에 대한 설명도 되지 못한다.
    #   ② 문구가 실제로 모순을 냈다 — "위치 미확인 5건" 뒤에 "이 가운데 12건"이 붙었다
    #      (지분 수는 전체 표본 기준이라 위치 미확인 수보다 클 수 있다). R6 M-1·M-2 에서
    #      고친 "지시 대상이 없거나 틀린 문구"와 **같은 결함 클래스**를 재생산할 뻔했다.
    #   → 지분은 **계측 필드로만** 노출한다(`share_deal_count`). 문구가 필요한 자리는
    #     표본을 **실제로 쓰는** 소비처이고, 그 경로가 생길 때 그쪽에서 말하는 것이 옳다.
    if not bits:
        if tail:
            return f"{basis.no_sample_head()}.{tail}"
        return f"{basis.no_sample_head()}(해당 기간·범위에 수집된 거래가 없습니다)."
    return (
        f"{basis.no_sample_head()} — {' · '.join(bits)}은 단가 산정에 쓰지 않습니다.{tail}"
    )


def select_located_groups(
    cat: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], SampleBasis]:
    """카테고리에서 **위치가 확인된** 그룹만 골라 근거와 함께 돌려준다.

    집계를 하려는 모든 코드는 이 함수를 통과해야 한다. `cat["groups"]` 를 직접 순회하면
    위치 미확인 그룹이 섞인다.
    """
    cat = cat or {}
    groups = cat.get("groups") or []
    located: list[dict[str, Any]] = []
    for g in groups:
        status = g.get("location_status")
        if status is None:
            # ★구버전 페이로드 폴백(캐시·배포 스큐). 좌표 유무만으로 판정하되, 정밀도 필드가
            #   있으면 그것까지 본다 — 없으면 "그 시절의 최선"으로 두고, 대신 여기서 만든
            #   표본이 실제보다 낙관적일 수 있다는 사실은 `location_status` 도입 이후
            #   자동으로 해소된다(신규 응답에는 항상 필드가 있다).
            if g.get("lat") is None:
                status = "unlocated"
            elif g.get("coord_precision") == "masked":
                # ★R3 리뷰(F-9) — 4번째 enum 값을 추가하면서 양쪽 레거시 폴백을 손대지
                #   않으면 두 미러가 조용히 갈라진다. **실제로 갈려 있었다** —
                #   백엔드는 `else` 로 떨어져 `approximate`, 프론트는 `!== "dong"` 이라
                #   `located` 였다. 위험한 쪽은 프론트다(마스킹을 집계에 넣는다).
                #   마스킹은 좌표가 **없다**는 뜻이므로 정밀을 주장하지 않는다.
                # ★정직 표기 — 이 한 줄은 **변이로 잠기지 않는다**. 지워도 `else` 가
                #   `approximate` 를 주고, 둘 다 `located` 가 아니라 이 함수의 반환값이
                #   같기 때문이다(하류 영향 0). 의미 정합을 위한 줄이며, 실제로 고쳐야
                #   했던 곳은 **프론트 미러**다(그쪽은 회귀락이 잡는다).
                status = "unlocated"
            elif g.get("coord_precision") in ("parcel", "building", None):
                status = "located"
            else:
                status = "approximate"
        if status == "located":
            located.append(g)
    return located, _basis_from_category(cat)


def weighted_avg_price_10k(groups: Iterable[dict[str, Any]]) -> int | None:
    """거래건수 가중 평균가(만원). 표본이 없거나 가격이 없으면 **None**(0을 지어내지 않는다)."""
    total_w = 0
    acc = 0.0
    for g in groups:
        price = g.get("avg_price_10k") or 0
        if price <= 0:
            continue
        w = max(1, int(g.get("count") or 0))
        acc += float(price) * w
        total_w += w
    if total_w <= 0:
        return None
    return int(round(acc / total_w))


def weighted_unit_price_per_sqm(groups: Iterable[dict[str, Any]]) -> float | None:
    """거래건수 가중 ㎡당 단가(원). 면적이 없는 그룹은 단가를 만들 수 없으므로 제외한다."""
    total_w = 0
    acc = 0.0
    for g in groups:
        price_10k = g.get("avg_price_10k") or 0
        area = g.get("avg_area_m2") or 0
        if price_10k <= 0 or area <= 0:
            continue
        w = max(1, int(g.get("count") or 0))
        acc += (float(price_10k) * 10000.0 / float(area)) * w
        total_w += w
    if total_w <= 0:
        return None
    return acc / total_w
