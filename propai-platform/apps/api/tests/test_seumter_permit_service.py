"""SeumterPermitService 단위 테스트 (W3-1).

라우터(routers/permits.py)에 실배선된 인허가 제출/추적 서비스의
순수 로직 경로(체크리스트·검증·기간 산정·진행률·규칙 로딩)와
DB 의존 경로(submit/get_status)를 FakeSession으로 검증한다.

내장 규칙 경로는 _load_dynamic_rules를 monkeypatch({} 반환)로 고정하고,
동적 규칙 파일 경로는 tmp_path의 실제 JSON으로 검증한다.
"""

import json
import os
import re
import sys
import uuid
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import apps.api.services.seumter_permit_service as sps_module
from apps.api.services.seumter_permit_service import SeumterPermitService

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")

BUILDING_REQUIRED_IDS = ["BA-01", "BA-02", "BA-03", "BA-04", "BA-05"]


@pytest.fixture
def builtin_rules(monkeypatch):
    """외부 규칙 파일을 배제하고 내장 기본 규칙만 사용하도록 고정."""
    monkeypatch.setattr(sps_module, "_load_dynamic_rules", lambda: {})


# ── FakeSession ──────────────────────────────


class FakeResult:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        if self.results:
            return self.results.pop(0)
        return FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None


# ── 순수 로직: 체크리스트 ──────────────────────────────


class TestBuildChecklist:
    def test_소형_민간부지는_조건부_항목_비적용(self, builtin_rules):
        items = SeumterPermitService._build_checklist(
            permit_type="building_permit",
            building_area_sqm=9_999.99,
            is_public=False,
            is_agricultural=False,
            submitted_document_ids=["BA-01"],
        )
        by_id = {item["id"]: item for item in items}
        assert len(items) == 7
        for doc_id in BUILDING_REQUIRED_IDS:
            assert by_id[doc_id]["applicable"] is True
        assert by_id["BA-06"]["applicable"] is False  # large_site 미충족
        assert by_id["BA-07"]["applicable"] is False  # public_or_large 미충족
        assert by_id["BA-01"]["submitted"] is True
        assert by_id["BA-02"]["submitted"] is False

    def test_대형부지_경계값_10000과_15000(self, builtin_rules):
        # 정확히 10,000㎡ → large_site 적용(>=), 15,000㎡ 미만 → public_or_large 비적용
        at_large = SeumterPermitService._build_checklist(
            permit_type="building_permit",
            building_area_sqm=10_000.0,
            is_public=False,
            is_agricultural=False,
            submitted_document_ids=[],
        )
        by_id = {item["id"]: item for item in at_large}
        assert by_id["BA-06"]["applicable"] is True
        assert by_id["BA-07"]["applicable"] is False

        at_public_or_large = SeumterPermitService._build_checklist(
            permit_type="building_permit",
            building_area_sqm=15_000.0,
            is_public=False,
            is_agricultural=False,
            submitted_document_ids=[],
        )
        by_id2 = {item["id"]: item for item in at_public_or_large}
        assert by_id2["BA-07"]["applicable"] is True

    def test_공공_및_농지_조건(self, builtin_rules):
        occupancy = SeumterPermitService._build_checklist(
            permit_type="occupancy_approval",
            building_area_sqm=100.0,
            is_public=True,
            is_agricultural=False,
            submitted_document_ids=[],
        )
        assert {i["id"]: i for i in occupancy}["UC-06"]["applicable"] is True

        development = SeumterPermitService._build_checklist(
            permit_type="development_permit",
            building_area_sqm=100.0,
            is_public=False,
            is_agricultural=True,
            submitted_document_ids=[],
        )
        assert {i["id"]: i for i in development}["DA-06"]["applicable"] is True

    def test_미지원_인허가_유형은_ValueError(self, builtin_rules):
        with pytest.raises(ValueError, match="Unsupported permit type"):
            SeumterPermitService._build_checklist(
                permit_type="demolition_permit",
                building_area_sqm=100.0,
                is_public=False,
                is_agricultural=False,
                submitted_document_ids=[],
            )


class TestValidateChecklist:
    def test_전량제출_준비완료_100점(self):
        checklist = [
            {"id": "A", "name": "doc-a", "required": True, "applicable": True, "submitted": True},
            {"id": "B", "name": "doc-b", "required": True, "applicable": True, "submitted": True},
        ]
        result = SeumterPermitService._validate_checklist(checklist)
        assert result == {
            "required_total": 2,
            "required_submitted": 2,
            "missing_required_documents": [],
            "is_ready": True,
            "readiness_score": 100.0,
        }

    def test_부분제출_점수와_누락목록(self):
        checklist = [
            {"id": "A", "name": "doc-a", "required": True, "applicable": True, "submitted": True},
            {"id": "B", "name": "doc-b", "required": True, "applicable": True, "submitted": False},
            {"id": "C", "name": "doc-c", "required": True, "applicable": True, "submitted": False},
            # 비적용 항목은 분모에서 제외되어야 함
            {"id": "D", "name": "doc-d", "required": False, "applicable": False, "submitted": False},
        ]
        result = SeumterPermitService._validate_checklist(checklist)
        assert result["required_total"] == 3
        assert result["readiness_score"] == 33.33
        assert result["missing_required_documents"] == ["doc-b", "doc-c"]
        assert result["is_ready"] is False

    def test_빈_체크리스트_0점이지만_준비완료로_판정됨(self):
        # 경계 관찰: 적용 항목이 0개면 missing이 없어 is_ready=True가 된다.
        result = SeumterPermitService._validate_checklist([])
        assert result["readiness_score"] == 0.0
        assert result["is_ready"] is True


# ── 순수 로직: 처리기간 산정 ──────────────────────────────


class TestEstimateDuration:
    def test_지역별_기본기간과_한글별칭(self, builtin_rules):
        result = SeumterPermitService._estimate_duration_contextual(
            permit_type="building_permit",
            region="서울특별시",
            building_area_sqm=0.0,
            is_public=False,
            is_agricultural=False,
        )
        assert result["region_key"] == "seoul"
        assert result["base_business_days"] == 20.0
        assert result["business_days"] == 20
        assert result["calendar_days"] == 28  # 20 * 1.4
        assert result["applied_multiplier"] == 1.0

    def test_미등록_지역은_default_기간(self, builtin_rules):
        result = SeumterPermitService._estimate_duration_contextual(
            permit_type="building_permit",
            region="제주",
            building_area_sqm=0.0,
            is_public=False,
            is_agricultural=False,
        )
        assert result["base_business_days"] == 15.0
        assert result["business_days"] == 15

    def test_가산계수_경계값과_중첩적용(self, builtin_rules):
        # 정확히 10,000㎡ → 대형(1.10)이며 초대형(1.20) 아님
        large = SeumterPermitService._estimate_duration_contextual(
            permit_type="building_permit",
            region="seoul",
            building_area_sqm=10_000.0,
            is_public=False,
            is_agricultural=False,
        )
        assert large["applied_multiplier"] == 1.10
        assert large["business_days"] == 22  # 20 * 1.1

        # 정확히 30,000㎡ + 공공 + 농지 → 1.2 * 1.15 * 1.1 = 1.518
        stacked = SeumterPermitService._estimate_duration_contextual(
            permit_type="building_permit",
            region="seoul",
            building_area_sqm=30_000.0,
            is_public=True,
            is_agricultural=True,
        )
        assert stacked["applied_multiplier"] == 1.518
        assert stacked["business_days"] == 30  # round(20 * 1.518) = round(30.36)
        assert stacked["calendar_days"] == 42

    def test_레거시_estimate_duration은_컨텍스트없는_동등값(self, builtin_rules):
        legacy = SeumterPermitService._estimate_duration("occupancy_approval", "gyeonggi")
        contextual = SeumterPermitService._estimate_duration_contextual(
            permit_type="occupancy_approval",
            region="gyeonggi",
            building_area_sqm=0.0,
            is_public=False,
            is_agricultural=False,
        )
        assert legacy == contextual
        assert legacy["business_days"] == 10

    def test_미지원_유형_ValueError(self, builtin_rules):
        with pytest.raises(ValueError, match="Unsupported permit type"):
            SeumterPermitService._estimate_duration_contextual(
                permit_type="unknown_permit",
                region="seoul",
                building_area_sqm=0.0,
                is_public=False,
                is_agricultural=False,
            )


class TestDynamicRules:
    def test_외부_규칙파일이_내장규칙보다_우선한다(self, monkeypatch, tmp_path):
        rules = {
            "region_aliases": {"테스트시": "testregion"},
            "permit_types": {
                "building_permit": {
                    "checklist": [{"id": "X-01", "name": "Custom doc", "required": True}],
                    "durations": {"testregion": 7, "default": 5},
                }
            },
            "duration_multipliers": {"public_project_multiplier": 2.0},
        }
        rules_path = tmp_path / "rules.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        monkeypatch.setattr(
            sps_module,
            "get_settings",
            lambda: SimpleNamespace(seumter_permit_rules_path=str(rules_path)),
        )

        checklist = SeumterPermitService._build_checklist(
            permit_type="building_permit",
            building_area_sqm=0.0,
            is_public=False,
            is_agricultural=False,
            submitted_document_ids=[],
        )
        assert [item["id"] for item in checklist] == ["X-01"]

        duration = SeumterPermitService._estimate_duration_contextual(
            permit_type="building_permit",
            region="테스트시",
            building_area_sqm=0.0,
            is_public=True,
            is_agricultural=False,
        )
        assert duration["region_key"] == "testregion"
        assert duration["base_business_days"] == 7.0
        assert duration["applied_multiplier"] == 2.0
        assert duration["business_days"] == 14

    def test_규칙파일_없거나_깨져도_내장규칙_폴백(self, monkeypatch, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{not-json", encoding="utf-8")
        monkeypatch.setattr(
            sps_module,
            "get_settings",
            lambda: SimpleNamespace(seumter_permit_rules_path=str(broken)),
        )
        monkeypatch.setattr(sps_module, "_DEFAULT_RULES_PATH", tmp_path / "absent.json")
        assert sps_module._load_dynamic_rules() == {}
        # 빈 규칙에서도 내장 체크리스트로 정상 동작
        items = SeumterPermitService._build_checklist(
            permit_type="building_permit",
            building_area_sqm=0.0,
            is_public=False,
            is_agricultural=False,
            submitted_document_ids=[],
        )
        assert len(items) == 7


# ── 순수 로직: 진행률/접수번호 ──────────────────────────────


class TestProgressAndReference:
    def test_진행률_단계별_및_미지단계_폴백(self, builtin_rules):
        assert SeumterPermitService._progress("document-prep") == 20.0
        assert SeumterPermitService._progress("submitted") == 40.0
        assert SeumterPermitService._progress("approved") == 100.0
        assert SeumterPermitService._progress("no-such-stage") == 20.0

    def test_접수번호_형식(self):
        ref = SeumterPermitService._submission_reference(PROJECT_ID)
        assert re.fullmatch(
            r"SEUMTER-\d{8}-" + str(PROJECT_ID)[:8] + r"-[0-9A-F]{6}", ref
        )


# ── DB 의존 경로 (FakeSession) ──────────────────────────────


class TestSubmit:
    async def _submit(self, *, submitted_docs, submit_flag=True):
        db = FakeSession()
        service = SeumterPermitService(db)
        result = await service.submit(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            permit_type="building_permit",
            region="seoul",
            building_area_sqm=500.0,
            is_public=False,
            is_agricultural=False,
            applicant_name="홍길동",
            submit_to_seumter=submit_flag,
            submitted_document_ids=submitted_docs,
        )
        return db, result

    async def test_필수서류_완비시_submitted_전이(self, builtin_rules):
        db, result = await self._submit(submitted_docs=BUILDING_REQUIRED_IDS)
        assert result["status"] == "submitted"
        assert result["current_stage"] == "submitted"
        assert result["readiness_score"] == 100.0
        assert result["progress_pct"] == 40.0
        assert result["missing_required_documents"] == []
        assert result["submitted_at"] is not None
        assert result["estimated_business_days"] == 20
        assert result["estimated_calendar_days"] == 28
        assert len(db.added) == 1
        assert db.commits == 1

    async def test_서류미비시_draft_유지_및_누락목록(self, builtin_rules):
        db, result = await self._submit(submitted_docs=["BA-01"])
        assert result["status"] == "draft"
        assert result["current_stage"] == "document-prep"
        assert result["submitted_at"] is None
        assert result["readiness_score"] == 20.0
        assert "Structural review" in result["missing_required_documents"]

    async def test_제출플래그_False면_완비여도_draft(self, builtin_rules):
        _, result = await self._submit(
            submitted_docs=BUILDING_REQUIRED_IDS, submit_flag=False
        )
        assert result["status"] == "draft"
        assert result["submitted_at"] is None

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "무날조 위반 후보: submit_to_seumter=True이면 status='submitted'로 기록되고"
            " 접수번호도 'SEUMTER-…'로 발급되지만, 모듈에 세움터 외부 전송 경로"
            "(httpx/aiohttp 등)가 전혀 없어 실제 접수 없이 제출된 것처럼 보인다."
            " 실연동 또는 'local-simulated' 명시가 필요 — 서비스 수정 대상."
        ),
    )
    async def test_세움터_실전송_경로가_존재해야_함(self, builtin_rules):
        import inspect

        source = inspect.getsource(sps_module)
        assert ("httpx" in source) or ("aiohttp" in source) or ("requests" in source)


class TestGetStatus:
    async def test_미존재_submission은_None(self):
        db = FakeSession(results=[FakeResult(scalar=None)])
        service = SeumterPermitService(db)
        result = await service.get_status(
            tenant_id=TENANT_ID, submission_id=uuid.uuid4()
        )
        assert result is None
        assert db.commits == 0
