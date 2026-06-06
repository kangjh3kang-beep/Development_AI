"""F-2 — 모델하우스 방문객 개인정보 동의 고지문 + 멱등 컬럼 보강 + 동의이력 저장.

개인정보보호법 제15조(수집·이용 동의) / 제22조(동의 받는 방법: 필수·선택 분리)에 따라
방문 등록 시 ① 수집항목 ② 이용목적 ③ 보유기간을 명확히 고지하고, 필수동의(개인정보)와
선택동의(마케팅 활용·제3자 제공)를 분리하여 동의이력(버전·시각·IP)을 저장한다.

- 필수동의(REQUIRED) 미동의 시 등록 차단(수집불가 안내).
- 마케팅(MARKETING)/제3자(THIRD_PARTY) 미동의여도 방문등록은 허용(후속 발송만 차단).
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 동의서 버전(고지문 변경 시 증가 → 어떤 고지문에 동의했는지 추적).
CONSENT_VERSION = "2026-06-v1"

# 표준 고지 템플릿(수집항목·이용목적·보유기간). 프론트 동의팝업이 그대로 렌더한다.
CONSENT_TEMPLATE: dict = {
    "version": CONSENT_VERSION,
    "consents": [
        {
            "type": "REQUIRED",
            "required": True,
            "title": "[필수] 방문·상담 관리 목적 개인정보 수집·이용",
            "items": ["성명", "연락처(휴대전화)", "방문목적", "방문인원", "방문일시"],
            "purpose": "모델하우스 방문 응대·상담 배정 및 분양 상담 진행, 재방문 관리",
            "retention": "상담종료(또는 청약 미진행 확정) 후 1년 보관 후 파기",
            "deny_notice": "필수 항목에 동의하지 않으시면 방문 등록 및 상담 배정이 불가합니다.",
        },
        {
            "type": "MARKETING",
            "required": False,
            "title": "[선택] 분양 정보 마케팅 활용",
            "items": ["성명", "연락처(휴대전화)"],
            "purpose": "신규 분양·이벤트·할인 정보 등 마케팅 정보의 문자·전화 발송",
            "retention": "동의 철회 시 또는 수집일로부터 2년 중 먼저 도래하는 시점까지",
            "deny_notice": "미동의 시에도 방문 등록은 가능하며, 마케팅 정보만 발송되지 않습니다.",
        },
        {
            "type": "THIRD_PARTY",
            "required": False,
            "title": "[선택] 시행사/분양대행사 제3자 제공",
            "items": ["성명", "연락처(휴대전화)", "방문목적"],
            "purpose": "분양 계약 진행을 위한 시행사·분양대행사의 상담 연락",
            "retention": "제공 목적 달성 후 또는 동의 철회 시까지",
            "deny_notice": "미동의 시에도 방문 등록은 가능합니다.",
        },
    ],
}

# 고지문에서 type→메타(purpose/retention/items) 역인덱스(저장 시 보강용).
_TEMPLATE_BY_TYPE = {c["type"]: c for c in CONSENT_TEMPLATE["consents"]}

# 필수동의 type 집합(미동의 시 등록 차단).
REQUIRED_TYPES = {c["type"] for c in CONSENT_TEMPLATE["consents"] if c.get("required")}

# mh_visit_consents 멱등 컬럼 보강(F-2 고지이력). 기존 테이블 무파괴.
_CONSENT_COLS_DDL = [
    "ALTER TABLE mh_visit_consents ADD COLUMN IF NOT EXISTS site_id uuid",
    "ALTER TABLE mh_visit_consents ADD COLUMN IF NOT EXISTS purpose text",
    "ALTER TABLE mh_visit_consents ADD COLUMN IF NOT EXISTS retention varchar(120)",
    "ALTER TABLE mh_visit_consents ADD COLUMN IF NOT EXISTS version varchar(20)",
    "ALTER TABLE mh_visit_consents ADD COLUMN IF NOT EXISTS consent_ip varchar(64)",
]


async def ensure_consent_columns(db: AsyncSession) -> None:
    """F-2 동의 고지이력 컬럼을 멱등 보강(배포 후 최초 1회). 기존 데이터 무파괴."""
    for ddl in _CONSENT_COLS_DDL:
        await db.execute(text(ddl))


def template() -> dict:
    """현행 동의 고지문(수집항목·이용목적·보유기간) 반환."""
    return CONSENT_TEMPLATE


def has_required_consent(consents: list[dict]) -> bool:
    """필수동의(REQUIRED)가 모두 agreed=True 인지 검사. 필수 type 누락 시 False."""
    agreed_types = {c.get("type") for c in consents if c.get("agreed")}
    return REQUIRED_TYPES.issubset(agreed_types)


def enrich_consent(c: dict) -> dict:
    """저장용 동의 레코드 보강: 고지문의 이용목적·보유기간·수집항목·버전을 결합."""
    meta = _TEMPLATE_BY_TYPE.get(c.get("type"), {})
    return {
        "type": c.get("type"),
        "agreed": bool(c.get("agreed")),
        "items": c.get("items") or meta.get("items"),
        "purpose": c.get("purpose") or meta.get("purpose"),
        "retention": c.get("retention") or meta.get("retention"),
        "version": c.get("version") or CONSENT_VERSION,
        "esign_uri": c.get("esign_uri"),
        "agreed_at": c.get("agreed_at"),
    }
