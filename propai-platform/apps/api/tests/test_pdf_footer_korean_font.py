"""PDF 꼬리말이 **한글로 그려지는지** 잠근다 — 전 보고서가 두부(□)로 나가고 있었다.

★라이브 실측(2026-08-26 · 실거래 신고내역 보고서 6쪽):
    추출 텍스트에 `■` **114개** — 전부 머리말/꼬리말 줄.
    **본문 한글은 1,949자로 정상**이었다.
  즉 **본문만 보면 정상으로 보인다.** 바이트가 나오는 것과 **읽을 만한 것**은 다르다.

★근본: `footer_callback` 이 `T.FONT_FALLBACK`(= `Helvetica`, 라틴·숫자 전용)으로 그렸는데
  꼬리말 내용은 **한글**이다 — `BRANDING`·`CONFIDENTIAL_LABEL`·`APPROVAL_LABEL`.
  한글 폰트는 `register_font()` 가 **이미 등록**하고 있었다 — 꼬리말만 안 썼다.

★파장: `footer_callback` 소비처는 `pdf_renderer` **하나**이고 그것이 **단일 PDF 렌더러**다.
  따라서 **플랫폼의 모든 PDF 보고서**가 같은 상태였다(토지분석·은행제출·탁상감정·설계심사·…).
"""

from __future__ import annotations

import ast
import inspect

import pytest

pypdf = pytest.importorskip("pypdf", reason="PDF 본문 검증에 필요")

from app.services.report.render.engine import render_report  # noqa: E402
from app.services.report.render.model import (  # noqa: E402
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
)


def _pdf_text(model: ReportModel) -> str:
    from io import BytesIO

    data, _, _ = render_report(model, "pdf")
    r = pypdf.PdfReader(BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def _model() -> ReportModel:
    return ReportModel(
        meta=ReportMeta(title="꼬리말 폰트 검증", subtitle="한글"),
        sections=[Section(title="본문", blocks=[NarrativeBlock(paragraphs=["본문 한글입니다."])])],
    )


class Test꼬리말한글:
    def test_꼬리말_한글이_두부로_나가지_않는다(self) -> None:
        """★탐지 — 이 PR 이 고친 결함 그 자체."""
        t = _pdf_text(_model())
        assert "■" not in t and "□" not in t, "꼬리말이 두부로 렌더됐다"

    def test_꼬리말_한글이_실제로_추출된다(self) -> None:
        """두부가 없는 것만으로는 부족하다 — **그 글자가 있어야** 한다.

        ★대조군 없이 `"■" not in t` 만 보면 **꼬리말을 통째로 지워도** 통과한다.
        """
        from app.services.report.render import tokens as T

        t = _pdf_text(_model())
        assert T.BRANDING.split()[0] in t, f"브랜딩이 없다: {T.BRANDING}"
        assert T.CONFIDENTIAL_LABEL.split()[0] in t, "기밀 라벨이 없다"

    def test_본문_한글도_함께_확인한다(self) -> None:
        """본문이 깨졌는데 꼬리말만 보고 통과하지 않게(반대 방향)."""
        assert "본문 한글입니다" in _pdf_text(_model())


class Test배선:
    def test_렌더러가_꼬리말에_본문폰트를_넘긴다(self) -> None:
        """★배선 — **`render_pdf` 함수 안에서** `footer_callback` 에 폰트를 넘기는지 본다.

        ★모듈 전체 스코프로 보면 *"어딘가에서 넘기면"* 초록이라, 인자를 빼는 회귀를 못 잡는다.
          대조군도 **문법 구조**에 결속한다(대상 함수가 사라지면 `StopIteration`).
        """
        from app.services.report.render import pdf_renderer

        tree = ast.parse(inspect.getsource(pdf_renderer))
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and "render_pdf" in n.name
        )  # ← 살아 있는 대조군
        ok = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "footer_callback"
            and len(n.args) >= 2          # (meta, font)
            for n in ast.walk(fn)
        )
        assert ok, "footer_callback 에 폰트를 넘기지 않는다 — 꼬리말이 다시 두부가 된다"

    def test_폰트_미지정시_종전대로_폴백한다(self) -> None:
        """호출부를 갱신 안 한 곳이 있어도 깨지지 않는다(무회귀)."""
        from app.services.report.render import pdf_kit as K

        cb = K.footer_callback(ReportMeta(title="x"))   # font 생략
        assert callable(cb)
