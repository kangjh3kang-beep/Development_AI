"""감정평가 **4방법을 전부 목록에 남긴다** — 적용 못 한 것은 사유와 함께.

## 왜 (2026-09-07 사용자 신고)

화면 부제는 *"4방법(공시지가기준·거래사례·원가·수익환원)"* 이라 주장하는데 라이브
응답의 `methods` 는 **1개**였다. 성립한 방법만 넣었기 때문이다. 사용자는
«4방법이라더니 왜 하나뿐인가 · 나머지는 왜 안 됐나»를 알 길이 없었다.

★「감정평가에 관한 규칙」 §12 는 **주된 방법 + 다른 방법 검토**를 요구한다.
  «검토했고 이런 이유로 안 썼다»가 **산출물에 남아야** 검토한 것이다.

## ★기존 판단을 뒤집지 않았다

이 저장소는 *"토지 층화 통계는 **참고값**이다. 채택 단가에 넣지 않았다 … 값만 주면
「내 땅 시세」로 오독한다(개별 필지 위치 미반영)"* 를 **명문으로** 갖고 있고 그 판단은
옳다 — 층화 통계는 **지역요인까지만** 반영된 값이고 개별요인 보정 전이다.
→ **승격이 아니라 등재**다. `applicable=false` + 사유 + 참고값.
"""

from __future__ import annotations

from app.services.land_intelligence.desk_appraisal_service import _assemble_methods

_PUB = {"method": "공시지가 기준 추정", "unit_price": 3_057_000}


def _names(ms: list[dict]) -> list[str]:
    return [m["method"] for m in ms]


def test_네_방법이_모두_목록에_남는다() -> None:
    ms = _assemble_methods(_PUB, None, None, None,
                           land_stats=None, comparable_skip_note="사유")
    assert len(ms) == 4, f"방법이 {len(ms)}개다 — 화면은 4방법이라 말한다: {_names(ms)}"
    joined = " ".join(_names(ms))
    for kw in ("공시지가", "거래사례", "원가", "수익환원"):
        assert kw in joined, f"{kw} 방법이 목록에 없다: {_names(ms)}"


def test_적용_못한_방법은_사유가_비지_않는다() -> None:
    """★무음 폐기 금지 — 사유 없는 미적용은 «조용히 사라진 것»과 같다."""
    ms = _assemble_methods(_PUB, None, None, None,
                           land_stats=None, comparable_skip_note="반경 내 위치 확인 거래 없음")
    for m in ms:
        if not m["applicable"]:
            assert m.get("why_not"), f"{m['method']} 이 사유 없이 미적용이다"
            assert len(str(m["why_not"]).strip()) >= 10, m


def test_적용된_방법은_사유가_없다() -> None:
    """★위양성 축 — 모든 항목에 사유를 다는 구현을 막는다(두 모집단이 갈려야 한다)."""
    ms = _assemble_methods(_PUB, None, None, None,
                           land_stats=None, comparable_skip_note="사유")
    applied = [m for m in ms if m["applicable"]]
    assert applied, "적용된 방법이 하나도 없다 — 픽스처가 두 모집단을 안 가른다"
    for m in applied:
        assert m.get("why_not") is None, f"{m['method']} 은 적용됐는데 미적용 사유가 있다"


def test_참고값은_실려도_채택이_아님을_말한다() -> None:
    """★핵심 — 값만 주면 「내 땅 시세」로 오독한다(저장소가 기록한 그 위험)."""
    ms = _assemble_methods(_PUB, None, None, None,
                           land_stats={"unit_price_per_sqm": 3_855_297},
                           comparable_skip_note="사유")
    cmp_m = next(m for m in ms if "거래사례" in m["method"])
    assert cmp_m["applicable"] is False
    assert cmp_m["reference_unit_price"] == 3_855_297, "참고값이 있는데 버렸다"
    note = cmp_m["reference_note"] or ""
    assert "개별 필지 위치가 반영되지 않" in note, note
    assert "채택 단가에 쓰지 않습니다" in note, note


def test_참고값이_없으면_지어내지_않는다() -> None:
    """★위양성 축 — 없는 값을 0이나 빈 문구로 채우지 않는다."""
    ms = _assemble_methods(_PUB, None, None, None,
                           land_stats=None, comparable_skip_note="사유")
    cmp_m = next(m for m in ms if "거래사례" in m["method"])
    assert cmp_m["reference_unit_price"] is None
    assert cmp_m["reference_note"] is None


def test_성립한_거래사례가_있으면_그것이_적용된다() -> None:
    """★두 모집단 — 성립/미성립이 **다른 결과**를 내야 한다."""
    cmp_ok = {"method": "실거래 비교 추정", "unit_price": 4_000_000}
    ms = _assemble_methods(_PUB, cmp_ok, None, None,
                           land_stats=None, comparable_skip_note="쓰이면 안 됨")
    applied = [m for m in ms if m["applicable"]]
    assert len(applied) == 2, _names(ms)
    assert any(m["unit_price"] == 4_000_000 for m in applied)


# ── W7 물건표시 정합 ──────────────────────────────────────────────────────────

def test_라이브_조합이_확인대상으로_잡힌다() -> None:
    """★라이브 실측 조합 — 지목 답 · 용도지역 일반상업 · 이용상황 업무용."""
    from app.services.land_intelligence.desk_appraisal_service import _subject_consistency
    # ★★독립 리뷰 적발(HIGH-5) — 종전 픽스처는 `usage` 라는 **프로덕션이 만들지 않는
    #   키**를 먹여 초록이었다. 생산자(`desk_appraisal_service:298`)는
    #   **`land_use_situation`** 으로 넣는다. 「사유가 도달하는가」만 재고
    #   **「그 사유가 발생하는가」를 안 쟀다.**
    #   → **프로덕션 shape** 로 먹인다.
    r = _subject_consistency({"land_category": "답", "zone_type": "일반상업지역",
                              "land_use_situation": "업무용"})
    assert r["ok"] is False
    assert len(r["conflicts"]) == 2, r["conflicts"]
    fields = " ".join(c["field_a"] + c["field_b"] for c in r["conflicts"])
    assert "지목 답" in fields and "일반상업지역" in fields and "업무용" in fields


def test_정합한_조합은_통과한다() -> None:
    """★위양성 축 — 이게 없으면 «항상 conflict» 인 구현이 만점을 받는다."""
    from app.services.land_intelligence.desk_appraisal_service import _subject_consistency
    r = _subject_consistency({"land_category": "대", "zone_type": "일반상업지역",
                              "land_use_situation": "업무용"})
    assert r["ok"] is True and r["conflicts"] == []
    # 농지에 농지 이용도 정합.
    r2 = _subject_consistency({"land_category": "답", "zone_type": "농림지역",
                               "land_use_situation": "답"})
    assert r2["ok"] is True, r2["conflicts"]


def test_값이_없으면_판정하지_않는다() -> None:
    """★빈 값끼리 매칭하지 않는다 — 「모름」을 「정합」으로 표현하지 않게."""
    from app.services.land_intelligence.desk_appraisal_service import _subject_consistency
    for sub in ({}, {"land_category": "답"}, {"zone_type": "일반상업지역"}, None):
        r = _subject_consistency(sub)
        assert r["conflicts"] == [], f"정보가 없는데 충돌을 신고했다: {sub} → {r}"


def test_생산자_키를_실제로_읽는다() -> None:
    """★배선 락 — 합성 키가 아니라 **생산자가 쓰는 키**로 발화하는지.

    독립 리뷰가 «이 규칙은 프로덕션에서 발화할 수 없다»를 실증했다. 그 재발을 막는다.
    """
    from app.services.land_intelligence.desk_appraisal_service import _subject_consistency
    prod = _subject_consistency({"land_category": "답", "zone_type": "일반상업지역",
                                 "land_use_situation": "업무용"})
    assert len(prod["conflicts"]) == 2, (
        f"생산자 키(`land_use_situation`)로 이용상황 규칙이 발화하지 않는다: {prod}")


def test_같은_값은_충돌이_아니다() -> None:
    """★독립 리뷰 적발(MEDIUM-10) — `도로 ↔ 도로` 가 «다르다»고 신고됐다."""
    from app.services.land_intelligence.desk_appraisal_service import _subject_consistency
    for j in ("도로", "구거", "유지", "하천", "제방", "임야"):
        r = _subject_consistency({"land_category": j, "land_use_situation": j})
        assert r["conflicts"] == [], f"{j} 가 자기 자신과 충돌한다: {r['conflicts']}"


def test_지목_판정이_파생형이다() -> None:
    """★독립 리뷰 적발(MEDIUM-11) — 10개 손 목록이라 잡종지 등 17종이 빠져 있었다."""
    from app.services.land_intelligence.desk_appraisal_service import _subject_consistency
    for j in ("잡종지", "공장용지", "창고용지", "학교용지", "주차장", "종교용지", "묘지"):
        r = _subject_consistency({"land_category": j, "zone_type": "일반상업지역"})
        assert r["conflicts"], f"「대」가 아닌 지목 {j} 가 목록에서 빠졌다(손 목록이 상한이다)"
    # 위양성 축 — 「대」는 충돌이 아니다.
    assert _subject_consistency({"land_category": "대", "zone_type": "일반상업지역"})["conflicts"] == []


def test_판정이_아니라_확인요청임을_근거가_말한다() -> None:
    """★이 판정의 **법적 근거는 미확인**이다 — 결론처럼 읽히면 안 된다."""
    from app.services.land_intelligence.desk_appraisal_service import _subject_consistency
    r = _subject_consistency({"land_category": "답", "zone_type": "일반상업지역"})
    assert "법적 근거 미확인" in r["basis"], r["basis"]
    assert "확인 요청" in r["basis"], r["basis"]


# ── HIGH-4 PDF 어댑터 ─────────────────────────────────────────────────────────

def test_PDF_가_미적용_사유를_싣는다() -> None:
    """★독립 리뷰 적발(HIGH-4) — 은행 제출 산출물에서 **사유가 통째로 사라졌다.**

    W5 의 명분이 *"«검토했고 이런 이유로 안 썼다»가 **산출물에 남아야** 검토한 것"* 인데,
    정작 PDF 어댑터가 `applicable`/`why_not` 을 안 읽어 **빈 3행**이 나갔다.
    이 저장소가 반복해 데인 «사유를 버렸다» 형태.
    """
    from app.services.report.render.appraisal_adapter import _method_basis
    applied = _method_basis({"applicable": True, "rationale": "공시지가 × 시점 × 개별요인"})
    assert "공시지가" in applied
    skipped = _method_basis({"applicable": False, "why_not": "인근 거래사례 없음",
                             "reference_unit_price": 3_855_297,
                             "reference_note": "개별 필지 위치 미반영 · 채택 아님"})
    assert "인근 거래사례 없음" in skipped, "미적용 사유가 PDF 에 안 실린다"
    assert "3,855,297" in skipped and "채택 아님" in skipped, skipped
    # ★위양성 축 — 사유가 아예 없으면 빈칸이 아니라 그 사실을 말한다.
    assert "사유 미기재" in _method_basis({"applicable": False})


def test_PDF_표가_그_함수를_실제로_부른다() -> None:
    """★배선 락 — 함수만 태우면 «표가 그것을 쓰는가»는 안 잠긴다(변이 SURVIVED 실증).

    ★AST 로 호출을 센다 — 소스 문자열은 주석에 뚫린다.
    """
    import ast
    from pathlib import Path as _P

    import app.services.report.render.appraisal_adapter as A

    tree = ast.parse(_P(A.__file__).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_method_basis"]
    assert calls, (
        "`_method_basis` 를 부르는 곳이 0건 — 함수는 있는데 표가 안 쓴다. "
        "미적용 사유가 PDF 에서 다시 사라진다")
    # ★그 호출이 **산정방법 표** 안에 있어야 한다(다른 데서 부르면 의미 없다).
    src = _P(A.__file__).read_text(encoding="utf-8")
    idx = src.index("산정방법별 추정")
    assert "_method_basis" in src[idx:idx + 900], "산정방법 표가 사유를 안 쓴다"


def test_채택_산정방법이_적용된_것만_센다() -> None:
    """★독립 리뷰 적발(HIGH-4) — 다필지 총괄표가 «4방법 다 썼다»고 **거짓 진술**했다."""
    from app.services.report.render.appraisal_adapter import _adopted_method
    label = _adopted_method({"methods": [
        {"method": "공시지가 기준 추정", "applicable": True},
        {"method": "거래사례비교법", "applicable": False},
        {"method": "원가법(건물)", "applicable": False},
        {"method": "수익환원법", "applicable": False},
    ]})
    assert label == "공시지가 기준 추정", f"미적용 방법까지 채택으로 적었다: {label}"
    # ★위양성 축 — 둘 다 적용이면 둘 다 적는다.
    both = _adopted_method({"methods": [
        {"method": "공시지가 기준 추정", "applicable": True},
        {"method": "실거래 비교 추정", "applicable": True},
    ]})
    assert "공시지가" in both and "실거래" in both, both
