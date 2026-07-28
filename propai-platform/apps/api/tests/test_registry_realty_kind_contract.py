"""등기 조회 — 부동산 구분 계약·물건 선택 회귀망.

배경(실장애):
    하이픈 이관 커밋(588ea8ed)이 RegistryService.get_one을 재작성하면서
    realty_type/dong/ho 세 파라미터를 시그니처에서 누락했는데 호출부는 그대로 남아
    `TypeError: get_one() got an unexpected keyword argument 'realty_type'`로
    등기 권리분석이 100% 실패했다. 이 파일은 그 계약과, 뒤이어 드러난
    '검색결과 첫 건 맹목 선택'(사용자가 고른 구분과 다른 물건 열람)을 함께 고정한다.
"""

from __future__ import annotations

import inspect

import pytest

from app.services.registry.realty_kind import (
    matches_realty_kind,
    realty_kind_label,
    select_registry_item,
)
from app.services.registry.registry_service import RegistryService


class TestGetOneSignatureContract:
    """호출부가 실제로 넘기는 인자를 get_one이 받아야 한다(실장애 재발 방지)."""

    def test_get_one_accepts_caller_kwargs(self):
        params = inspect.signature(RegistryService.get_one).parameters
        # registry_analysis_service가 넘기는 인자 전량
        for name in ("pnu", "address", "realty_type", "dong", "ho"):
            assert name in params, f"get_one이 '{name}'를 받지 못함 — 호출부와 계약 파열"

    def test_analysis_service_call_binds_without_typeerror(self):
        """호출부와 동일한 키워드 조합이 시그니처에 바인딩되는지 정적 검증."""
        sig = inspect.signature(RegistryService.get_one)
        # self는 bound method 가정 → 제외하고 바인딩
        sig.bind_partial(
            None, pnu="1111", address="서울시 ...", realty_type="1", dong="101", ho="1502"
        )


class TestRealtyKindMatching:
    def test_none_or_zero_means_all(self):
        assert matches_realty_kind("토지", None) is True
        assert matches_realty_kind("집합건물", "0") is True

    @pytest.mark.parametrize(
        ("gubun", "realty_type", "expected"),
        [
            ("집합건물", "1", True),
            ("토지", "2", True),
            ("건물", "3", True),
            ("토지", "1", False),
            ("집합건물", "2", False),
        ],
    )
    def test_basic_matching(self, gubun, realty_type, expected):
        assert matches_realty_kind(gubun, realty_type) is expected

    def test_ordinary_building_must_not_match_collective(self):
        """★부분문자열 함정: '집합건물'에 '건물'이 들어있다 — 3(건물)에 걸리면 안 됨."""
        assert matches_realty_kind("집합건물", "3") is False

    def test_missing_gubun_is_not_a_match(self):
        assert matches_realty_kind(None, "2") is False
        assert matches_realty_kind("", "2") is False

    @pytest.mark.parametrize(
        ("gubun", "realty_type", "expected"),
        [
            # 등기 실무에서 집합건물을 '구분건물'로 표기 — '건물'(3)로 새면 안 된다
            ("구분건물", "1", True),
            ("구분건물", "3", False),
            ("구분소유건물", "1", True),
            ("구분소유건물", "3", False),
            ("집합건물(구분건물)", "1", True),
            ("집합 건물", "1", True),      # 공백 표기 정규화
            ("일반건물", "3", True),
            ("토지및건물", "3", True),     # 복합 표기는 해당 구분으로 인정
            # 프로바이더가 표기 대신 코드를 주는 경우
            ("1", "1", True),
            ("1", "3", False),
            ("2", "2", True),
        ],
    )
    def test_provider_vocabulary_variants(self, gubun, realty_type, expected):
        assert matches_realty_kind(gubun, realty_type) is expected

    def test_label_lookup(self):
        assert realty_kind_label("1") == "집합건물"
        assert realty_kind_label("2") == "토지"
        assert realty_kind_label("0") is None
        assert realty_kind_label(None) is None


class TestSelectRegistryItem:
    LAND = {"unique_no": "L1", "gubun": "토지", "jibun": "대보리 산 1-1"}
    BLDG = {"unique_no": "B1", "gubun": "건물", "jibun": "대보리 산 1-1"}
    COLL_A = {"unique_no": "C1", "gubun": "집합건물", "jibun": "대보리 101동 1502호"}
    COLL_B = {"unique_no": "C2", "gubun": "집합건물", "jibun": "대보리 102동 301호"}

    def test_picks_requested_kind_not_first_item(self):
        """핵심 회귀: 첫 건이 토지여도 '건물'을 고르면 건물이 선택돼야 한다."""
        picked, note = select_registry_item([self.LAND, self.BLDG], realty_type="3")
        assert picked["unique_no"] == "B1"
        assert note is None

    def test_picks_matching_dong_ho(self):
        picked, note = select_registry_item(
            [self.COLL_A, self.COLL_B], realty_type="1", dong="102동", ho="301호"
        )
        assert picked["unique_no"] == "C2"
        assert note is None

    def test_no_kind_match_falls_back_but_warns(self):
        """좁히지 못하면 실패시키지 않되 반드시 고지한다(조용한 오답 금지)."""
        picked, note = select_registry_item([self.LAND], realty_type="1")
        assert picked["unique_no"] == "L1"
        assert note and "집합건물" in note

    def test_dong_ho_miss_falls_back_but_warns(self):
        picked, note = select_registry_item(
            [self.COLL_A], realty_type="1", dong="999동", ho="1호"
        )
        assert picked["unique_no"] == "C1"
        assert note and "999동" in note

    def test_substring_must_not_match_other_unit(self):
        """★실결함 재발방지: 프론트는 접미사 없는 숫자를 보낸다("101"·"502").
        "101"이 "제1101동"에 부분일치해 남의 세대를 고르면 안 되고,
        목록 순서가 바뀌어도 결과가 흔들리면 안 된다."""
        wrong = {"unique_no": "W", "gubun": "집합건물", "jibun": "○○동 1-1 제1101동 제1502호"}
        right = {"unique_no": "R", "gubun": "집합건물", "jibun": "○○동 1-1 제101동 제502호"}
        for order in ([wrong, right], [right, wrong]):
            picked, note = select_registry_item(order, realty_type="1", dong="101", ho="502")
            assert picked["unique_no"] == "R", "부분문자열 오매칭으로 다른 세대 선택"
            assert note is None

    def test_ambiguous_unit_match_must_warn(self):
        """동·호가 똑같이 일치하는 물건이 2건이면 '정확히 골랐다'고 침묵하면 안 된다."""
        a = {"unique_no": "A", "gubun": "집합건물", "jibun": "○○동 1-1 제101동 제502호"}
        b = {"unique_no": "B", "gubun": "집합건물", "jibun": "○○동 1-1 제101동 제502호"}
        picked, note = select_registry_item([a, b], realty_type="1", dong="101", ho="502")
        assert picked["unique_no"] == "A"
        assert note and "2건" in note, "모호성이 고지되지 않음"

    def test_unknown_code_warns_that_filter_not_applied(self):
        """모르는 구분코드는 필터가 조용히 무력화되므로 그 사실 자체를 고지해야 한다."""
        picked, note = select_registry_item([self.LAND], realty_type="9")
        assert picked["unique_no"] == "L1"
        assert note and "알 수 없는" in note

    def test_multiple_kind_candidates_must_warn(self):
        """구분만 지정했는데 같은 구분 물건이 여러 건이면 침묵하면 안 된다."""
        a = {"unique_no": "A", "gubun": "건물", "jibun": "○○동 1-1"}
        b = {"unique_no": "B", "gubun": "건물", "jibun": "○○동 1-2"}
        picked, note = select_registry_item([a, b], realty_type="3")
        assert picked["unique_no"] == "A"
        assert note and "2건" in note, "동일 구분 복수 후보가 고지되지 않음"

    def test_unit_suffix_tolerated(self):
        """사용자가 '101동'처럼 접미사를 붙여 입력해도 동일하게 대조돼야 한다."""
        right = {"unique_no": "R", "gubun": "집합건물", "jibun": "○○동 1-1 제101동 제502호"}
        picked, note = select_registry_item([right], realty_type="1", dong="101동", ho="502호")
        assert picked["unique_no"] == "R" and note is None

    def test_empty_list(self):
        picked, note = select_registry_item([], realty_type="2")
        assert picked is None and note is None

    def test_no_filter_keeps_first(self):
        picked, note = select_registry_item([self.LAND, self.BLDG])
        assert picked["unique_no"] == "L1"
        assert note is None
