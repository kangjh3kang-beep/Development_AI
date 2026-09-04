"""주소 **해상도** — 동 단위 주소가 지오코딩으로 흘러가지 않게 한다(D8).

★화면감사 실측(2026-08-24): 통합 시나리오의 대표 주소가 `"경기도 오산시 내삼미동"`
  (번지 없음)이라 지오코딩이 **엉뚱한 필지**를 집었고, `zone_basis="representative_parcel"`
  라벨까지 거짓이 됐다 — 대표(첫) 필지조차 다른 용도지역이었다.

★"주소가 없다"와 "주소는 있는데 거칠다"는 **다른 상태**다. 후자가 더 위험하다 —
  조회가 **성공하고 틀린 값**을 준다(실패하면 차라리 드러난다).

★없는 걸 새로 만든 게 아니다 — `parcel_display_address` 는 **이미 있었고 같은 파일이
  두 곳(:901 · :2240)에서 쓰고 있었다.** 세 번째 자리(`rep_addr`)만 raw 였다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apps.api.app.utils.pnu import (
    RESOLUTION_DONG_ONLY,
    RESOLUTION_JIBUN,
    RESOLUTION_NONE,
    address_resolution,
    pick_representative_parcel,
)

_OSAN_PNU = "4137011000104670001"   # 오산 내삼미동 467-1


class Test해상도판정:
    def test_동_단위는_dong_only(self) -> None:
        assert address_resolution("경기도 오산시 내삼미동") == RESOLUTION_DONG_ONLY

    def test_번지가_있으면_jibun(self) -> None:
        assert address_resolution("경기도 오산시 내삼미동 467-1") == RESOLUTION_JIBUN
        assert address_resolution("경기도 오산시 내삼미동 467") == RESOLUTION_JIBUN
        assert address_resolution("강원도 평창군 봉평면 산 12") == RESOLUTION_JIBUN

    def test_주소가_없으면_none(self) -> None:
        assert address_resolution("") == RESOLUTION_NONE
        assert address_resolution(None) == RESOLUTION_NONE

    def test_PNU가_있으면_동_단위여도_해상_가능(self) -> None:
        """지번을 파생할 수 있으면 jibun 이다 — `parcel_display_address` 가 붙여 준다."""
        assert address_resolution("경기도 오산시 내삼미동", _OSAN_PNU) == RESOLUTION_JIBUN

    def test_본번_0인_PNU는_해상_불가(self) -> None:
        """★특이도 — PNU 가 있다고 무조건 jibun 이 아니다(본번 0 = 지번 없음)."""
        assert address_resolution("경기도 오산시 내삼미동", "4137011000100000000") == RESOLUTION_DONG_ONLY

    def test_없는것과_거친것은_다른_값이다(self) -> None:
        """★두 상태가 같은 값을 내면 소비처가 구분할 수 없다."""
        assert address_resolution(None) != address_resolution("경기도 오산시 내삼미동")


class Test대표필지선택:
    def test_지번_해상된_필지를_고른다(self) -> None:
        """★종전엔 **첫 필지**를 집었다 — 그게 동 단위면 거친 주소가 그대로 흘러간다."""
        parcels = [
            {"address": "경기도 오산시 내삼미동", "pnu": None},          # 거칠다(첫 필지)
            {"address": "경기도 오산시 내삼미동 467-1", "pnu": _OSAN_PNU},  # 해상됨
        ]
        rep = pick_representative_parcel(parcels)
        assert rep is not None and rep["pnu"] == _OSAN_PNU, (
            f"첫 필지(동 단위)를 그대로 집었다: {rep}"
        )

    def test_두_모집단이_실제로_갈린다(self) -> None:
        """★픽스처가 두 모집단을 갈라야 한다 — 다 해상되면 배선을 끊어도 결과가 같다."""
        rough = [{"address": "경기도 오산시 내삼미동", "pnu": None},
                 {"address": "경기도 오산시 내삼미동", "pnu": None}]
        mixed = [{"address": "경기도 오산시 내삼미동", "pnu": None},
                 {"address": "경기도 오산시 내삼미동 467-1", "pnu": _OSAN_PNU}]
        assert pick_representative_parcel(rough)["pnu"] is None      # 고를 게 없다 → 폴백
        assert pick_representative_parcel(mixed)["pnu"] == _OSAN_PNU  # 해상된 것을 고른다

    def test_전부_거칠면_정직하게_폴백한다(self) -> None:
        rep = pick_representative_parcel([{"address": "경기도 오산시 내삼미동"}])
        assert rep is not None, "고를 게 없다고 None 을 주면 상류가 주소를 잃는다"

    def test_빈_입력은_None(self) -> None:
        assert pick_representative_parcel([]) is None
        assert pick_representative_parcel(None) is None


class Test배선:
    """★순수 함수만 잠그면 **호출부가 안 써도 초록**이다(이 세션에서 실증했다)."""

    @pytest.fixture
    def src(self) -> str:
        import sys

        p = Path(__file__).resolve().parents[1] / "routers" / "auto_zoning.py"
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests"))
        from _scan_guard import code_lines, read  # noqa: PLC0415

        return code_lines(read(p, must_exist_reason="auto_zoning 라우터가 사라졌다"))

    def test_rep_addr가_대표필지_선택기를_통과한다(self, src: str) -> None:
        # 공허 방지 대조군 — 이 파일에 반드시 있는 것
        assert "auto_recommend_top3" in src, "대상 파일이 틀렸다(조회기 사망)"
        assert re.search(r"rep_parcel\s*=\s*pick_representative_parcel\(", src), (
            "대표 주소를 여전히 **첫 필지**에서 집는다 — 그게 동 단위면 지오코딩이 "
            "엉뚱한 필지를 집는다(D8 실측)"
        )

    def test_rep_addr가_지번을_붙여_나간다(self, src: str) -> None:
        # ★줄바꿈·괄호 감싸기를 허용한다 — 종전 패턴은 `rep_addr = (\n    parcel_display_address(`
        #   형태를 **위반으로 신고**했다(정상 코드를 막는 가드도 결함이다 §A-6).
        assert re.search(r"rep_addr\s*=\s*\(?\s*parcel_display_address\(", src), (
            "같은 파일 :901 · :2240 은 parcel_display_address 를 쓰는데 "
            "여기만 raw 주소다 — 없는 게 아니라 **안 쓴 것**이다"
        )

    def test_해상도를_응답에_싣는다(self, src: str) -> None:
        assert re.search(r'"address_resolution"\s*:', src), (
            "해상도를 응답에 싣지 않으면 소비처가 '이 주소를 믿어도 되는지' 알 수 없다"
        )


class Test시군구걸침:
    """★D8 전역 스윕이 드러낸 **인접 결함** — 조례를 첫 필지 것으로 조용히 정한다.

    스윕은 `auto_zoning.py:1964`(`up_addr`)를 같은 패턴으로 집었는데, 재보니 **D8 결함은
    아니었다** — 그 값은 `_extract_sigungu` 로만 가고 시군구는 동보다 **거친** 단위라
    동 단위 주소로도 같은 답('오산시')을 준다(실측). **위양성이다.**

    그런데 같은 자리에서 **다른 진짜 결함**이 나왔다: `next(...)` 가 **첫 필지**의 시군구를
    뽑아 **전체 조례**에 쓴다. 필지가 시군구를 걸치면 나머지 필지에 **틀린 조례**가 적용된다.

    ★실측(같은 용도지역·면적, 시군구만 변경 — `far_tier_service.calc_upzoning`):
        오산시 250%  ·  **성남시 280%**  ·  강남구 250%  ·  미확보 300%(법정 폴백=과대)
    → **30%p 격차**. 숫자가 틀렸다기보다 **"누구의 조례인지"를 말하지 않는 것**이 결함이다.
    """

    def test_시군구가_갈리면_사실을_말한다(self) -> None:
        from apps.api.app.utils.pnu import sigungu_spread
        spread = sigungu_spread([
            {"address": "경기도 오산시 내삼미동 467-1"},
            {"address": "경기도 성남시 분당구 정자동 1-1"},
        ])
        assert spread["count"] == 2, spread
        assert spread["mixed"] is True
        assert spread["disclosure"], "걸침을 감지했는데 고지 문구가 없다"
        assert "오산시" in spread["disclosure"] and "성남시" in spread["disclosure"], (
            f"어느 시군구들인지 말하지 않는다: {spread['disclosure']}"
        )

    def test_단일_시군구면_고지하지_않는다(self) -> None:
        """★특이도 — 정상 케이스에 경고를 붙이면 그것도 결함이다."""
        spread = sigungu_spread_of([
            {"address": "경기도 오산시 내삼미동 467-1"},
            {"address": "경기도 오산시 내삼미동 468"},
        ])
        assert spread["count"] == 1 and spread["mixed"] is False
        assert not spread["disclosure"], f"단일 시군구인데 경고를 낸다: {spread}"

    def test_두_모집단이_갈린다(self) -> None:
        single = sigungu_spread_of([{"address": "경기도 오산시 내삼미동 467-1"}])
        multi = sigungu_spread_of([
            {"address": "경기도 오산시 내삼미동 467-1"},
            {"address": "서울특별시 강남구 논현동 1-1"},
        ])
        assert single["mixed"] != multi["mixed"], "걸침 유무가 같은 값을 낸다"

    def test_주소_없으면_세지_않는다(self) -> None:
        s = sigungu_spread_of([{"address": ""}, {"address": None}])
        assert s["count"] == 0 and s["mixed"] is False and not s["disclosure"]

    def test_배선_종상향이_걸침_고지를_싣는다(self) -> None:
        """★배선 락 — 순수 함수만 잠그면 호출부가 안 써도 초록이다(이 세션 실증)."""
        import sys
        from pathlib import Path as _P
        sys.path.insert(0, str(_P(__file__).resolve().parents[3] / "tests"))
        from _scan_guard import code_lines, read  # noqa: PLC0415

        src = code_lines(read(
            _P(__file__).resolve().parents[1] / "routers" / "auto_zoning.py",
            must_exist_reason="auto_zoning 라우터가 사라졌다"))
        assert "calc_upzoning" in src, "대상 파일이 틀렸다(조회기 사망 대조군)"
        assert re.search(r"up_spread\s*=\s*sigungu_spread\(", src), (
            "종상향이 시군구 걸침을 재지 않는다 — 첫 필지 조례가 전체에 조용히 적용된다"
        )
        assert re.search(r'upzoning\["sigungu_disclosure"\]', src), (
            "걸침을 감지하고도 응답에 고지하지 않는다(무언 적용)"
        )


def sigungu_spread_of(parcels):
    from apps.api.app.utils.pnu import sigungu_spread
    return sigungu_spread(parcels)
