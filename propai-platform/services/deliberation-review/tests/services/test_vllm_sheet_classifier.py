"""P0 — 실 VLLM 시트분류 어댑터: 동일 계약·graceful degrade·실 클라이언트 경로·팩토리·resolver 통합."""
from app.adapters.vision.sheet_classifier import MockSheetClassifier
from app.adapters.vision.vllm_sheet_classifier import (
    VLLMSheetClassifier,
    build_sheet_classifier,
)
from app.contracts.sheet_role import SheetRole
from app.services.sheet.sheet_role_resolver import SheetRoleResolver


class _FakeVision:
    """주입형 가짜 VLLM — 결정론. (실 호출 없이 추출 경로 검증)"""

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def classify_sheet(self, image_ref: str, hint_text: str | None) -> str | None:
        return self.answer


def test_contract_same_signature():
    # mock과 동일 계약: classify(sheet) -> str|None.
    clf = VLLMSheetClassifier()
    assert clf.classify({"classifier_role": "PLAN"}) == "PLAN"


def test_graceful_degrade_without_client_or_image():
    # 클라이언트/이미지 없으면 입력 신호 그대로(날조 금지) — 키 없이 동작.
    clf = VLLMSheetClassifier()
    assert clf.classify({"classifier_role": "SECTION"}) == "SECTION"
    assert clf.classify({}) is None


def test_real_path_normalizes_korean_output():
    # 이미지+클라이언트 있으면 VLLM 호출 → 한국어 출력도 SheetRole로 정규화.
    clf = VLLMSheetClassifier(vision_client=_FakeVision("단면도"))
    assert clf.classify({"image_ref": "s3://sheet.png", "titleblock_text": "A-201"}) == "SECTION"


def test_real_path_unknown_output_is_none():
    # 미상 출력 → None(임의 단정 금지, INV-9).
    clf = VLLMSheetClassifier(vision_client=_FakeVision("무슨도면인지모름"))
    assert clf.classify({"image_ref": "x"}) is None


def test_factory_defaults_to_mock():
    assert isinstance(build_sheet_classifier(), MockSheetClassifier)


def test_factory_vllm_when_configured(monkeypatch):
    monkeypatch.setenv("SHEET_CLASSIFIER", "vllm")  # env 우선(오버레이 동작)
    clf = build_sheet_classifier(vision_client=_FakeVision("PLAN"))
    assert isinstance(clf, VLLMSheetClassifier)


def test_resolver_uses_vllm_and_keeps_consensus():
    # VLLM을 분류기로 끼워도 3원 합의(INV-8) 보존 — 표제란/내용 불합의 시 격리.
    clf = VLLMSheetClassifier(vision_client=_FakeVision("입면도"))  # ELEVATION
    sheet = {"sheet_id": "A-201", "image_ref": "x", "titleblock_text": "단면도", "content_role": "SECTION"}
    a = SheetRoleResolver(classifier=clf).resolve(sheet)
    assert a.isolated is True  # 분류기(ELEVATION) vs 표제란/내용(SECTION) 불합의 → 격리
    assert a.role != SheetRole.ELEVATION
