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
