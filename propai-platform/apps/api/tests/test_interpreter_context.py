"""인터프리터 공용 컨텍스트 빌더(SSOT) + precheck 배선 테스트 — REFACTOR CR-1/CR-3.

검증 범위:
- build_interpreter_context: 정상 collected→analysis_data 키정합(_extract_compact_data
  기대 스키마)·evidence_text 직렬화·누락키 graceful(빈dict/None)·무날조(없는 값 미생성).
- wrap_evidence: 표준계약 6키·legal_link verified만.
- SiteAnalysisInterpreter.generate_interpretation: evidence_text 인자 수용·기존 호출
  (evidence_text 없이) 무파손(시그니처 회귀).
- precheck: use_llm=True시 ai_interpretation 가산(인터프리터 mock)·기존 키 불변·
  인터프리터 실패시 graceful(기존 응답 무손상).

순수 헬퍼는 외부 I/O 없이 결정론 검증, precheck는 zoning/인터프리터를 모킹한다.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.ai.interpreter_context import (  # noqa: E402
    build_interpreter_context,
    wrap_evidence,
)


def _run(coro):
    """이벤트 루프 안전 실행(러닝 루프 부재 환경에서도 동작)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# collected(precheck 실데이터) 표준 픽스처 — legal(실효한도)·공시지가·근거·특이부지.
def _sample_collected(with_special: bool = False) -> dict:
    collected = {
        "address": "서울특별시 강남구 역삼동 123",
        "zone_type": "제2종일반주거지역",
        "area_sqm": 660.0,
        "official_price": 12_000_000.0,
        "legal": {
            "bcr_pct": 60,
            "far_pct": 250,
            "height_m": None,
            "source": "국토의 계획 및 이용에 관한 법률 제78조",
            "zone_type": "제2종일반주거지역",
            "applied_bcr_pct": 60,
            "applied_far_pct": 200,
            "ordinance_far_pct": 200,
            "ordinance_bcr_pct": 60,
            "ordinance_confirmed": True,
            "far_source": "강남구 도시계획조례 적용",
            "sigungu": "강남구",
            "legal_ref_keys": ["far_limit", "bcr_limit", "ordinance_far"],
        },
        "evidence": [
            {
                "id": "ev_far",
                "target": "legal_limits.far_pct",
                "formula": "적용 용적률 = min(법정상한 250%, 강남구 조례 200%)",
                "result": "200%",
            }
        ],
        "legal_refs": [
            {"label": "국토계획법 시행령 제85조", "url": "https://www.law.go.kr/x", "url_status": "ok"},
            {"label": "강남구 도시계획조례", "url": "", "url_status": "pending"},
        ],
        "sources": ["permit_validator", "auto_zoning_service", "auto_zoning_service"],
    }
    if with_special:
        collected["special_parcel"] = {
            "is_special": True,
            "developability": "PRECONDITION",
            "severity_label": "중대한 선행절차 필수",
            "resolvable": "CONDITIONAL",
            "development_caveat": "학교 폐지·용도변경 전제",
            "honest_disclosure": "현 상태 개발 제한",
            "factors": [{"category": "학교용지", "developability": "PRECONDITION", "resolvable": "CONDITIONAL"}],
        }
    return collected


# ──────────────────────────────────────────────────────────────────────────
# wrap_evidence — 표준계약 6키
# ──────────────────────────────────────────────────────────────────────────
class TestWrapEvidence:
    def test_six_keys_present(self):
        ev = wrap_evidence(
            value=250, basis="법정 용적률 상한", source="ZONE_LIMITS",
            provenance="국토계획법 제78조", legal_link="https://www.law.go.kr/x",
            confidence="high",
        )
        assert set(ev.keys()) == {
            "value", "basis", "source", "provenance", "legal_link", "confidence"
        }
        assert ev["value"] == 250
        assert ev["legal_link"] == "https://www.law.go.kr/x"

    def test_legal_link_none_when_unverified(self):
        # legal_link 미제공 → None(pending 취지, 할루시네이션 링크 금지).
        ev = wrap_evidence(value=200, basis="조례 적용값", source="ordinance")
        assert ev["legal_link"] is None
        assert ev["provenance"] is None
        assert ev["confidence"] is None


# ──────────────────────────────────────────────────────────────────────────
# build_interpreter_context — analysis_data 키정합 + evidence_text 직렬화
# ──────────────────────────────────────────────────────────────────────────
class TestBuildInterpreterContext:
    def test_returns_four_elements(self):
        ctx = build_interpreter_context(_sample_collected())
        assert set(ctx.keys()) == {
            "analysis_data", "evidence_text", "analysis_signals", "prior_context"
        }

    def test_analysis_data_matches_extract_compact_schema(self):
        """analysis_data가 _extract_compact_data가 읽는 키셋과 정합."""
        ctx = build_interpreter_context(_sample_collected())
        ad = ctx["analysis_data"]
        # 최상위 식별자.
        assert ad["address"] == "서울특별시 강남구 역삼동 123"
        assert ad["zone_type"] == "제2종일반주거지역"
        assert ad["land_area_sqm"] == 660.0
        # effective_far: 법정/조례/실효 매핑(_extract_compact_data가 읽는 키).
        ef = ad["effective_far"]
        assert ef["national_bcr_pct"] == 60
        assert ef["national_far_pct"] == 250
        assert ef["ordinance_far_pct"] == 200
        assert ef["effective_far_pct"] == 200  # applied_far_pct
        assert ef["effective_bcr_pct"] == 60   # applied_bcr_pct
        assert ef["source"] == "강남구 도시계획조례 적용"  # far_source 우선
        # land_prices: 공시지가.
        lp = ad["land_prices"]
        assert lp["official_price_per_sqm"] == 12_000_000.0
        assert "official_price_per_pyeong" in lp
        assert "total_official_value_won" in lp

    def test_extract_compact_data_consumes_without_error(self):
        """실제 SiteAnalysisInterpreter._extract_compact_data가 analysis_data를 소화."""
        from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter

        ctx = build_interpreter_context(_sample_collected())
        compact = SiteAnalysisInterpreter()._extract_compact_data(ctx["analysis_data"])
        # effective_far·land_prices가 compact에 전달됨(그라운딩 유효).
        assert "effective_far" in compact
        assert compact["effective_far"]["effective_far_pct"] == 200
        assert "land_prices" in compact

    def test_evidence_text_serialized(self):
        ctx = build_interpreter_context(_sample_collected())
        et = ctx["evidence_text"]
        assert et is not None
        assert "근거 트레이스" in et
        assert "200%" in et                    # evidence result
        assert "국토계획법 시행령 제85조" in et  # legal_refs verified label
        assert "https://www.law.go.kr/x" in et  # verified 링크만
        assert "공시지가" in et                  # official_price 출처

    def test_evidence_text_excludes_pending_links(self):
        ctx = build_interpreter_context(_sample_collected())
        et = ctx["evidence_text"]
        # pending(빈 url) 조례는 링크 없이 '확인 필요' 텍스트만(무날조 링크).
        assert "강남구 도시계획조례 (링크 확인 필요)" in et

    def test_special_parcel_signal_and_passthrough(self):
        ctx = build_interpreter_context(_sample_collected(with_special=True))
        # analysis_signals에 special_parcel 신호.
        assert ctx["analysis_signals"]["special_parcel"]["developability"] == "PRECONDITION"
        # analysis_data에 원형 통과(_extract_compact_data가 is_special 게이트로 읽음).
        assert ctx["analysis_data"]["special_parcel"]["is_special"] is True

    def test_no_fabrication_when_missing(self):
        """없는 값은 생성하지 않는다(무날조) — 최소 collected."""
        ctx = build_interpreter_context({"zone_type": "제3종일반주거지역"})
        ad = ctx["analysis_data"]
        assert ad == {"zone_type": "제3종일반주거지역"}
        # 공시지가·근거 없음 → land_prices/effective_far 미생성, evidence_text None.
        assert "land_prices" not in ad
        assert "effective_far" not in ad
        assert ctx["evidence_text"] is None
        assert ctx["prior_context"] is None
        assert ctx["analysis_signals"] == {}

    def test_empty_and_none_collected_graceful(self):
        """빈 dict/None collected에도 graceful(KeyError 금지)."""
        for c in ({}, None):
            ctx = build_interpreter_context(c)
            assert ctx["analysis_data"] == {}
            assert ctx["evidence_text"] is None
            assert ctx["prior_context"] is None
            assert ctx["analysis_signals"] == {}

    def test_prior_context_passthrough(self):
        c = _sample_collected()
        c["prior_context"] = "직전심사: 조건부 통과"
        ctx = build_interpreter_context(c)
        assert ctx["prior_context"] == "직전심사: 조건부 통과"


# ──────────────────────────────────────────────────────────────────────────
# SiteAnalysisInterpreter.generate_interpretation — evidence_text 시그니처 회귀
# ──────────────────────────────────────────────────────────────────────────
class TestGenerateInterpretationSignature:
    def test_accepts_evidence_text_kw(self):
        """evidence_text 인자 수용 + _invoke로 전달(무네트워크: _invoke 모킹)."""
        from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter

        interp = SiteAnalysisInterpreter()
        captured = {}

        async def _fake_invoke(user_prompt, **kwargs):  # noqa: ANN001
            captured.update(kwargs)
            return {"overall_summary": "ok"}

        interp._invoke = _fake_invoke  # type: ignore[method-assign]
        result = _run(interp.generate_interpretation(
            {"address": "A", "zone_type": "Z", "land_area_sqm": 100},
            evidence_text="근거X", prior_context="prior Y",
        ))
        assert result == {"overall_summary": "ok"}
        # _invoke에 evidence_text/prior_context가 그대로 전달됨.
        assert captured.get("evidence_text") == "근거X"
        assert captured.get("prior_context") == "prior Y"

    def test_backward_compat_without_evidence_text(self):
        """기존 호출(evidence_text 없이)도 무파손 — 시그니처 회귀 방지."""
        from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter

        interp = SiteAnalysisInterpreter()
        captured = {}

        async def _fake_invoke(user_prompt, **kwargs):  # noqa: ANN001
            captured.update(kwargs)
            return {"overall_summary": "legacy ok"}

        interp._invoke = _fake_invoke  # type: ignore[method-assign]
        # evidence_text 미지정(기존 호출부 형태).
        result = _run(interp.generate_interpretation(
            {"address": "A", "zone_type": "Z", "land_area_sqm": 100},
        ))
        assert result == {"overall_summary": "legacy ok"}
        assert captured.get("evidence_text") is None
        assert captured.get("prior_context") is None


# ──────────────────────────────────────────────────────────────────────────
# precheck 배선 — use_llm=True시 ai_interpretation 가산 + graceful
# ──────────────────────────────────────────────────────────────────────────
class TestPrecheckWiring:
    def _patched_run(self, monkeypatch, *, use_llm, interp_result=None, interp_raises=False):
        import app.services.precheck.precheck_service as svc

        async def _fake_analyze(self, address):  # noqa: ANN001
            return {
                "zone_type": "제2종일반주거지역",
                "pnu": "1168010100101230045",
                "land_area_sqm": 660.0,
                "official_price_per_sqm": 12_000_000.0,
            }

        async def _fake_ordinance(self, address, zone_type):  # noqa: ANN001
            return {"sigungu": "강남구", "ordinance_far": None, "ordinance_bcr": None}

        monkeypatch.setattr(
            svc.AutoZoningService, "analyze_by_address", _fake_analyze, raising=True
        )
        from app.services.land_intelligence.ordinance_service import OrdinanceService

        monkeypatch.setattr(
            OrdinanceService, "get_ordinance_limits", _fake_ordinance, raising=True
        )

        # 인터프리터 모킹(무네트워크·무과금). generate_interpretation을 결정론화.
        from app.services.ai.site_analysis_interpreter import SiteAnalysisInterpreter

        async def _fake_generate(self, analysis_data, *, evidence_text=None, prior_context=None):  # noqa: ANN001
            if interp_raises:
                raise RuntimeError("boom")
            return interp_result

        monkeypatch.setattr(
            SiteAnalysisInterpreter, "generate_interpretation", _fake_generate, raising=True
        )

        # _llm_one_liner도 모킹(폴백 경로 결정론 — 네트워크 없이).
        async def _fake_one_liner(*args, **kwargs):  # noqa: ANN001
            return "규칙 폴백 한 줄"

        monkeypatch.setattr(svc, "_llm_one_liner", _fake_one_liner, raising=True)

        return _run(svc.run_instant_precheck(
            address="서울특별시 강남구 역삼동 123", use_llm=use_llm
        ))

    def test_use_llm_false_no_ai_interpretation(self, monkeypatch):
        """use_llm=False(기본) → ai_interpretation=None, llm_note 미설정(기존 동작)."""
        resp = self._patched_run(monkeypatch, use_llm=False)
        assert resp["ok"] is True
        assert resp["ai_interpretation"] is None
        assert resp["summary"]["llm_note"] is None

    def test_use_llm_true_adds_ai_interpretation(self, monkeypatch):
        """use_llm=True + 인터프리터 성공 → ai_interpretation 가산 + llm_note 파생."""
        interp_out = {
            "overall_summary": "제2종일반주거 660㎡, 실효 용적률 200%로 공동주택 개발 적합.",
            "effective_far_interpretation": "조례 200% 적용.",
            "risk_factors": "일조·주차.",
        }
        resp = self._patched_run(monkeypatch, use_llm=True, interp_result=interp_out)
        assert resp["ok"] is True
        # ai_interpretation 가산(신규 키).
        assert resp["ai_interpretation"] == interp_out
        # llm_note는 overall_summary에서 파생(80자→다변량 해석의 요약).
        assert resp["summary"]["llm_note"].startswith("제2종일반주거 660㎡")
        # 기존 9키 전부 보존.
        for k in ("ok", "address", "pnu", "zone_type", "area_sqm", "legal_limits",
                  "methods", "summary", "elapsed_ms", "sources"):
            assert k in resp
        # 신규 5블록 보존.
        for k in ("inputs", "data_quality", "legal_refs", "evidence", "feasibility_band"):
            assert k in resp

    def test_interpreter_failure_graceful(self, monkeypatch):
        """인터프리터 예외 → ai_interpretation=None + 규칙 폴백 llm_note(응답 무손상)."""
        resp = self._patched_run(monkeypatch, use_llm=True, interp_raises=True)
        assert resp["ok"] is True
        assert resp["ai_interpretation"] is None
        # 폴백: _llm_one_liner 결과가 llm_note에 들어감(정직 폴백).
        assert resp["summary"]["llm_note"] == "규칙 폴백 한 줄"
        # 기존 블록 무손상.
        for k in ("legal_limits", "methods", "evidence", "feasibility_band"):
            assert k in resp

    def test_interpreter_empty_dict_graceful(self, monkeypatch):
        """인터프리터 빈 dict(호출 실패) → ai_interpretation=None + 폴백."""
        resp = self._patched_run(monkeypatch, use_llm=True, interp_result={})
        assert resp["ai_interpretation"] is None
        assert resp["summary"]["llm_note"] == "규칙 폴백 한 줄"
