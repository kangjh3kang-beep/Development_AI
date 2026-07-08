"""ContractGeneratorService 단위 테스트 (W3-1).

라우터(routers/contracts.py)에 실배선된 계약서 초안 생성 서비스의
순수 로직 경로(정규화·포맷·조항 생성·마크다운 렌더)와
DB 의존 경로(초안 생성·조회·전자서명 요청)를 FakeSession으로 검증한다.
"""

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.contract_generator import (
    _LANGUAGE_COPY,
    ContractGeneratorService,
)

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
EFFECTIVE = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)


# ── FakeSession ──────────────────────────────


class FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    """execute 응답 큐 기반 AsyncSession 대역."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.commits = 0
        self.flushes = 0

    async def execute(self, stmt):
        if self.results:
            return self.results.pop(0)
        return FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushes += 1
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def refresh(self, obj):
        return None


def _fake_project(name="강남 오피스"):
    return SimpleNamespace(id=PROJECT_ID, tenant_id=TENANT_ID, name=name)


# ── 순수 로직: 정규화 ──────────────────────────────


class TestNormalization:
    def test_언어_정규화_지원언어는_그대로_미지원은_ko_폴백(self):
        assert ContractGeneratorService._normalize_language("en") == "en"
        assert ContractGeneratorService._normalize_language("zh-CN") == "zh-CN"
        assert ContractGeneratorService._normalize_language("ja") == "ko"
        assert ContractGeneratorService._normalize_language("") == "ko"

    def test_계약유형_정규화_공백대문자_허용_미지원은_construction_폴백(self):
        assert ContractGeneratorService._normalize_contract_type("  SALE  ") == "sale"
        assert ContractGeneratorService._normalize_contract_type("lease") == "lease"
        assert ContractGeneratorService._normalize_contract_type("franchise") == "construction"
        assert ContractGeneratorService._normalize_contract_type("") == "construction"


# ── 순수 로직: 포맷 ──────────────────────────────


class TestFormatting:
    def test_효력발생일_언어별_포맷(self):
        assert ContractGeneratorService._format_effective_date(EFFECTIVE, "ko") == "2026-08-01"
        assert ContractGeneratorService._format_effective_date(EFFECTIVE, "en") == "2026-08-01"
        assert ContractGeneratorService._format_effective_date(EFFECTIVE, "zh-CN") == "2026年08月01日"

    def test_효력발생일_타임존은_UTC로_환산(self):
        # KST 2026-08-01 05:00 → UTC 2026-07-31 20:00 (날짜가 하루 당겨져야 함)
        kst = timezone(timedelta(hours=9))
        value = datetime(2026, 8, 1, 5, 0, tzinfo=kst)
        assert ContractGeneratorService._format_effective_date(value, "ko") == "2026-07-31"

    def test_금액_포맷_천단위구분_및_None은_언어별_미확정_문구(self):
        assert ContractGeneratorService._format_amount(1_234_567_890.0, "ko") == "KRW 1,234,567,890"
        assert ContractGeneratorService._format_amount(0.0, "en") == "KRW 0"
        for lang in ("ko", "en", "zh-CN"):
            assert (
                ContractGeneratorService._format_amount(None, lang)
                == _LANGUAGE_COPY[lang]["unpriced_amount"]
            )

    def test_특약_접미사_공백만_있으면_빈문자열_항목은_세미콜론_결합(self):
        assert ContractGeneratorService._special_clause_suffix("ko", []) == ""
        assert ContractGeneratorService._special_clause_suffix("ko", ["  ", ""]) == ""
        suffix = ContractGeneratorService._special_clause_suffix("ko", [" 지체상금 ", "하자보증"])
        assert suffix == " 추가 특약: 지체상금; 하자보증"


# ── 순수 로직: 조항/키텀/마크다운 ──────────────────────────────


class TestDraftComposition:
    def test_키텀_6개_항목과_라벨_로컬라이즈(self):
        terms = ContractGeneratorService._build_key_terms(
            contract_type="construction",
            language="ko",
            counterparty_name="㈜대한건설",
            effective_date=EFFECTIVE,
            contract_amount_krw=None,
            special_clauses=[],
        )
        assert len(terms) == 6
        labels = [t["label"] for t in terms]
        assert labels == ["계약 유형", "상대방", "효력발생일", "계약 금액", "문서 언어", "특약"]
        by_label = {t["label"]: t["value"] for t in terms}
        assert by_label["계약 유형"] == "공사도급계약"
        assert by_label["계약 금액"] == "세부 금액은 별도 협의"
        assert by_label["특약"] == "-"  # 특약 없으면 '-' 표기

    def test_조항_5개_생성과_치환값_반영(self):
        clauses = ContractGeneratorService._build_clauses(
            project_name="Riverfront Tower",
            contract_type="lease",
            language="en",
            counterparty_name="ACME Ltd.",
            effective_date=EFFECTIVE,
            contract_amount_krw=500_000_000.0,
            special_clauses=["No sublease"],
        )
        assert len(clauses) == 5
        titles = [c["title"] for c in clauses]
        assert titles[0] == "Purpose"
        assert "Riverfront Tower" in clauses[0]["body"]
        assert "Lease agreement" in clauses[0]["body"]
        assert "KRW 500,000,000" in clauses[1]["body"]
        assert "ACME Ltd." in clauses[2]["body"]
        assert clauses[3]["body"].endswith("Additional clauses: No sublease")
        assert "2026-08-01" in clauses[4]["body"]

    def test_마크다운_렌더_구조(self):
        md = ContractGeneratorService._render_markdown(
            title="T 계약",
            summary="요약문",
            key_terms=[{"label": "L1", "value": "V1"}],
            clauses=[{"title": "C1", "body": "B1"}, {"title": "C2", "body": "B2"}],
        )
        assert md.startswith("# T 계약\n\n요약문")
        assert "## Key Terms\n- **L1**: V1" in md
        assert "## C1\nB1" in md
        assert "## C2\nB2" in md


# ── DB 의존 경로 (FakeSession) ──────────────────────────────


class TestGenerateDraft:
    async def test_초안생성_정규화_영속화_응답필드(self):
        db = FakeSession(results=[FakeResult(scalar=_fake_project())])
        service = ContractGeneratorService(db)
        result = await service.generate_draft(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            contract_type="SALE",  # 정규화 대상
            target_language="fr",  # 미지원 → ko
            counterparty_name="김철수",
            effective_date=EFFECTIVE,
            contract_amount_krw=1_000_000.0,
            special_clauses=["특약1"],
        )
        assert result["contract_type"] == "sale"
        assert result["target_language"] == "ko"
        assert result["title"] == "강남 오피스 매매계약"
        assert result["status"] == "draft"
        assert result["sign_status"] == "not_requested"
        assert result["project_name"] == "강남 오피스"
        assert len(result["key_terms"]) == 6
        assert len(result["clauses"]) == 5
        assert result["rendered_markdown"].startswith("# 강남 오피스 매매계약")
        assert len(db.added) == 1  # GeneratedContractDraft 1건 영속화
        assert db.commits == 1

    async def test_프로젝트_미존재시_ValueError(self):
        db = FakeSession(results=[FakeResult(scalar=None)])
        service = ContractGeneratorService(db)
        with pytest.raises(ValueError, match="Project not found"):
            await service.generate_draft(
                tenant_id=TENANT_ID,
                project_id=PROJECT_ID,
                contract_type="sale",
                target_language="ko",
                counterparty_name="김철수",
                effective_date=EFFECTIVE,
                contract_amount_krw=None,
                special_clauses=[],
            )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "무날조 관찰: document_url이 실존하지 않는 플레이스홀더 도메인"
            "(https://propai.local/contracts/...)으로 생성됨. 법적 문서 URL이"
            " 실제 저장소/렌더링 산출물과 연결되지 않은 가짜 링크 — 서비스 수정 대상."
        ),
    )
    async def test_document_url은_실존_저장소를_가리켜야_함(self):
        db = FakeSession(results=[FakeResult(scalar=_fake_project())])
        service = ContractGeneratorService(db)
        result = await service.generate_draft(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            contract_type="sale",
            target_language="ko",
            counterparty_name="김철수",
            effective_date=EFFECTIVE,
            contract_amount_krw=None,
            special_clauses=[],
        )
        assert not str(result["document_url"]).startswith("https://propai.local/")


class TestGetLatestAndESign:
    async def test_get_latest_초안없으면_None(self):
        db = FakeSession(
            results=[FakeResult(scalar=_fake_project()), FakeResult(rows=[])]
        )
        service = ContractGeneratorService(db)
        assert (
            await service.get_latest(tenant_id=TENANT_ID, project_id=PROJECT_ID)
        ) is None

    async def test_request_esign_신규요청은_mock_provider로_생성_상태전이(self):
        from apps.api.database.models.phase_v53_contracts import GeneratedContractDraft

        draft = GeneratedContractDraft(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            contract_type="construction",
            target_language="ko",
            title="강남 오피스 공사도급계약",
            counterparty_name="㈜대한건설",
            effective_date=EFFECTIVE,
            status="draft",
            sign_status="not_requested",
            document_url="https://propai.local/contracts/x",
        )
        db = FakeSession(
            results=[FakeResult(scalar=draft), FakeResult(scalar=_fake_project())]
        )
        service = ContractGeneratorService(db)
        result = await service.request_esign(
            tenant_id=TENANT_ID,
            draft_id=draft.id,
            signer_name="홍길동",
            signer_email="hong@example.com",
            signer_phone=None,
        )
        assert result["status"] == "esign_requested"
        assert result["sign_status"] == "requested"
        assert len(db.added) == 1
        esign = db.added[0]
        # 외부 전자서명 연동이 아닌 mock provider임이 정직하게 표기되는지
        assert esign.provider == "mock"
        assert esign.external_request_id.startswith("contract_esign_")
        assert esign.metadata_json["contract_draft_id"] == str(draft.id)
        assert draft.esign_request_id == esign.id
        assert db.flushes == 1
        assert db.commits == 1

    async def test_request_esign_이미_요청된_초안은_중복생성_안함(self):
        from apps.api.database.models.phase_v53_contracts import GeneratedContractDraft

        existing_esign_id = uuid.uuid4()
        draft = GeneratedContractDraft(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            contract_type="construction",
            target_language="ko",
            title="계약",
            counterparty_name="상대방",
            effective_date=EFFECTIVE,
            status="esign_requested",
            sign_status="requested",
            esign_request_id=existing_esign_id,
        )
        db = FakeSession(
            results=[FakeResult(scalar=draft), FakeResult(scalar=_fake_project())]
        )
        service = ContractGeneratorService(db)
        result = await service.request_esign(
            tenant_id=TENANT_ID,
            draft_id=draft.id,
            signer_name="홍길동",
            signer_email="hong@example.com",
            signer_phone="010-0000-0000",
        )
        assert db.added == []  # 신규 ESignRequest 미생성 (멱등)
        assert db.commits == 0
        assert result["esign_request_id"] == existing_esign_id

    async def test_request_esign_초안_미존재시_ValueError(self):
        db = FakeSession(results=[FakeResult(scalar=None)])
        service = ContractGeneratorService(db)
        with pytest.raises(ValueError, match="draft not found"):
            await service.request_esign(
                tenant_id=TENANT_ID,
                draft_id=uuid.uuid4(),
                signer_name="홍길동",
                signer_email="hong@example.com",
                signer_phone=None,
            )
