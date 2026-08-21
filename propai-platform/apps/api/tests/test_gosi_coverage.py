"""고시 **결손 탐지** — 우리 데이터가 모르는 최근 지구단위계획 결정고시를 지목한다.

【실제 사고】오산 내삼미동: 제2025-274호(2025-12-23)로 지구단위계획구역이 **신규 결정**됐는데
VWorld 에 없어 플랫폼이 자연녹지 80%를 지배 한도인 양 답했다.

【★이 파일이 잠그는 것 — 정직성이 핵심이다】
1. 신규 구역 지정 고시를 **가려낸다**(변경·경미·실효 제외)
2. `실효고시`는 결손이 **아니다** — 구역이 사라졌으니 없는 게 맞다(위양성 방지)
3. 목록이 **절단됐거나 조회 실패면 아무것도 단정하지 않는다**(거짓 안심 금지)
4. 문구는 *"확인되지 않는다"* 이지 *"틀렸다"* 가 아니다(대조는 휴리스틱)
"""

import pytest

from app.services.legal.gosi_coverage_service import (
    build_coverage_notice,
    find_uncovered,
    is_new_district_designation,
    parse_gosi_rows,
)

# ── 라이브 원문 최소 재현(2026-08-21 토지이음 오산 실응답 구조 그대로) ──────────────
_REAL_HTML = """
<table><caption>고시정보 목록으로 고시일, 고시번호, 고시제목, 담당기관 조회 정보 제공</caption>
<thead><tr><th>고시일</th><th>고시번호</th><th>[구분]고시제목</th><th>담당기관</th></tr></thead>
<tbody>
<tr class="center">
  <td class="mb">2025-12-23</td>
  <td class="left mb" title="경기도 오산시 고시 제2025-274호"> 경기도 오산시 고시 제2025-274호 </td>
  <td class="left"><a href='gvGosiDet.jsp?seq=1' title='오산(내삼미3구역) 도시관리계획(용도지구, 지구단위계획구역, 지구단위계획) 결정 및 지형도면 고시'>
    [신규] 오산(내삼미3구역) 도시관리계획(용도지구, 지구단위계획구역, 지구단위계획) 결정 및 지형도면 고시<!-- x --></a></td>
  <td class="left mb" title="경기도 오산시 도시주택국 도시정책과">경기도 오산시 도시주택국 도시정책과</td>
</tr>
<tr class="center">
  <td class="mb">2024-02-29</td>
  <td class="left mb" title="경기도 오산시 고시 제2024-40호"> 경기도 오산시 고시 제2024-40호 </td>
  <td class="left"><a href='gvGosiDet.jsp?seq=2' title='오산(내삼미2구역) …'>
    [신규] 오산(내삼미2구역) 도시관리계획(지구단위계획구역, 지구단위계획)결정 및 지형도면고시<!-- x --></a></td>
  <td class="left mb" title="경기도 오산시 도시주택국 도시정책과">경기도 오산시 도시주택국 도시정책과</td>
</tr>
<tr class="center">
  <td class="mb">2019-03-14</td>
  <td class="left mb" title="경기도 오산시 고시 제2019-35호"> 경기도 오산시 고시 제2019-35호 </td>
  <td class="left"><a href='gvGosiDet.jsp?seq=3' title='지구단위계획구역 실효고시'>
    [신규] 지구단위계획구역 실효고시<!-- x --></a></td>
  <td class="left mb" title="경기도 오산시 도시주택국 도시정책과">경기도 오산시 도시주택국 도시정책과</td>
</tr>
<tr class="center">
  <td class="mb">2026-01-30</td>
  <td class="left mb" title="경기도 오산시 고시 제2026-23호"> 경기도 오산시 고시 제2026-23호 </td>
  <td class="left"><a href='gvGosiDet.jsp?seq=4' title='오산 도시관리계획(도시계획시설:학교81호) …'>
    [변경] 오산 도시관리계획(도시계획시설:학교81호) 결정(경미한변경) 및 실시계획(변경)인가 고시<!-- x --></a></td>
  <td class="left mb" title="경기도 오산시 도시주택국 도시정책과">경기도 오산시 도시주택국 도시정책과</td>
</tr>
</tbody></table>
"""


@pytest.fixture
def rows():
    return parse_gosi_rows(_REAL_HTML)


def test_premise_fixture_holds_all_four_populations(rows):
    """전제 — 픽스처가 **네 부류를 실제로 가른다**(같은 부류만 있으면 판별이 공허하다)."""
    assert len(rows) == 4, [r["date"] for r in rows]
    titles = " ".join(r["title"] for r in rows)
    assert "[신규]" in titles and "[변경]" in titles
    assert "실효" in titles and "도시계획시설" in titles


def test_parses_date_gosino_title(rows):
    r = next(r for r in rows if r["date"] == "2025-12-23")
    assert r["gosino"] == "경기도 오산시 고시 제2025-274호"
    assert r["title"].startswith("[신규]")
    assert "지구단위계획구역" in r["title"]
    assert "도시정책과" in r["org"]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("[신규] 오산(내삼미3구역) 도시관리계획(용도지구, 지구단위계획구역, 지구단위계획) 결정 및 지형도면 고시", True),
        # ★실효 = 구역이 사라짐 → 피처가 **없는 게 맞다**(라이브에서 실제로 빠져 있었다)
        ("[신규] 지구단위계획구역 실효고시", False),
        # 경미한 변경은 결정고시관리코드를 갱신하지 않을 수 있다
        ("[신규] 오산 도시관리계획(지구단위계획구역, 지구단위계획) 결정(경미한 변경) 및 지형도면 고시", False),
        ("[변경] 오산(원동7구역) 도시관리계획(지구단위계획구역, 지구단위계획) 결정(변경)", False),
        ("[신규] 오산 도시관리계획(도시계획시설:학교81호) 결정", False),
    ],
)
def test_new_district_designation_filter(title, expected):
    assert is_new_district_designation(title) is expected


def test_finds_the_real_incident(rows):
    """★실제 사고 재현 — 2024-02-29 는 우리 데이터에 있고 2025-12-23 은 없다."""
    known = {"20240229"}          # VWorld 가 아는 날짜(라이브 실측에서 확인된 것)
    out = find_uncovered(rows, known)
    assert [r["date"] for r in out] == ["2025-12-23"], out
    assert "제2025-274호" in out[0]["gosino"]


def test_covered_gosi_is_not_reported(rows):
    """★대조군(음성) — 우리 데이터가 아는 고시는 결손이 아니다(위양성 방지)."""
    known = {"20240229", "20251223"}
    assert find_uncovered(rows, known) == []
    # ★양성 짝 — 같은 실행에서 하나를 빼면 **잡힌다**(탐지가 통째로 죽은 게 아니다).
    assert len(find_uncovered(rows, {"20240229"})) == 1


def test_expired_district_is_never_reported_as_missing(rows):
    """★★위양성 방지 — `실효고시`는 아무것도 모르는 상태에서도 결손이 아니다."""
    out = find_uncovered(rows, set())          # 아는 것이 하나도 없어도
    dates = [r["date"] for r in out]
    assert "2019-03-14" not in dates, "실효고시를 결손으로 신고했다(구역은 사라진 게 맞다)"
    # 공허 진리 가드 — 그 상태에서 **다른 것들은 실제로 잡혔는가**.
    assert "2025-12-23" in dates and "2024-02-29" in dates


def test_notice_says_unconfirmed_not_wrong(rows):
    n = build_coverage_notice(find_uncovered(rows, {"20240229"}), complete=True, checked=4,
                              sigungu_name="오산시", list_url="https://www.eum.go.kr/x")
    assert n is not None
    assert "확인되지 않는" in n["reason"], n["reason"]
    assert "틀렸" not in n["reason"] and "없습니다." not in n["reason"].split("있습니다")[0]
    assert n["applied"] is False, "값을 바꾸지 않는다는 형제 계약"
    assert n["list_url"]


def test_incomplete_listing_asserts_nothing():
    """★★절단·실패면 **아무것도 단정하지 않는다** — 거짓 안심 금지.

    이 저장소는 같은 함정을 두 번 밟았다(VWorld `size` 상한 · 이 목록의 `listSize`).
    절단된 목록으로 "결손 없음"을 말하면 안심시키는 방향으로 틀린다.
    """
    uncovered = find_uncovered(parse_gosi_rows(_REAL_HTML), {"20240229"})
    # ★양성 짝 — complete=True 면 **고지가 나온다**(로직이 죽은 게 아니다).
    assert build_coverage_notice(uncovered, complete=True, checked=4) is not None
    assert build_coverage_notice(uncovered, complete=False, checked=4) is None


def test_no_uncovered_means_no_notice(rows):
    """결손이 없으면 화면에 아무것도 붙이지 않는다(빈 배너 금지)."""
    assert build_coverage_notice([], complete=True, checked=4) is None


def test_parser_survives_empty_and_garbage():
    assert parse_gosi_rows("") == []
    assert parse_gosi_rows("<table><tr><td>깨진</td></tr></table>") == []
    # ★양성 짝 — 정상 입력에서는 실제로 파싱된다.
    assert len(parse_gosi_rows(_REAL_HTML)) == 4


# ── 진입점 — 대조 상대가 비면 **전건 위양성**이 된다(실측으로 겪은 함정) ─────────────
import asyncio


def _run(monkeypatch, *, rows, complete, known):
    """외부 경계(토지이음·VWorld)만 대역하고 `gosi_coverage_for_region` 본체를 태운다."""
    import app.services.legal.gosi_coverage_service as M

    async def fake_fetch(sgg, end, **kw):
        return rows, complete, "20240821"

    async def fake_known(sgg, bbox):
        return known

    monkeypatch.setattr(M, "fetch_recent_gosi_adaptive", fake_fetch)
    monkeypatch.setattr(M, "_vworld_known_dates", fake_known)
    M._CACHE.clear()
    return asyncio.run(M.gosi_coverage_for_region("41370", "BOX(1,2,3,4)", sigungu_name="오산시"))


def test_entrypoint_reports_the_incident(monkeypatch, rows):
    out = _run(monkeypatch, rows=rows, complete=True, known={"20240229"})
    assert out["notice"] is not None
    assert "제2025-274호" in out["notice"]["reason"]
    assert out["notice"]["window_start"] == "20240821", "확인 범위가 고지에 없다"


def test_empty_known_set_never_reports(monkeypatch, rows):
    """★★대조 상대가 비면 **모든 고시가 결손처럼 보인다** — 그 상태로 신고하면 전건 위양성.

    실측으로 겪었다: 목록 페이징이 절단됐을 때 16/16 결손이 나왔고 **전부 오탐**이었다.
    """
    out = _run(monkeypatch, rows=rows, complete=True, known=set())
    assert out["notice"] is None, "대조 상대가 0인데 결손을 신고했다"
    assert out["complete"] is False
    # ★양성 짝 — 대조 상대가 있으면 **실제로 신고한다**(탐지가 통째로 죽은 게 아니다).
    assert _run(monkeypatch, rows=rows, complete=True, known={"20240229"})["notice"] is not None


def test_incomplete_listing_never_reports(monkeypatch, rows):
    out = _run(monkeypatch, rows=rows, complete=False, known={"20240229"})
    assert out["notice"] is None
    # ★양성 짝
    assert _run(monkeypatch, rows=rows, complete=True, known={"20240229"})["notice"] is not None


def test_no_gap_means_no_notice(monkeypatch, rows):
    """음성 대조군 — 결손이 없는 시군구는 조용하다(라이브 실측: 성남시)."""
    out = _run(monkeypatch, rows=rows, complete=True, known={"20240229", "20251223"})
    assert out["notice"] is None
    assert out["known_date_count"] == 2
