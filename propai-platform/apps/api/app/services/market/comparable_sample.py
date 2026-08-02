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
3. 표본이 0이면 값을 만들지 않고 **`SampleBasis.no_sample_reason()`** 으로 사유를 고지한다.
   "거래가 없다"와 "반경 안에서 위치가 확인된 거래가 없다"는 다른 상태다.

프론트 미러: `apps/web/lib/market/comparable-sample.ts` (같은 계약·같은 문구).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "SampleBasis",
    "select_located_groups",
    "weighted_avg_price_10k",
    "weighted_unit_price_per_sqm",
]


@dataclass(frozen=True)
class SampleBasis:
    """집계값에 붙일 라벨의 **근거**. 라벨 문자열은 반드시 여기서만 만든다."""

    scope: str  # "radius" | "sigungu"
    radius_applied: bool
    radius_m: int | None
    located_count: int
    approximate_count: int
    unlocated_count: int
    capped_count: int

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
        return "시군구 전체(반경 미적용)"

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

    def no_sample_reason(self) -> str:
        """표본 0일 때의 사유. 왜 없는지에 따라 문장이 달라야 한다."""
        excluded = self.unlocated_count + self.approximate_count
        if excluded > 0:
            bits: list[str] = []
            if self.unlocated_count:
                bits.append(f"위치 미확인 {self.unlocated_count:,}건")
            if self.approximate_count:
                bits.append(f"동 단위까지만 확인된 {self.approximate_count:,}건")
            return (
                f"{self.label()}를 찾지 못했습니다"
                f"({' · '.join(bits)}은 집계에 쓰지 않습니다)."
            )
        return "해당 조건에서 수집된 실거래가 없습니다."


def _basis_from_category(cat: dict[str, Any] | None) -> SampleBasis:
    cat = cat or {}
    raw = cat.get("sample_basis")
    if isinstance(raw, dict):
        return SampleBasis(
            scope=str(raw.get("scope") or "sigungu"),
            radius_applied=bool(raw.get("radius_applied")),
            radius_m=raw.get("radius_m"),
            located_count=int(raw.get("located_count") or 0),
            approximate_count=int(raw.get("approximate_count") or 0),
            unlocated_count=int(raw.get("unlocated_count") or 0),
            capped_count=int(raw.get("capped_count") or 0),
        )
    # ★구버전 페이로드(캐시·배포 스큐) 폴백 — sample_basis 가 없던 시절의 응답도 안전하게
    #   다룬다. 이때는 카운트 필드에서 복원하고, 알 수 없으면 보수적으로 "반경 미적용"으로 본다
    #   (모르면 반경을 주장하지 않는다 = 이 모듈의 존재 이유와 같은 방향).
    return SampleBasis(
        scope="sigungu",
        radius_applied=False,
        radius_m=None,
        located_count=int(cat.get("count_in_radius") or 0),
        approximate_count=int(cat.get("count_approximate") or 0),
        unlocated_count=int(cat.get("count_unresolved") or 0),
        capped_count=int(cat.get("capped_count") or 0),
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
