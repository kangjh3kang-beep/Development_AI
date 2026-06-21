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
# ── 설계생성·전수조사 보강(부동산개발·건축 관련 법규) 법령명 상수 ──
_CONDO = "집합건물의 소유 및 관리에 관한 법률"
_REG = "부동산등기법"
_FIRE = "소방시설 설치 및 관리에 관한 법률"
_FIRE_PREV = "화재의 예방 및 안전관리에 관한 법률"
_FIRE_EVAC = "건축물의 피난·방화구조 등의 기준에 관한 규칙"
_ENV = "환경영향평가법"
_DISASTER = "자연재해대책법"
_TRAFFIC = "도시교통정비 촉진법"
_APPRAISAL = "감정평가 및 감정평가사에 관한 법률"
_PRICE_DISCLOSURE = "부동산 가격공시에 관한 법률"
_REALTX = "부동산 거래신고 등에 관한 법률"
_FARMLAND = "농지법"
_FOREST = "산지관리법"
_GREENBELT = "개발제한구역의 지정 및 관리에 관한 특별조치법"
_SMALL_REDEV = "빈집 및 소규모주택 정비에 관한 특례법"
_LANDSCAPE = "경관법"
_HERITAGE = "매장유산 보호 및 조사에 관한 법률"
_DEVELOPER = "부동산개발업의 관리 및 육성에 관한 법률"
# ── 2차 전수조사 보강(관리·재정·기부채납·국유재산·시공·토지·구역) ──
_APT_MGMT = "공동주택관리법"
_DEV_LEVY = "개발이익 환수에 관한 법률"
_STATE_PROP = "국유재산법"
_PUBLIC_PROP = "공유재산 및 물품 관리법"
_CULTURAL = "문화유산의 보존 및 활용에 관한 법률"
_PRIVATE_RENTAL = "민간임대주택에 관한 특별법"
_BLDG_SALES = "건축물의 분양에 관한 법률"
_URBAN_REGEN = "도시재생 활성화 및 지원에 관한 특별법"
_URBAN_RENEW = "도시재정비 촉진을 위한 특별법"
_TRANSIT = "역세권의 개발 및 이용에 관한 법률"
_LAND_DEV = "택지개발촉진법"
_INDUSTRIAL = "산업입지 및 개발에 관한 법률"
_CONSTR_IND = "건설산업기본법"
_CONSTR_TECH = "건설기술 진흥법"
_LAND_COMP = "공익사업을 위한 토지 등의 취득 및 보상에 관한 법률"
_CADASTRAL = "공간정보의 구축 및 관리 등에 관한 법률"
_LAND_USE_REG = "토지이용규제 기본법"

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
    # ── 설계생성 전수조사 보강: 집합건물·등기(분양 권리·대지권) ──
    "condo_ownership":            _ref(_CONDO, "제20조", "대지사용권의 일체성(세대별 대지지분)"),
    "condo_reconstruction":       _ref(_CONDO, "제47조", "재건축 결의(구분소유자·의결권 4/5)"),
    "condo_management":           _ref(_CONDO, "제23조", "관리단의 구성(분양 후 운영)"),
    "land_right_registration":    _ref(_REG, None, "대지권 등기(구분건물 일체성)"),
    # ── 소방·방화 ──
    "fire_safety":                _ref(_FIRE, None, "소방시설 설치 및 관리"),
    "fire_prevention":            _ref(_FIRE_PREV, None, "화재의 예방 및 안전관리"),
    "fire_evac_structure":        _ref(_FIRE_EVAC, None, "피난·방화구조 기준(피난계단·방화구획)"),
    # ── 환경·재해·교통 영향평가(인허가 협의) ──
    "env_impact":                 _ref(_ENV, None, "환경영향평가"),
    "disaster_impact":            _ref(_DISASTER, None, "재해영향평가(자연재해대책)"),
    "traffic_impact":             _ref(_TRAFFIC, None, "교통영향평가"),
    # ── 감정평가·공시·거래(자산가치·근거가액) ──
    "appraisal":                  _ref(_APPRAISAL, None, "감정평가(자산·담보·보상)"),
    "official_land_price":        _ref(_PRICE_DISCLOSURE, "제10조", "개별공시지가의 결정·공시"),
    "realtx_report":              _ref(_REALTX, None, "부동산 거래신고·토지거래허가"),
    # ── 농지·산지(개발행위 전용허가) ──
    "farmland_conversion":        _ref(_FARMLAND, "제34조", "농지전용허가"),
    "forest_conversion":          _ref(_FOREST, "제14조", "산지전용허가"),
    # ── 구역·정비·경관·문화유산 ──
    "greenbelt":                  _ref(_GREENBELT, None, "개발제한구역 행위제한"),
    "small_housing_redev":        _ref(_SMALL_REDEV, None, "가로주택·소규모주택 정비(모아주택)"),
    "landscape_review":           _ref(_LANDSCAPE, None, "경관계획·경관심의"),
    "buried_heritage":            _ref(_HERITAGE, None, "매장유산 지표·발굴조사(착공 전)"),
    # ── 디벨로퍼 ──
    "developer_registration":     _ref(_DEVELOPER, None, "부동산개발업 등록"),
    # ── 2차 보강: 관리·재정·기부채납·국유/공유재산 ──
    "apartment_management":       _ref(_APT_MGMT, None, "공동주택 관리(입대의·장기수선·하자보수)"),
    "development_levy":           _ref(_DEV_LEVY, None, "개발부담금(개발이익 환수)"),
    "public_facility_contribution": _ref(_KOOKTO, "제65조", "개발행위에 따른 공공시설의 귀속(기부채납)"),
    "state_property":             _ref(_STATE_PROP, None, "국유재산 사용·대부·매각"),
    "public_property":            _ref(_PUBLIC_PROP, None, "공유재산 관리(기부채납 수령)"),
    # ── 2차 보강: 분양·임대·정비·구역 ──
    "apartment_sales":            _ref(_BLDG_SALES, None, "건축물(비주택) 분양신고"),
    "private_rental":             _ref(_PRIVATE_RENTAL, None, "등록 민간임대주택"),
    "urban_regeneration":         _ref(_URBAN_REGEN, None, "도시재생활성화지역"),
    "urban_renewal_promotion":    _ref(_URBAN_RENEW, None, "재정비촉진지구"),
    "transit_oriented":           _ref(_TRANSIT, None, "역세권개발구역"),
    "land_dev_promotion":         _ref(_LAND_DEV, None, "택지개발지구"),
    "industrial_site":            _ref(_INDUSTRIAL, None, "산업단지 지정·개발"),
    # ── 2차 보강: 시공·토지·지적·문화유산 ──
    "construction_industry":      _ref(_CONSTR_IND, None, "건설업 도급·하도급"),
    "construction_tech":          _ref(_CONSTR_TECH, None, "건설사업관리·품질·안전관리"),
    "land_compensation":          _ref(_LAND_COMP, None, "수용·협의취득·손실보상"),
    "cadastral":                  _ref(_CADASTRAL, None, "지목·지번·경계(지적)·측량"),
    "land_use_regulation":        _ref(_LAND_USE_REG, None, "토지이용계획확인(지역·지구 규제)"),
    "cultural_heritage":          _ref(_CULTURAL, None, "문화유산 보호구역·현상변경 허가"),
    # ── 조례(동적) — sigungu 런타임 치환. url은 조례명 확정 시 build_ordinance_url로 주입 ──
    "ordinance_bcr": {
        "law_name": "{sigungu} 도시계획 조례", "article": "", "title": "건폐율(지자체별)", "url": "",
    },
    "ordinance_far": {
        "law_name": "{sigungu} 도시계획 조례", "article": "", "title": "용적률(지자체별)", "url": "",
    },
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
        law_name = record.get("law_name") or ""
        if "{sigungu}" in law_name and sigungu:
            ordinance_name = law_name.replace("{sigungu}", sigungu)
            record["law_name"] = ordinance_name
            record["url"] = build_ordinance_url(ordinance_name)
        # sigungu 미상이면 조례 플레이스홀더 유지 + url 빈 슬롯 → pending.
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
