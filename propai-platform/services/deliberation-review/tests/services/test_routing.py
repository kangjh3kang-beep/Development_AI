"""AT-6 — 필수 시트 결손(일조분석도 없음) → 하류 원장 resolve MISSING(확인 불가 연결)."""
from app.contracts.enums import RecordStatus
from app.services.sheet.routing import route_to_ledger

# 일조분석도(SUNLIGHT) 부재 — 평면/단면만 존재(합의 확정).
SHEETS_WITHOUT_SUNLIGHT = [
    {
        "sheet_id": "A-101",
        "classifier_role": "PLAN",
        "titleblock_text": "평면도",
        "content_role": "PLAN",
        "quantities": [{"variable_id": "building_area", "value": 500, "method": "TABLE", "unit": "m2"}],
    },
    {
        "sheet_id": "A-201",
        "classifier_role": "SECTION",
        "titleblock_text": "단면도",
        "content_role": "SECTION",
        "quantities": [],
    },
]


def test_required_sheet_missing_marks_unavailable():
    led = route_to_ledger(SHEETS_WITHOUT_SUNLIGHT)
    assert led.resolve("sunlight_hours").status == RecordStatus.MISSING


def test_confirmed_sheet_quantity_routed():
    led = route_to_ledger(SHEETS_WITHOUT_SUNLIGHT)
    assert led.resolve("building_area").status == RecordStatus.AGREED
