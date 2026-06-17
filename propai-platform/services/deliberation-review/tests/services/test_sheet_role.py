"""AT-1/AT-2/AT-7 — 시트역할 3원 합의: 오분류 격리, 불합의 격리, 충돌 플래그."""
from app.contracts.sheet_role import SheetRole
from app.services.sheet.sheet_role_resolver import SheetRoleResolver

# 단면도인데 분류기가 입면도로 오라벨(표제란·내용은 단면).
SHEET_SECTION_MISLABELED_ELEVATION = {
    "sheet_id": "A-201",
    "classifier_role": "ELEVATION",
    "titleblock_text": "단면도",
    "content_role": "SECTION",
}

# 세 신호가 전부 다름.
SHEET_CONFLICTING_SIGNALS = {
    "sheet_id": "A-301",
    "classifier_role": "PLAN",
    "titleblock_text": "단면도",
    "content_role": "ELEVATION",
}

# 표제란(단면) vs 분류기(입면) 충돌, 내용 신호 결손.
SHEET_TITLEBLOCK_VS_CLASSIFIER = {
    "sheet_id": "A-401",
    "classifier_role": "ELEVATION",
    "titleblock_text": "단면도",
    "content_role": None,
}


def test_misclassified_sheet_isolated():
    a = SheetRoleResolver().resolve(SHEET_SECTION_MISLABELED_ELEVATION)
    assert a.isolated is True
    assert a.role != SheetRole.ELEVATION  # 잘못된 높이 라우팅 차단


def test_role_disagreement_isolates():
    a = SheetRoleResolver().resolve(SHEET_CONFLICTING_SIGNALS)
    assert a.isolated is True


def test_titleblock_classifier_conflict_flags():
    a = SheetRoleResolver().resolve(SHEET_TITLEBLOCK_VS_CLASSIFIER)
    assert a.isolated is True
    assert "conflict" in a.flags
