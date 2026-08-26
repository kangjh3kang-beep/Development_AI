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

from app.services.report.render.engine import render_report
from app.services.report.render.model import (
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
)

#: ★**두부(글리프 부재) 후보 — 한 종류가 아니다.**
#:
#:   2026-08-26 실측: 같은 PDF 를 두 사람이 쟀는데 **0 과 32** 로 갈렸다.
#:   한쪽이 `□ / U+FFFD / ☐` 만 세고 **`■`(U+25A0)를 안 셌기** 때문이다.
#:   reportlab 이 `Helvetica` 로 한글을 만나면 **`■`** 를 낸다 — 그러나 렌더러·폰트·뷰어에 따라
#:   다른 글자가 나온다. **하나만 고르면 0 이 나오고, 그 0 을 부재로 읽게 된다.**
#:   ★`■` 를 고른 것도 근거가 아니라 **우연**이었다 — 그래서 목록으로 박는다.
TOFU_GLYPHS = ("■", "□", "\ufffd", "☐", "▪", "▫", "◻", "◼")


def tofu_counts(text: str) -> dict[str, int]:
    """텍스트에 나타난 두부 글자를 **후보 전체**로 센다(0 인 것은 제외).

    ★반환이 빈 dict 여야 "두부 없음"이다. `text.count("■") == 0` 만 보면 **다른 글자로 나온
      두부를 놓친다** — 그것이 위 실측의 정확한 실패 형태다.
    """
    return {g: text.count(g) for g in TOFU_GLYPHS if text.count(g)}


def _pdf_text(model: ReportModel) -> str:
    """PDF 를 렌더해 텍스트를 추출한다.

    ★`importorskip` 을 **여기 안에** 둔다 — 모듈 레벨에 두면 `pypdf` 가 없을 때
      **파일 전체가 skip** 되고, `ast`/`inspect` 만 쓰는 **배선 락까지 함께 꺼진다.**

    ★2026-08-26 실측(동료 세션이 CI 로그로 적발): `pypdf` 가 의존성에 없어
      CI 에서 이 파일 **3건이 전부 skip** 됐다. `Backend (pytest)` 는
      `10648 passed, 85 skipped` 로 **초록**이었고 그 85 안에 들어 있었다.
      → *"모든 PDF 꼬리말이 두부"* 를 고친 PR 이 **그 회귀를 막는 그물을 꺼 놓은 채**
      들어갈 뻔했다. 다음에 누가 `font=` 를 떼도 CI 는 초록이었을 것이다.
      ★**내 로컬이 초록이었던 이유는 내가 검증하려고 `pypdf` 를 손수 설치했기 때문**이다
      — 같은 명령이라도 **환경이 다르면 다른 게이트**다(§32).

    지금은 `requirements.txt`·`requirements.oracle.txt` 에 `pypdf` 를 넣어 CI 에서도 돈다.
    이 함수 안의 `importorskip` 은 **그것이 다시 빠졌을 때의 2중 방어**다 —
    내용 락만 skip 되고 **배선 락은 계속 산다.**
    """
    from io import BytesIO

    pypdf = pytest.importorskip("pypdf", reason="PDF 본문 검증에 필요")
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
        found = tofu_counts(t)
        assert not found, f"꼬리말이 두부로 렌더됐다: {found}"

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


class Test두부프로브:
    """★프로브 자신을 잠근다 — **아무것도 못 세는 헬퍼**면 위 단언이 공허해진다."""

    def test_후보를_실제로_센다(self) -> None:
        assert tofu_counts("정상 텍스트") == {}
        assert tofu_counts("아■야") == {"■": 1}
        # ★한 글자만 보면 놓치는 경우 — 이 테스트의 존재 이유
        assert tofu_counts("아□야") == {"□": 1}, "■ 이외의 두부를 놓친다"
        assert tofu_counts("\ufffd") == {"\ufffd": 1}

    def test_후보_목록이_비어있지_않다(self) -> None:
        """목록이 비면 `tofu_counts` 가 **항상 {} 를 반환**해 모든 검사가 통과한다."""
        assert len(TOFU_GLYPHS) >= 4
        assert "■" in TOFU_GLYPHS, "실측으로 확인된 글자가 목록에 없다"


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
