"""PNU→행정구역코드 어댑터 + 건축HUB 키 정합 테스트.

검증 대상:
- integrations/region_codes.py: pnu_to_bcode / pnu_to_full_parcel 경계 (19자리 정상·짧음·비숫자)
- config.py: hub_permit_api_key 필드 존재 (클라이언트 AttributeError 갭 차단)
- public_data_registry.py: 건축HUB 주택·건축인허가 2종 등록
"""

from apps.api.integrations.region_codes import pnu_to_bcode, pnu_to_full_parcel

# 서울 강남구 역삼동 대지 본번727 부번0035 형태의 정상 19자리 PNU
VALID_PNU = "1168010100" + "1" + "0727" + "0035"  # 산(1)


# ── pnu_to_bcode ──

class TestPnuToBcode:
    def test_valid_19_digits(self):
        assert pnu_to_bcode(VALID_PNU) == ("11680", "10100")

    def test_valid_10_digits_only(self):
        """법정동코드 10자리만 있어도 추출 가능."""
        assert pnu_to_bcode("1168010100") == ("11680", "10100")

    def test_strips_whitespace(self):
        assert pnu_to_bcode(f"  {VALID_PNU}  ") == ("11680", "10100")

    def test_too_short_returns_none(self):
        assert pnu_to_bcode("11680") is None

    def test_non_numeric_returns_none(self):
        """가짜 코드 생성 금지 — 비숫자는 정직하게 None."""
        assert pnu_to_bcode("ABCDE10100123456789") is None

    def test_empty_and_none_return_none(self):
        assert pnu_to_bcode("") is None
        assert pnu_to_bcode(None) is None


# ── pnu_to_full_parcel ──

class TestPnuToFullParcel:
    def test_valid_san_parcel(self):
        parcel = pnu_to_full_parcel(VALID_PNU)
        assert parcel is not None
        # building_registry_service.get_building_by_pnu 슬라이싱 규약과 동일해야 함
        assert parcel["sigungu_cd"] == VALID_PNU[:5]
        assert parcel["bjdong_cd"] == VALID_PNU[5:10]
        assert parcel["plat_gb_cd"] == "1"
        assert parcel["is_san"] is True
        assert parcel["bun"] == VALID_PNU[11:15] == "0727"
        assert parcel["ji"] == VALID_PNU[15:19] == "0035"

    def test_valid_daeji_parcel(self):
        """대지구분 0 → 산 아님."""
        pnu = "1168010100" + "0" + "0001" + "0000"
        parcel = pnu_to_full_parcel(pnu)
        assert parcel is not None
        assert parcel["plat_gb_cd"] == "0"
        assert parcel["is_san"] is False

    def test_shorter_than_19_returns_none(self):
        """bcode 추출은 가능한 10자리도 full parcel은 None."""
        assert pnu_to_full_parcel("1168010100") is None
        assert pnu_to_full_parcel(VALID_PNU[:18]) is None

    def test_non_numeric_returns_none(self):
        assert pnu_to_full_parcel("11680101001072700AB") is None

    def test_empty_and_none_return_none(self):
        assert pnu_to_full_parcel("") is None
        assert pnu_to_full_parcel(None) is None


# ── config 키 정합 (건축HUB 클라이언트 AttributeError 갭) ──

class TestHubPermitKeyConfig:
    def test_settings_has_hub_permit_api_key_field(self):
        """hub_permit_client.py가 self.settings.hub_permit_api_key를 참조하므로 필드 필수."""
        from apps.api.config import Settings

        assert "hub_permit_api_key" in Settings.model_fields
        assert Settings.model_fields["hub_permit_api_key"].default == ""

    def test_get_settings_attribute_accessible(self):
        """런타임 싱글톤에서도 AttributeError 없이 접근 가능해야 함."""
        from apps.api.config import get_settings

        settings = get_settings()
        # 미설정 시 빈 문자열(falsy) → 클라이언트의 'or molit_api_key' 인라인 폴백이 동작
        assert isinstance(settings.hub_permit_api_key, str)


# ── 공공데이터 레지스트리 등록 ──

class TestPublicDataRegistryHubPermit:
    def test_hub_permit_sources_registered(self):
        from apps.api.app.services.data_validation.public_data_registry import (
            PublicDataRegistry,
        )

        registry = PublicDataRegistry()
        for name in ("hub_permit", "arch_permit"):
            status = registry.get_status(name)
            assert status is not None, f"{name} 미등록"
            assert status.source_type == "api"
            assert status.update_frequency == "daily"
