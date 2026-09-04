"""등기 **권리분석 보고서** 어댑터의 계약.

【실장애가 만든 요구 — 2026-08-24】
오산 내삼미동 448-2·347-8 은 등기부가 **정상 발급**됐는데 권리분석(LLM)만 실패했다.
그런 필지를 보고서 표에서 빼면 문서는 "N필지 전부 안전"이라고 말하게 된다 —
**없는 안전을 만든다.** 그래서 이 스위트의 중심은 표가 예쁘게 나오는지가 아니라
**미분석 필지가 문서 표면까지 살아 나오는가**다.

【두 모집단을 가른다】
`ai` 는 성공·실패 **둘 다** dict 다(폴백도 `safety_grade:"주의"` 를 담는다).
픽스처가 그 둘을 실제로 다른 값으로 갈라야 배선을 끊었을 때 죽는다.
"""

from __future__ import annotations

import pytest

from app.services.report.render import build_report_model_from_registry_rights


def _ok(jibun: str, *, grade: str = "안전", owner: str = "홍길동",
        mortgage: list | None = None, seizure: list | None = None) -> dict:
    return {
        "jibun": jibun,
        "result": {
            "status": "ok",
            "ai": {
                "generated": True,
                "safety_grade": grade,
                "summary": f"{jibun} 요약",
                "ownership": {"current_owner": owner, "share": "1/1"},
                "mortgage": mortgage or [],
                "seizure": seizure or [],
                "right_to_demand_sale": {"possible": "가능", "reason": "단독소유"},
            },
        },
    }


def _llm_failed(jibun: str, reason: str = "JSONDecodeError: Unterminated string") -> dict:
    """등기는 받았는데 권리분석만 실패한 건 — 실장애의 형태."""
    return {
        "jibun": jibun,
        "result": {
            "status": "ok",
            "ai": {
                "generated": False,
                "safety_grade": "주의",       # ★폴백도 등급을 담는다
                "summary": "분석 불가",
                "failure_reason": reason,
            },
        },
    }


def _not_issued(jibun: str, msg: str = "민원캐시 잔액이 부족합니다") -> dict:
    return {"jibun": jibun, "result": {"status": "error", "message": msg}}


def _text(model) -> str:
    """모델 전체를 한 문자열로 — 어느 섹션에 있든 '문서에 남았는가'를 본다."""
    import dataclasses

    return repr(dataclasses.asdict(model))


class TestUnanalyzedParcelsSurvive:
    def test_전제_두_모집단이_실제로_다른_문서를_만든다(self):
        a = _text(build_report_model_from_registry_rights([_ok("가")]))
        b = _text(build_report_model_from_registry_rights([_llm_failed("가")]))
        assert a and b
        assert a != b, "성공/폴백이 같은 문서를 만든다 — 픽스처가 모집단을 가르지 못한다"

    def test_폴백은_분석_성공으로_세지_않는다(self):
        m = build_report_model_from_registry_rights([_ok("가"), _llm_failed("나")])
        assert m.meta.completeness == {"total": 2, "filled": 1, "empty": 1, "pct": 50.0}

    def test_미분석_필지가_지번과_사유까지_문서에_남는다(self):
        m = build_report_model_from_registry_rights([_ok("가"), _llm_failed("내삼미동 448-2")])
        s = _text(m)
        assert "내삼미동 448-2" in s, "미분석 필지가 문서에서 사라졌다"
        assert "JSONDecodeError" in s, "왜 분석되지 않았는지가 사라졌다"
        assert "미분석" in s

    def test_요약이_분모를_드러낸다(self):
        m = build_report_model_from_registry_rights([_ok("가"), _llm_failed("나"), _not_issued("다")])
        s = _text(m)
        assert "1 / 3 필지" in s, "분모 없이 성공 건수만 말하면 전량 분석으로 읽힌다"

    def test_전부_실패해도_보고서는_거짓_안전을_말하지_않는다(self):
        m = build_report_model_from_registry_rights([_llm_failed("가"), _llm_failed("나")])
        s = _text(m)
        assert "없습니다" in s
        assert m.meta.completeness["filled"] == 0

    def test_대조군_전부_성공이면_미분석_섹션을_만들지_않는다(self):
        m = build_report_model_from_registry_rights([_ok("가"), _ok("나")])
        titles = [sec.title for sec in m.sections]
        assert not any("미분석" in t for t in titles), "없는 경고를 만든다"
        assert m.meta.completeness["pct"] == 100.0


class TestAggregatesDoNotUnderstate:
    def test_근저당_압류_건수는_분석된_건에서만_센다(self):
        m = build_report_model_from_registry_rights([
            _ok("가", mortgage=[{"mortgagee": "A은행", "max_claim": "120000000"}],
                seizure=[{"type": "압류", "holder": "세무서"}]),
            _llm_failed("나"),
        ])
        s = _text(m)
        assert "1건" in s
        assert "A은행" in s

    def test_금액을_읽지_못하면_0으로_깔지_않고_제외를_밝힌다(self):
        # '1억 2,000만원' 같은 표기는 자릿수를 바꾼다 — 잘못 곱하느니 판단을 보류한다.
        m = build_report_model_from_registry_rights([
            _ok("가", mortgage=[{"mortgagee": "A은행", "max_claim": "채권최고액 1억 2,000만원"}]),
        ])
        assert "판독 불가" in _text(m)

    def test_최고_위험등급은_가장_나쁜_것을_고른다(self):
        m = build_report_model_from_registry_rights([_ok("가", grade="안전"), _ok("나", grade="위험")])
        assert "위험" in _text(m)


class TestRendersEndToEnd:
    @pytest.mark.parametrize("fmt", ["pdf", "docx"])
    def test_실제로_파일이_나온다(self, fmt):
        """모델이 렌더러를 통과하는지 — 어댑터만 초록이고 렌더에서 죽으면 사용자에겐 0이다."""
        from app.services.report.render import render_report

        m = build_report_model_from_registry_rights(
            [_ok("가", mortgage=[{"mortgagee": "A은행", "max_claim": "120000000"}]), _llm_failed("나")],
            project_address="경기도 오산시 내삼미동",
            generated_at="2026-08-24 18:00",
        )
        data, mime, ext = render_report(m, fmt)
        assert len(data) > 1000, f"{fmt} 산출물이 너무 작다 — 빈 문서일 수 있다"
        assert ext == fmt and mime


class TestKPISignalContract:
    """★계약 잠금 — 신호색 이름이 렌더러까지 흘러가면 PDF 다운로드가 500 으로 죽는다.

    실사고(2026-08-24): `model.py` 독스트링이 `signal='safe'|'warn'|'danger'` 라고 안내해
    새 어댑터가 이름을 넣었고, PDF 렌더러가 reportlab 색 파서에 그대로 넘겨 터졌다.
    **docx 는 색을 안 써서 통과했다** — 포맷 하나만 보면 못 잡는다.
    """

    def test_이름을_주면_hex_로_정규화된다(self):
        from app.services.report.render.model import KPITile
        from app.services.report.render.tokens import SIGNAL

        assert KPITile(label="a", value="b", signal="warn").signal == SIGNAL["warn"]
        assert KPITile(label="a", value="b", signal="#123456").signal == "#123456"
        assert KPITile(label="a", value="b").signal is None

    def test_알_수_없는_값은_조용히_통과하지_않는다(self):
        from app.services.report.render.model import KPITile

        with pytest.raises(ValueError):
            KPITile(label="a", value="b", signal="보라색")

    def test_이_어댑터가_만드는_모든_타일이_hex_이거나_None(self):
        from app.services.report.render.model import KPITileBlock
        from app.services.report.render.tokens import SIGNAL

        m = build_report_model_from_registry_rights([_ok("가", grade="위험"), _llm_failed("나")])
        tiles = [t for b in (m.exec_summary.blocks if m.exec_summary else [])
                 if isinstance(b, KPITileBlock) for t in b.tiles]
        assert tiles, "타일이 하나도 없다 — 공허한 검사"
        assert any(t.signal for t in tiles), "신호색이 전부 비었다 — 대조군이 성립하지 않는다"
        for t in tiles:
            assert t.signal is None or t.signal.startswith("#"), f"{t.label}: {t.signal!r}"
            assert t.signal is None or t.signal in SIGNAL.values()
