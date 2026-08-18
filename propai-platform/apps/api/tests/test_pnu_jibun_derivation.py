"""PNU→지번 파생과 **응답 조립부 배선**을 함께 잠근다.

【무엇이 뚫렸었나 — 2026-08-18 사용자 신고】
77필지 목록이 전부 "경기도 오산시 내삼미동" 이었다. 두 결함이 겹쳤다:
  ① `/zoning/parcel-boundaries` 가 응답 `address` 에 **입력을 그대로 echo** — 동 단위 입력이
     동 단위로 나갔다(PNU 는 바로 위에서 해석해 놓고 쓰지 않았다).
  ② `/zoning/parcel-at-point` 가 `jibun` 에 **`address` 를 복제** — 지번 칸이 주소였다.
     소비처는 "jibun 이 있으니 지번이 있다"고 읽어 보강 기회를 잃는다.

【파생의 축】아래 배선 검사는 **함수 소스가 아니라 응답 딕셔너리 리터럴**을 본다. 헬퍼를
임포트만 하고 안 쓰면(가장 흔한 소비처 0) 잡히도록, 키가 헬퍼 호출에 결속됐는지 확인한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apps.api.app.utils.pnu import is_valid_pnu, jibun_from_pnu, parcel_display_address

ROUTER = Path(__file__).resolve().parents[1] / "routers" / "auto_zoning.py"


class TestJibunFromPnu:
    def test_일반필지_본번부번(self):
        # 사용자 화면에 실제로 찍힌 PNU
        assert jibun_from_pnu("4137011000104670001") == "467-1"

    def test_부번0이면_본번만(self):
        assert jibun_from_pnu("4137011000104670000") == "467"

    def test_산은_접두어를_붙인다(self):
        assert jibun_from_pnu("4137011000200120000") == "산12"

    @pytest.mark.parametrize("bad", [None, "", "123", "4137011000104670001X", "41370110001046700012"])
    def test_대조군_형식이_아니면_None(self, bad):
        # ★없으면 "무엇이든 지번으로 만든다"가 되어 날조가 화면에 나간다.
        assert jibun_from_pnu(bad) is None
        assert is_valid_pnu(bad) is False

    def test_본번0은_지번없음(self):
        assert jibun_from_pnu("4137011000100000000") is None


class TestParcelDisplayAddress:
    def test_동단위_주소에_지번을_붙인다(self):
        assert (
            parcel_display_address("경기도 오산시 내삼미동", "4137011000104670001")
            == "경기도 오산시 내삼미동 467-1"
        )

    def test_이미_지번이_있으면_중복하지_않는다(self):
        addr = "경기도 오산시 내삼미동 467-1"
        assert parcel_display_address(addr, "4137011000104670001") == addr

    def test_유사지번에_속지_않는다(self):
        # "467-10" 은 "467-1" 이 아니다 — 경계를 안 보면 중복표기를 잘못 억제한다.
        assert (
            parcel_display_address("경기도 오산시 내삼미동 467-10", "4137011000104670001")
            == "경기도 오산시 내삼미동 467-10 467-1"
        )

    def test_대조군_PNU가_없으면_주소를_그대로(self):
        assert parcel_display_address("경기도 오산시 내삼미동", None) == "경기도 오산시 내삼미동"

    def test_주소가_없으면_지번만(self):
        assert parcel_display_address(None, "4137011000104670001") == "467-1"


class TestResponseWiring:
    """★임포트만 하고 안 쓰는 '소비처 0' 을 잡는다 — 응답 키가 헬퍼에 결속됐는가."""

    @pytest.fixture(scope="class")
    def src(self) -> str:
        return ROUTER.read_text(encoding="utf-8")

    def test_전제_라우터를_실제로_읽었다(self, src):
        # 공허한 초록 방지 — 조회기가 죽으면 아래가 전부 무의미하게 통과한다.
        assert len(src) > 10_000
        assert "/parcel-boundaries" in src and "/parcel-at-point" in src

    def test_boundaries_주소가_파생헬퍼를_통과한다(self, src):
        assert re.search(r'"address":\s*parcel_display_address\(address,\s*pnu\)', src), (
            "parcel-boundaries 가 입력 주소를 그대로 echo 한다 — 동 단위 입력이 동 단위로 나간다"
        )
        assert re.search(r'"jibun":\s*jibun_from_pnu\(pnu\)', src)

    def test_boundaries_입력주소_원본을_남긴다(self, src):
        # ★표시를 보강하면서 매칭 키를 없애면 프론트 healParcelPnu 가 끊긴다(표시 고치다 배선 절단).
        assert re.search(r'"input_address":\s*address', src), (
            "input_address 가 없으면 프론트가 pnu 미확보 씨드를 주소로 찾지 못한다"
        )

    def test_at_point_지번이_주소의_복제가_아니다(self, src):
        assert '"jibun": pp.get("address")' not in src, "jibun 이 address 복제로 되돌아갔다"
        assert re.search(r'"jibun":\s*jibun_from_pnu\(pnu\)\s*or\s*""', src)
