"""법령 근거 레지스트리 테스트 — legal_reference_registry.

검증 범위:
- 각 키의 URL이 ②-1 검증 형식(law.go.kr 한글주소, /법령/{명}/제{N}조)을 따르는가.
- 미존재 키는 None, 별칭(②-3 내부키) 해석.
- percent-encoding(UTF-8) 라운드트립(인코딩 ↔ 원문 한글 동치).
- 조례(자치법규) URL 형식 + sigungu 치환.
계산 로직이 없는 데이터 매핑 모듈이므로 데이터 무결성 위주로 검증한다.
"""
from urllib.parse import quote, unquote

import pytest

from app.services.legal.legal_reference_registry import (
    LAW_GO_KR_BASE,
    LEGAL_REFERENCES,
    build_law_url,
    build_ordinance_url,
    get_legal_ref,
    get_legal_refs,
    inject_urls,
)

# 작업 지시서가 요구한 핵심 공개 키(도메인 명명).
REQUIRED_KEYS = [
    "far_limit",
    "bcr_limit",
    "daylight_height",
    "parking_min",
    "acquisition_tax",
    "district_unit_plan",
]

# 블루프린트 ②-3 내부 키(별칭으로 해석되어야 함).
BLUEPRINT_ALIASES = [
    "bldg_height",
    "parking",
    "acq_tax",
    "district_unit",
    "bldg_open",
    "bldg_height_dec",
    "parking_dec",
]

# WP-R 도메인 확장 신규 키(5도메인: 세금·인허가·설계·ESG·정비).
WP_R_NEW_KEYS = [
    # 세금
    "capital_gains_tax",
    "comprehensive_property_tax",
    "reconstruction_levy",
    "local_education_tax",
    "stamp_tax",
    # 인허가
    "building_permit",
    "use_permission",
    # 설계
    "evacuation",
    "structure_safety",
    # ESG
    "green_building",
    "energy_efficiency",
    "zeb_certification",
    # 정비
    "urban_redevelopment",
]


class TestRequiredKeysPresent:
    def test_required_keys_exist(self):
        for key in REQUIRED_KEYS:
            assert get_legal_ref(key) is not None, f"필수 키 누락: {key}"

    def test_record_shape(self):
        """각 레코드는 law_name/article/title/url 4키를 보유."""
        for key in LEGAL_REFERENCES:
            ref = get_legal_ref(key)
            assert set(ref.keys()) == {"law_name", "article", "title", "url"}
            assert isinstance(ref["law_name"], str) and ref["law_name"]
            assert isinstance(ref["title"], str) and ref["title"]


class TestUrlFormat:
    def test_law_urls_use_korean_address_scheme(self):
        """조례를 제외한 모든 법령 키 URL은 /법령/ 한글주소(인코딩) 형식."""
        prefix = f"{LAW_GO_KR_BASE}/{quote('법령')}/"
        for key, ref in LEGAL_REFERENCES.items():
            if key.startswith("ordinance_"):
                continue  # 조례는 동적(빈 url) — 별도 검증
            url = ref["url"]
            assert url.startswith(prefix), f"{key} URL이 /법령/ 형식 아님: {url}"

    def test_article_segment_is_korean_ordinal(self):
        """조문이 지정된 키는 URL 마지막 세그먼트가 '제N조'(인코딩)로 끝난다."""
        for key, ref in LEGAL_REFERENCES.items():
            if key.startswith("ordinance_"):
                continue
            article = ref["article"]
            if not article:
                continue  # 루트 폴백(예: urban_complex)
            last_segment = unquote(ref["url"].rsplit("/", 1)[-1])
            assert last_segment == article
            assert last_segment.startswith("제") and last_segment.endswith("조")

    def test_no_arabic_only_or_english_article(self):
        """②-1 금지 형식: '/55', '/article55' 등 불가."""
        for key, ref in LEGAL_REFERENCES.items():
            url = ref["url"]
            if not url:
                continue
            tail = url.rsplit("/", 1)[-1]
            assert tail.lower() != tail or not tail.isdigit(), f"{key}: 숫자 단독 조문 {url}"
            assert "article" not in unquote(tail)

    def test_specific_verified_urls(self):
        """블루프린트 ②-3 실접속 검증 항목 핵심 매핑 대조(디코드 동치)."""
        cases = {
            "far_limit": ("국토의 계획 및 이용에 관한 법률 시행령", "제85조"),
            "bcr_limit": ("국토의 계획 및 이용에 관한 법률 시행령", "제84조"),
            "bldg_bcr": ("건축법", "제55조"),
            "bldg_far": ("건축법", "제56조"),
            "daylight_height": ("건축법", "제61조"),
            "parking_min": ("주차장법", "제19조"),
            "acquisition_tax": ("지방세법", "제11조"),
            "district_unit_plan": ("국토의 계획 및 이용에 관한 법률", "제52조"),
        }
        for key, (law, article) in cases.items():
            ref = get_legal_ref(key)
            assert ref["law_name"] == law
            assert ref["article"] == article
            decoded = unquote(ref["url"])
            name_nospace = law.replace(" ", "")
            assert decoded == f"{LAW_GO_KR_BASE}/법령/{name_nospace}/{article}"


class TestBuildLawUrl:
    def test_with_article_string(self):
        url = build_law_url("건축법", "제55조")
        assert unquote(url) == f"{LAW_GO_KR_BASE}/법령/건축법/제55조"

    def test_with_numeric_article(self):
        """숫자 단독 입력은 '제{N}조'로 보정."""
        assert build_law_url("건축법", 55) == build_law_url("건축법", "제55조")
        assert build_law_url("건축법", "55") == build_law_url("건축법", "제55조")

    def test_without_article_falls_back_to_root(self):
        url = build_law_url("건축법")
        assert unquote(url) == f"{LAW_GO_KR_BASE}/법령/건축법"
        assert "/제" not in unquote(url)

    def test_spaces_and_middle_dot_removed(self):
        """공백·가운뎃점 제거 — ②-2 규칙."""
        url = build_law_url("도시 및 주거환경정비법", "제74조")
        assert unquote(url) == f"{LAW_GO_KR_BASE}/법령/도시및주거환경정비법/제74조"
        url2 = build_law_url("부설·주차장법")
        assert unquote(url2) == f"{LAW_GO_KR_BASE}/법령/부설주차장법"

    def test_branch_article_preserved(self):
        """가지번호 '제29조의2' 형식은 보존."""
        url = build_law_url("건축법", "제29조의2")
        assert unquote(url).endswith("제29조의2")

    def test_no_plus_for_spaces(self):
        """공백은 '+' 가 아닌 제거/percent-encoding(②-2: '+' 지양)."""
        url = build_law_url("국토의 계획 및 이용에 관한 법률", "제78조")
        assert "+" not in url

    def test_empty_law_name(self):
        assert build_law_url("") == LAW_GO_KR_BASE
        assert build_law_url(None) == LAW_GO_KR_BASE


class TestBuildOrdinanceUrl:
    def test_ordinance_url_scheme(self):
        url = build_ordinance_url("서울특별시 강남구 도시계획 조례")
        assert unquote(url) == f"{LAW_GO_KR_BASE}/자치법규/서울특별시강남구도시계획조례"

    def test_ordinance_uses_jachi_keyword(self):
        url = build_ordinance_url("서울특별시도시계획조례")
        assert f"/{quote('자치법규')}/" in url

    def test_empty_ordinance_returns_empty(self):
        assert build_ordinance_url("") == ""
        assert build_ordinance_url(None) == ""


class TestGetLegalRef:
    def test_nonexistent_key_returns_none(self):
        assert get_legal_ref("does_not_exist") is None
        assert get_legal_ref("") is None
        assert get_legal_ref(None) is None

    def test_returns_copy_not_reference(self):
        """반환 dict 변형이 레지스트리 원본을 오염시키지 않음."""
        ref = get_legal_ref("far_limit")
        ref["title"] = "오염시도"
        assert LEGAL_REFERENCES["far_limit"]["title"] != "오염시도"

    def test_aliases_resolve(self):
        """②-3 내부키 별칭이 도메인 키와 동일 레코드로 해석."""
        assert get_legal_ref("bldg_height") == get_legal_ref("daylight_height")
        assert get_legal_ref("parking") == get_legal_ref("parking_min")
        assert get_legal_ref("acq_tax") == get_legal_ref("acquisition_tax")
        assert get_legal_ref("district_unit") == get_legal_ref("district_unit_plan")

    @pytest.mark.parametrize("alias", BLUEPRINT_ALIASES)
    def test_all_blueprint_aliases_resolve(self, alias):
        assert get_legal_ref(alias) is not None


class TestEncodingRoundTrip:
    def test_percent_encoding_roundtrip_all_keys(self):
        """모든 키 URL은 UTF-8 percent-encoding ↔ 원문 한글 라운드트립."""
        for key, ref in LEGAL_REFERENCES.items():
            url = ref["url"]
            if not url:
                continue
            decoded = unquote(url)
            assert quote(decoded, safe=":/") == quote(unquote(url), safe=":/")
            # 디코드 결과에 mojibake/물음표 없이 한글 또는 ASCII만.
            assert "%" not in decoded
            assert decoded.startswith("https://www.law.go.kr/")

    def test_korean_chars_decoded_match_source(self):
        """건축법 제55조: 인코딩값을 디코드하면 원문 한글과 동일."""
        url = build_law_url("건축법", "제55조")
        assert "%EA%B1%B4%EC%B6%95%EB%B2%95" in url  # '건축법'
        assert unquote(url) == f"{LAW_GO_KR_BASE}/법령/건축법/제55조"


class TestGetLegalRefsList:
    def test_skips_unknown_keys(self):
        refs = get_legal_refs(["far_limit", "nope", "bcr_limit"])
        keys = [r["key"] for r in refs]
        assert keys == ["far_limit", "bcr_limit"]

    def test_url_status_verified_for_static(self):
        refs = get_legal_refs(["far_limit"])
        assert refs[0]["url_status"] == "verified"
        assert refs[0]["url"]

    def test_ordinance_pending_without_sigungu(self):
        refs = get_legal_refs(["ordinance_far"])
        assert refs[0]["url_status"] == "pending"
        assert refs[0]["url"] == ""
        assert "{sigungu}" in refs[0]["law_name"]

    def test_ordinance_substituted_with_sigungu(self):
        refs = get_legal_refs(["ordinance_far"], sigungu="서울특별시 강남구")
        rec = refs[0]
        assert "{sigungu}" not in rec["law_name"]
        assert "강남구" in rec["law_name"]
        assert rec["url_status"] == "verified"
        assert f"/{quote('자치법규')}/" in rec["url"]

    def test_empty_input(self):
        assert get_legal_refs([]) == []
        assert get_legal_refs(None) == []

    def test_alias_key_normalized_in_output(self):
        """별칭 입력 시 출력 key는 정식 키로 정규화."""
        refs = get_legal_refs(["bldg_height"])
        assert refs[0]["key"] == "daylight_height"


class TestWpRDomainExpansion:
    """WP-R: 5도메인(세금·인허가·설계·ESG·정비) 확장 키 — 존재·URL 형식·루트 폴백 검증."""

    @pytest.mark.parametrize("key", WP_R_NEW_KEYS)
    def test_new_keys_exist(self, key):
        assert get_legal_ref(key) is not None, f"WP-R 신규 키 누락: {key}"

    def test_preexisting_keys_confirmed(self):
        """기존재 확인 대상: acquisition_tax·daylight_height·housing_approval(주택법 제15조)."""
        acq = get_legal_ref("acquisition_tax")
        assert acq["law_name"] == "지방세법" and acq["article"] == "제11조"
        day = get_legal_ref("daylight_height")
        assert day["law_name"] == "건축법" and day["article"] == "제61조"
        hsg = get_legal_ref("housing_approval")
        assert hsg["law_name"] == "주택법" and hsg["article"] == "제15조"

    def test_housing_project_approval_alias(self):
        """housing_project_approval은 기존 housing_approval 레코드의 별칭(중복 데이터 0)."""
        assert get_legal_ref("housing_project_approval") == get_legal_ref("housing_approval")
        refs = get_legal_refs(["housing_project_approval"])
        assert refs[0]["key"] == "housing_approval"
        assert refs[0]["url_status"] == "verified"

    def test_article_verified_mappings(self):
        """조문이 확정된 신규 키 — 법령명·조문·딥링크(디코드 동치) 대조."""
        cases = {
            "capital_gains_tax": ("소득세법", "제104조"),
            "stamp_tax": ("인지세법", "제3조"),
            "building_permit": ("건축법", "제11조"),
            "use_permission": ("건축법", "제22조"),
            "evacuation": ("건축법", "제49조"),
            "structure_safety": ("건축법", "제48조"),
        }
        for key, (law, article) in cases.items():
            ref = get_legal_ref(key)
            assert ref["law_name"] == law, key
            assert ref["article"] == article, key
            decoded = unquote(ref["url"])
            name_nospace = law.replace(" ", "")
            assert decoded == f"{LAW_GO_KR_BASE}/법령/{name_nospace}/{article}", key

    @pytest.mark.parametrize(
        "key,law",
        [
            ("comprehensive_property_tax", "종합부동산세법"),
            ("reconstruction_levy", "재건축초과이익 환수에 관한 법률"),
            ("local_education_tax", "지방세법"),
            ("green_building", "녹색건축물 조성 지원법"),
            ("energy_efficiency", "녹색건축물 조성 지원법"),
            ("zeb_certification", "녹색건축물 조성 지원법"),
            ("urban_redevelopment", "도시 및 주거환경정비법"),
        ],
    )
    def test_root_fallback_for_unverified_articles(self, key, law):
        """조문 미검증 신규 키는 법령 루트 폴백 — 조문 세그먼트 없음(할루시네이션 링크 금지)."""
        ref = get_legal_ref(key)
        assert ref["law_name"] == law
        assert ref["article"] == ""
        decoded = unquote(ref["url"])
        name_nospace = law.replace(" ", "")
        assert decoded == f"{LAW_GO_KR_BASE}/법령/{name_nospace}"

    def test_new_keys_url_status_verified_via_get_legal_refs(self):
        """신규 키 전부 url 보유(루트 포함) → url_status 'verified', law.go.kr 한글주소 형식."""
        refs = get_legal_refs(WP_R_NEW_KEYS)
        assert len(refs) == len(WP_R_NEW_KEYS)
        prefix = f"{LAW_GO_KR_BASE}/{quote('법령')}/"
        for rec in refs:
            assert rec["url_status"] == "verified", rec["key"]
            assert rec["url"].startswith(prefix), rec["key"]

    def test_existing_required_keys_unchanged(self):
        """가산 후에도 기존 필수 키·별칭 해석 불변(하위호환)."""
        for key in REQUIRED_KEYS + BLUEPRINT_ALIASES:
            assert get_legal_ref(key) is not None, key


class TestInjectUrls:
    def test_inject_updates_existing_key(self):
        original = LEGAL_REFERENCES["ordinance_bcr"]["url"]
        try:
            inject_urls({"ordinance_bcr": "https://www.law.go.kr/자치법규/테스트조례"})
            assert LEGAL_REFERENCES["ordinance_bcr"]["url"].endswith("테스트조례")
        finally:
            LEGAL_REFERENCES["ordinance_bcr"]["url"] = original

    def test_inject_ignores_unknown_key(self):
        inject_urls({"unknown_key_xyz": "https://x"})
        assert "unknown_key_xyz" not in LEGAL_REFERENCES

    def test_inject_via_alias(self):
        original = LEGAL_REFERENCES["parking_min"]["url"]
        try:
            inject_urls({"parking": "https://www.law.go.kr/법령/주차장법/제19조-NEW"})
            assert LEGAL_REFERENCES["parking_min"]["url"].endswith("제19조-NEW")
        finally:
            LEGAL_REFERENCES["parking_min"]["url"] = original
