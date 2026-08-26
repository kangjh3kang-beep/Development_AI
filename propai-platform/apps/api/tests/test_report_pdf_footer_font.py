"""PDF 꼬리글이 **한글을 라틴 전용 폰트로 그리고 있었다** — 전 페이지·전 보고서.

## 어떻게 발견했나

`#853` 착지 후 **라이브 API 에서 실제로 받은 PDF**(propai-v002801-a7838464, 7페이지)를
텍스트 추출해 보니 본문 한글은 정상인데 **머리/꼬리글만 네모**로 나왔다.

    ■■■■ · AI ■■■ ■■■■■   ·   ■■ ■■ (INTERNAL DRAFT)   ·   ■■■ (CONFIDENTIAL)
    (기대: 사통팔땅 · AI 부동산 인텔리전스 · 내부 초안 (INTERNAL DRAFT) · 대외비 (CONFIDENTIAL))

★**추출 아티팩트가 아니다** — 같은 추출기가 본문 한글 1,971자는 정상으로 뽑았다.
  근본은 `pdf_kit.footer_callback` 이 `T.FONT_FALLBACK`(Helvetica)로 `setFont` 하는데
  그리는 문자열이 전부 한글이라는 것이다. Helvetica 에는 한글 글리프가 없다.

## 왜 이 락이 필요한가

`footer_callback` 은 **공용 헬퍼**다. `render_report` 정본 통로를 쓰는 보고서
**13개 파일**이 전부 이 꼬리글을 쓴다 — 한 곳이 뚫리면 모든 PDF 가 뚫린다.

## ★이 락이 **못 보는** 것 / 보는 것

- 검사하는 것은 *"한글을 그릴 때 라틴 전용 폰트를 고르지 않는가"* 라는 **선택**이다.
  글리프가 실제 픽셀로 그려지는지는 보지 않는다.
- ★**폴백을 봐주지 않는다.** `register_font()` 가 CID 등록에 실패해 Helvetica 로
  폴백하면 이 락은 **빨개진다** — 이유가 무엇이든 한글을 Helvetica 로 그리면
  사용자는 네모를 본다. 폴백을 허용하면 그 순간 이 락은 원래 결함을 다시 통과시킨다.
- **표 줄바꿈·오버플로는 별개 문제**이며 여기서 다루지 않는다(인계서가 같이 적어 둔
  미측정 항목 중 하나 — 여전히 미측정).
- 종단 확증은 이 파일이 아니라 산출물로 했다: 실제 PDF 를 렌더해 꼬리글의
  네모가 **133 → 0** 이 되고 '사통팔땅'·'대외비' 가 추출되는 것을 확인했다.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.report.render import pdf_kit as K
from app.services.report.render import tokens as T


#: 한글 음절 판정
def _has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in str(text))


class _RecordingCanvas:
    """`setFont` 와 `drawString` 을 기록만 하는 캔버스 — 실제 그리기는 하지 않는다."""

    def __init__(self) -> None:
        self.current_font: str | None = None
        self.draws: list[tuple[str, str]] = []   # (font, text)

    def saveState(self) -> None: ...
    def restoreState(self) -> None: ...
    def setFillColor(self, *_a, **_k) -> None: ...

    def setFont(self, name: str, _size: float) -> None:
        self.current_font = name

    def drawString(self, _x, _y, text) -> None:
        self.draws.append((self.current_font or "", str(text)))

    drawRightString = drawString


def _run_footer() -> _RecordingCanvas:
    meta = SimpleNamespace(
        confidential=True, approval_state="DRAFT",
        doc_no="DOC-1", generated_at="2026-08-26T08:00:00",
    )
    canvas = _RecordingCanvas()
    K.footer_callback(meta)(canvas, SimpleNamespace(page=1))
    return canvas


def test_footer_actually_draws_hangul():
    """★공허 진리 가드 — 꼬리글에 한글이 없으면 아래 단언은 아무것도 안 잠근다."""
    canvas = _run_footer()
    assert canvas.draws, "꼬리글이 아무것도 그리지 않았다"
    hangul_draws = [d for d in canvas.draws if _has_hangul(d[1])]
    assert hangul_draws, f"꼬리글에 한글이 없다 — 락이 공허하다: {canvas.draws}"


def test_hangul_is_never_drawn_with_a_latin_only_font():
    """한글을 그리는 순간의 폰트가 **라틴 전용**이면 안 된다.

    ★기대값을 손으로 나열하지 않는다 — 라틴 전용 목록은 reportlab 기본 14종에서 파생한다.
    """
    LATIN_ONLY = {"Helvetica", "Helvetica-Bold", "Helvetica-Oblique",
                  "Times-Roman", "Times-Bold", "Courier", "Courier-Bold",
                  "Symbol", "ZapfDingbats"}
    assert T.FONT_FALLBACK in LATIN_ONLY, "폴백 폰트가 라틴 전용 목록에 없다 — 목록을 갱신하라"

    for font, text in _run_footer().draws:
        if _has_hangul(text):
            assert font not in LATIN_ONLY, (
                f"한글 '{text[:30]}' 를 라틴 전용 폰트 {font!r} 로 그린다 — 네모로 렌더된다"
            )


def test_latin_only_text_may_use_any_font():
    """대조군 — 이 락이 **라틴 텍스트까지 막지는 않는다**(위양성 방지)."""
    for font, text in _run_footer().draws:
        if not _has_hangul(text):
            assert font, f"폰트가 비었다: {text!r}"
