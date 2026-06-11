"""
법령 근거 레지스트리 — 부동산개발 사업성·규제·인허가·설계·세금·ESG 분석에서
참조하는 모든 법적 근거를 {근거키 → {law_name, article, title, url}}로 매핑한다.

설계 원칙(절대 준수):
- **계산 로직 0.** 순수 데이터 매핑 + URL 조립 함수만. import 부작용 없음.
- 마스터 출처: PRECHECK_UPGRADE_BLUEPRINT ②-3 "법률별 공식명 + 핵심 조문 + 딥링크 매핑표".
- law.go.kr 딥링크는 ②에서 실접속/형식 검증된 **한글주소 형식만** 사용한다.
    · 법령 본문/조문 : https://www.law.go.kr/법령/{법령명}/제{N}조
    · 자치법규(조례)  : https://www.law.go.kr/자치법규/{조례명}
  조(條) 단위까지만 신뢰(항·호 딥링크 미지원). 미검증 조문은 법령 루트로 폴백.
  레지스트리에 없는 근거는 링크 없이 텍스트만(할루시네이션 링크 절대 금지).

공개 API:
- get_legal_ref(key)                  -> dict | None
- build_law_url(law_name, article)    -> str
- build_ordinance_url(ordinance_name) -> str
- get_legal_refs(keys, sigungu=None)  -> list[dict]   (블루프린트 WP-1 호환)
"""
from urllib.parse import quote

# law.go.kr 대표 URL (법령정보식별주소 = 한글주소). 개정 시 자동으로 현행본을 가리킨다.
LAW_GO_KR_BASE = "https://www.law.go.kr"

# 분류 키워드 — ②-1 규칙: '법령' 또는 '자치법규'를 그대로 한글로.
_CATEGORY_LAW = "법령"
_CATEGORY_ORDINANCE = "자치법규"


def _normalize_name(name: str) -> str:
    """법령명/조례명 정규화 — ②-2: 공백·가운뎃점 제거해도 정상 resolve.

    안정성을 위해 percent-encoding(UTF-8) 형태로 반환한다(`+` 지양, HTML href/JSON 안전).
    가운뎃점(·, U+00B7 / U+30FB)과 공백은 제거한다.
    """
    cleaned = (name or "").strip()
    for ch in (" ", "·", "・"):  # 공백, 가운뎃점(라틴/일본어 형태)
        cleaned = cleaned.replace(ch, "")
    return cleaned


def _format_article(article) -> str | None:
    """조문 표기 정규화 — ②-1: 반드시 국문 서수 + '조'(제55조). 가지번호 '의2' 허용.

    허용 입력: '제55조', '55', 55, '제29조의2'. 빈 값/None → None(법령 루트 폴백).
    아라비아 숫자 단독/영문 형태는 '제{N}조'로 보정한다.
    """
    if article is None:
        return None
    text = str(article).strip()
    if not text:
        return None
    # 이미 '제…조' 형식이면 그대로 사용(가지번호 '제29조의2' 포함).
    if text.startswith("제") and ("조" in text):
        return text
    # 순수 숫자(또는 'N조' 형태)면 '제{N}조'로 보정.
    digits = "".join(c for c in text if c.isdigit())
    if digits:
        return f"제{digits}조"
    return None


def build_law_url(law_name: str, article=None) -> str:
    """법령 딥링크(한글주소) 생성 — ②-1 검증 형식만.

    - 조문 지정 시 : {base}/법령/{법령명}/제{N}조
    - 조문 미지정/미검증 시 : {base}/법령/{법령명}  (법령 루트 폴백)
    공백·가운뎃점은 제거하고 percent-encoding(UTF-8)으로 안전하게 인코딩한다.
    """
    name = _normalize_name(law_name)
    if not name:
        return LAW_GO_KR_BASE
    encoded_name = quote(name)
    base = f"{LAW_GO_KR_BASE}/{quote(_CATEGORY_LAW)}/{encoded_name}"
    art = _format_article(article)
    if art:
        return f"{base}/{quote(art)}"
    return base


def build_ordinance_url(ordinance_name: str) -> str:
    """자치법규(조례) 딥링크(한글주소) 생성 — ②-1: {base}/자치법규/{조례명}.

    조례는 지자체명 완전 포함 권장(동명 조례 충돌 방지). 조례명이 비면 빈 문자열 반환
    (호출부에서 url_status:"pending" 처리). 조문 단위는 미지원 — 루트까지만.
    """
    name = _normalize_name(ordinance_name)
    if not name:
        return ""
    return f"{LAW_GO_KR_BASE}/{quote(_CATEGORY_ORDINANCE)}/{quote(name)}"


# ─────────────────────────────────────────────────────────────────────────────
# 근거 키 → {law_name, article, title, url}
# 마스터: 블루프린트 ②-3 검증표. URL은 build_law_url로 일관 생성(검증된 형식만).
# 키 명명 규칙: 도메인 의미 기반(far_limit/bcr_limit/daylight_height/parking_min/
#   acquisition_tax/district_unit_plan …). 블루프린트 ②-3 내부키는 _ALIASES로 흡수.
# ─────────────────────────────────────────────────────────────────────────────
def _ref(law_name: str, article, title: str) -> dict:
    """레코드 1건 구성 — url은 검증 형식으로 자동 생성(계산 로직 아님, 문자열 조립)."""
    return {
        "law_name": law_name,
        "article": _format_article(article) or "",
        "title": title,
        "url": build_law_url(law_name, article),
    }


_KOOKTO = "국토의 계획 및 이용에 관한 법률"
_KOOKTO_DEC = "국토의 계획 및 이용에 관한 법률 시행령"
_BLDG = "건축법"
_BLDG_DEC = "건축법 시행령"
_PARKING = "주차장법"
_PARKING_DEC = "주차장법 시행령"
_GREEN = "녹색건축물 조성 지원법"

LEGAL_REFERENCES: dict[str, dict[str, str]] = {
    # ── 국토의 계획 및 이용에 관한 법률 ──
    "zone_use":           _ref(_KOOKTO, "제76조", "용도지역에서의 건축물 제한"),
    "bcr_law":            _ref(_KOOKTO, "제77조", "용도지역의 건폐율"),
    "far_law":            _ref(_KOOKTO, "제78조", "용도지역의 용적률"),
    "district_unit_plan": _ref(_KOOKTO, "제52조", "지구단위계획의 내용"),
    # ── 국토계획법 시행령 (실효 한도: 별표 위임) ──
    "bcr_limit":          _ref(_KOOKTO_DEC, "제84조", "용도지역 안에서의 건폐율"),
    "far_limit":          _ref(_KOOKTO_DEC, "제85조", "용도지역 안에서의 용적률"),
    # ── 건축법 ──
    "bldg_bcr":           _ref(_BLDG, "제55조", "건축물의 건폐율"),
    "bldg_far":           _ref(_BLDG, "제56조", "건축물의 용적률"),
    "daylight_height":    _ref(_BLDG, "제61조", "일조 등의 확보를 위한 건축물의 높이 제한"),
    "site_open_space":    _ref(_BLDG, "제58조", "대지 안의 공지"),
    # ── 건축법 시행령 (일조 위임기준) ──
    "daylight_height_dec": _ref(_BLDG_DEC, "제86조", "일조 등의 확보를 위한 건축물의 높이 제한"),
    # ── 주택법 ──
    "housing_approval":   _ref("주택법", "제15조", "사업계획의 승인"),
    "housing_price_cap":  _ref("주택법", "제57조", "주택의 분양가격 제한 등(분양가상한제)"),
    # ── 도시개발법 ──
    "urban_dev_replot":   _ref("도시개발법", "제28조", "환지 계획의 작성"),
    # ── 도시 및 주거환경정비법 ──
    "redev_mgmt":         _ref("도시 및 주거환경정비법", "제74조", "관리처분계획의 인가 등"),
    "redev_impl":         _ref("도시 및 주거환경정비법", "제50조", "사업시행계획인가"),
    # ── 도심 복합개발 지원에 관한 법률 (2024.8.7 시행 신법, 루트 폴백) ──
    "urban_complex":      _ref("도심 복합개발 지원에 관한 법률", None, "도심 복합개발(현행본 재확인)"),
    # ── 공공주택 특별법 ──
    "public_housing":     _ref("공공주택 특별법", "제6조", "공공주택지구의 지정 등"),
    # ── 주차장법 ──
    "parking_min":        _ref(_PARKING, "제19조", "부설주차장의 설치·지정"),
    "parking_min_dec":    _ref(_PARKING_DEC, "제6조", "부설주차장의 설치기준(별표1 위임)"),
    # ── 지방세법 ──
    "acquisition_tax":    _ref("지방세법", "제11조", "부동산 취득의 세율"),
    # ── WP-R 확장: 세금 ──
    "capital_gains_tax":          _ref("소득세법", "제104조", "양도소득세의 세율"),
    "comprehensive_property_tax": _ref("종합부동산세법", None, "종합부동산세(주택·토지분, 현행본)"),
    "reconstruction_levy":        _ref("재건축초과이익 환수에 관한 법률", None, "재건축부담금(재건축초과이익 환수)"),
    "local_education_tax":        _ref("지방세법", None, "지방교육세(지방세법 내 목적세, 현행본)"),
    "stamp_tax":                  _ref("인지세법", "제3조", "과세문서 및 세액"),
    # ── WP-R 확장: 인허가 (housing_project_approval은 _ALIASES → housing_approval) ──
    "building_permit":            _ref(_BLDG, "제11조", "건축허가"),
    "use_permission":             _ref(_BLDG, "제22조", "건축물의 사용승인"),
    # ── WP-R 확장: 설계 ──
    "evacuation":                 _ref(_BLDG, "제49조", "건축물의 피난시설 및 용도제한 등"),
    "structure_safety":           _ref(_BLDG, "제48조", "구조내력 등(구조안전 확인)"),
    # ── WP-R 확장: ESG — 조문 딥링크 미검증 → 법령 루트 폴백(잘못된 조문 추정 금지) ──
    "green_building":             _ref(_GREEN, None, "녹색건축 인증"),
    "energy_efficiency":          _ref(_GREEN, None, "건축물 에너지효율등급 인증"),
    "zeb_certification":          _ref(_GREEN, None, "제로에너지건축물(ZEB) 인증"),
    # ── WP-R 확장: 정비 (법령 루트) ──
    "urban_redevelopment":        _ref("도시 및 주거환경정비법", None, "도시·주거환경정비사업(현행본)"),
    # ── 조례(동적) — sigungu 런타임 치환. url은 조례명 확정 시 build_ordinance_url로 주입 ──
    "ordinance_bcr":      {"law_name": "{sigungu} 도시계획 조례", "article": "", "title": "건폐율(지자체별)", "url": ""},
    "ordinance_far":      {"law_name": "{sigungu} 도시계획 조례", "article": "", "title": "용적률(지자체별)", "url": ""},
}

# 블루프린트 ②-3 내부 키 ↔ 본 레지스트리 도메인 키 별칭(하위호환·중복 데이터 0).
# get_legal_ref / get_legal_refs는 별칭도 동일하게 해석한다.
_ALIASES: dict[str, str] = {
    "district_unit": "district_unit_plan",   # ②-3 키
    "bldg_height": "daylight_height",          # ②-3 키
    "bldg_height_dec": "daylight_height_dec",  # ②-3 키
    "bldg_open": "site_open_space",            # ②-3 키
    "parking": "parking_min",                  # ②-3 키
    "parking_dec": "parking_min_dec",          # ②-3 키
    "acq_tax": "acquisition_tax",              # ②-3 키
    # WP-R 도메인 확장 별칭 — 기존 레코드 재사용(중복 데이터 0).
    "housing_project_approval": "housing_approval",  # 주택법 제15조 사업계획승인
}


def _resolve_key(key: str) -> str | None:
    """별칭 → 정식 키. 미존재 시 None."""
    if not key:
        return None
    if key in LEGAL_REFERENCES:
        return key
    return _ALIASES.get(key)


def get_legal_ref(key: str) -> dict | None:
    """근거 키 1건 조회 — {law_name, article, title, url}의 복사본. 미존재 시 None.

    별칭(②-3 내부 키)도 해석한다. 반환은 호출부 변형 격리를 위해 얕은 복사본.
    """
    resolved = _resolve_key(key)
    if resolved is None:
        return None
    return dict(LEGAL_REFERENCES[resolved])


def get_legal_refs(keys, *, sigungu: str | None = None) -> list[dict]:
    """근거 키 목록 → 레코드 목록(블루프린트 WP-1 호환).

    - key·url_status 부착. url_status = 'verified' if url else 'pending'.
    - 조례 키({sigungu} 플레이스홀더)는 sigungu로 치환하고, 치환 시 조례명으로
      build_ordinance_url을 생성해 url_status를 'verified'로 승격한다.
    - 미존재 키는 건너뛴다(할루시네이션 링크 방지).
    """
    out: list[dict] = []
    for key in keys or []:
        ref = get_legal_ref(key)
        if ref is None:
            continue
        record = {"key": _resolve_key(key), **ref}
        law_name = record.get("law_name", "")
        if "{sigungu}" in law_name:
            if sigungu:
                ordinance_name = law_name.replace("{sigungu}", sigungu)
                record["law_name"] = ordinance_name
                record["url"] = build_ordinance_url(ordinance_name)
            # sigungu 미상이면 플레이스홀더 유지 + url 빈 슬롯 → pending.
        record["url_status"] = "verified" if record.get("url") else "pending"
        out.append(record)
    return out


def inject_urls(url_map: dict) -> None:
    """조례 등 동적 URL 런타임 주입(블루프린트 WP-1 호환).

    url_map[key] = url. 레지스트리에 존재하는 키만 갱신(데이터 매핑만, 계산 없음).
    """
    for key, url in (url_map or {}).items():
        resolved = _resolve_key(key)
        if resolved is not None and url:
            LEGAL_REFERENCES[resolved]["url"] = url
