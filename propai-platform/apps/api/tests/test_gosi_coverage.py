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


# ── ★페이징 층 — **HTTP(외부 경계)만** 대역하고 본체를 태운다 ──────────────────────
#   변이감사가 잡았다: 위 진입점 테스트가 `fetch_recent_gosi_adaptive` 를 **통째로 대역**해
#   페이징·창축소 층이 **무잠금**이었다(생존 20건이 전부 그 구간).
#   이 저장소가 반복해 데인 형태다 — 대역은 항상 외부 경계로 내린다.
#   ★그리고 하필 이 층이 **절단 함정**이 사는 곳이다(잘린 목록으로 "결손 없음"을 말하면
#     안심시키는 방향으로 틀린다 — 실측으로 두 번 겪었다).

import httpx as _httpx


def _page_html(n_rows: int, start_day: int = 1) -> str:
    body = "".join(
        f"""<tr class="center"><td class="mb">2026-01-{(start_day + i) % 28 + 1:02d}</td>
        <td class="left mb" title="경기도 오산시 고시 제2026-{start_day + i}호">x</td>
        <td class="left"><a title='t'>[변경] 도시관리계획 결정</a></td>
        <td class="left mb" title="기관">기관</td></tr>"""
        for i in range(n_rows)
    )
    return f"<table><tbody>{body}</tbody></table>"


def _client_serving(pages: list[str], *, fail: bool = False) -> _httpx.AsyncClient:
    """`pageNo` 에 따라 정해진 페이지를 돌려주는 가짜 전송층(외부 경계만 대역)."""
    calls: list[int] = []

    def handler(request: _httpx.Request) -> _httpx.Response:
        if fail:
            raise _httpx.ConnectError("boom")
        page = int(dict(request.url.params).get("pageNo", "1"))
        calls.append(page)
        html_text = pages[page - 1] if page <= len(pages) else "<table></table>"
        return _httpx.Response(200, content=html_text.encode("euc-kr", "replace"))

    c = _httpx.AsyncClient(transport=_httpx.MockTransport(handler))
    c._calls = calls  # type: ignore[attr-defined]
    return c


def test_pagination_collects_every_page():
    """★2페이지에 걸친 목록을 **전건** 모은다(마지막이 50 미만이면 종료)."""
    from app.services.legal.gosi_coverage_service import fetch_recent_gosi

    c = _client_serving([_page_html(50), _page_html(7, start_day=60)])
    rows, complete = asyncio.run(fetch_recent_gosi("41370", "20250101", "20260101", client=c))
    assert complete is True
    assert len(rows) == 57, len(rows)
    assert c._calls == [1, 2]  # type: ignore[attr-defined]


def test_hitting_the_page_cap_is_reported_incomplete():
    """★★상한에 걸리면 **전건확보 실패**로 보고한다 — 잘린 목록으로 안심시키지 않는다."""
    from app.services.legal.gosi_coverage_service import _MAX_PAGES, fetch_recent_gosi

    c = _client_serving([_page_html(50) for _ in range(_MAX_PAGES + 3)])
    rows, complete = asyncio.run(fetch_recent_gosi("41370", "20250101", "20260101", client=c))
    assert complete is False, "상한 도달인데 전건확보라고 보고했다"
    assert len(rows) == 50 * _MAX_PAGES
    # ★양성 짝 — 같은 경로가 짧은 목록에서는 **전건확보 True** 를 낸다.
    c2 = _client_serving([_page_html(3)])
    assert asyncio.run(fetch_recent_gosi("41370", "20250101", "20260101", client=c2))[1] is True


def test_network_failure_is_reported_incomplete():
    """조회 실패는 **침묵하지 않고** 불완전으로 표기한다(예외를 삼켜 빈 목록을 내지 않는다)."""
    from app.services.legal.gosi_coverage_service import fetch_recent_gosi

    rows, complete = asyncio.run(
        fetch_recent_gosi("41370", "20250101", "20260101", client=_client_serving([], fail=True))
    )
    assert complete is False and rows == []


def test_adaptive_window_narrows_until_complete(monkeypatch):
    """★창 축소 — 넓은 창이 상한에 걸리면 **좁혀서 전건을 확보**한다.

    실측: 화성시가 2.5년 창 600건으로 상한에 걸려 **통째로 침묵**했다. 좁히면 탐지 범위만
    줄고 거짓 주장은 생기지 않는다(우리는 "결손 없음"을 말하지 않는다).
    """
    import app.services.legal.gosi_coverage_service as M

    seen: list[str] = []

    async def fake_fetch(sgg, start, end, *, client=None):
        seen.append(start)
        # 첫(가장 넓은) 창만 상한에 걸린 것으로, 그 다음부터는 전건확보.
        return ([{"date": "2026-01-01"}], len(seen) > 1)

    monkeypatch.setattr(M, "fetch_recent_gosi", fake_fetch)
    rows, complete, window_start = asyncio.run(
        M.fetch_recent_gosi_adaptive("41370", "20260821")
    )
    assert complete is True
    assert len(seen) >= 2, "좁히지 않고 포기했다"
    # ★좁아진 창이 **실제로 더 늦게 시작**해야 한다(같으면 축소가 일어나지 않은 것).
    assert window_start > seen[0], (window_start, seen)


def test_adaptive_gives_up_honestly(monkeypatch):
    """모든 창이 불완전이면 **빈 결과 + 전건확보 False** — 여기서 결손을 말할 수 없다."""
    import app.services.legal.gosi_coverage_service as M

    async def always_incomplete(sgg, start, end, *, client=None):
        return ([{"date": "2026-01-01"}], False)

    monkeypatch.setattr(M, "fetch_recent_gosi", always_incomplete)
    rows, complete, window_start = asyncio.run(M.fetch_recent_gosi_adaptive("41370", "20260821"))
    assert rows == [] and complete is False and window_start == ""


def test_query_params_are_actually_sent():
    """★★어느 시군구·어느 기간을 물었는지 **실제로 보내는지** 잠근다.

    변이감사가 잡았다: `selSggCd`/`startdt` 를 지워도 통과했다 — MockTransport 가 파라미터를
    안 보기 때문이다. 이게 틀리면 **다른 시군구의 고시를 조용히 조회**하고, 결과는 그럴듯하다
    (이 저장소가 반복해 데인 '조용히 틀린 값' 형태).
    """
    from app.services.legal.gosi_coverage_service import _PAGE_SIZE, fetch_recent_gosi

    seen: dict[str, str] = {}

    def handler(request: _httpx.Request) -> _httpx.Response:
        seen.update(dict(request.url.params))
        return _httpx.Response(200, content=_page_html(2).encode("euc-kr", "replace"))

    c = _httpx.AsyncClient(transport=_httpx.MockTransport(handler))
    asyncio.run(fetch_recent_gosi("41370", "20250101", "20260101", client=c))
    assert seen.get("selSggCd") == "41370", seen
    assert seen.get("startdt") == "20250101" and seen.get("enddt") == "20260101", seen
    assert seen.get("listSize") == str(_PAGE_SIZE)


def test_empty_page_terminates_as_complete():
    """빈 페이지를 만나면 **전건확보로 종료**한다(무한 루프·상한 소진 방지)."""
    from app.services.legal.gosi_coverage_service import fetch_recent_gosi

    c = _client_serving([_page_html(50), "<table></table>"])
    rows, complete = asyncio.run(fetch_recent_gosi("41370", "20250101", "20260101", client=c))
    assert complete is True and len(rows) == 50


def test_non_date_rows_are_rejected():
    """★첫 칸이 날짜가 아닌 행(헤더·안내문 등)은 버린다 — 안 버리면 쓰레기가 고시로 샌다."""
    from app.services.legal.gosi_coverage_service import parse_gosi_rows

    junk = """<table><tbody><tr>
      <td class="mb">등록된 고시가 없습니다</td><td title="x">x</td>
      <td class="left"><a title='t'>t</a></td><td title="기관">기관</td></tr></tbody></table>"""
    assert parse_gosi_rows(junk) == []
    # ★양성 짝 — 같은 파서가 정상 행은 실제로 읽는다(파서가 죽은 게 아니다).
    assert len(parse_gosi_rows(_page_html(3))) == 3


@pytest.mark.parametrize(
    ("ntfc", "expected"),
    [
        ("41370NTC202512230001", "20251223"),
        ("41110NTC201105160042", "20110516"),
        ("41370NTC000000000270", None),      # 파손값(실측: 화성에 존재)
        ("", None),
    ],
)
def test_ntfc_date_extraction(ntfc, expected):
    """VWorld 관리코드에서 대조 키를 뽑는다.

    ★이 8자리를 '고시일'이라 부르지 않는다 — VWorld 공식 속성표에 날짜 필드가 없고
      이것은 결정고시**관리코드**다. 여기서는 **대조 키**로만 쓴다.
    """
    from app.services.legal.gosi_coverage_service import NTFC_DATE_RE

    m = NTFC_DATE_RE.search(ntfc)
    assert (m.group(0) if m else None) == expected


# ── ★고시 원문 수치(P5) — 인계서가 "사용자 입력 전제"라 못 박은 전제를 반증했다 ──────
#   실측(2026-08-21, 오산 지구단위계획 고시): 6건 중 **5건에서 텍스트 추출 성공**,
#   원동7구역 `용적률 200%`(사고 당시 사용자가 신고한 "실제 계획 200%"와 일치) ·
#   양산2구역 `200%·180%`. 다운로드 열쇠는 **EUC-KR 폼 인코딩**이었다.
#   ★그러나 정작 사고 고시(내삼미3구역)는 첨부가 스캔본+도면뿐이라 **수치를 못 뽑는다** —
#     그래서 이 기능은 "있으면 더 나은 것"이지 항상 되는 것이 아니다.

def test_parses_multiple_far_candidates():
    """★값을 **하나로 고르지 않는다** — 한 구역 안에 여럿이다(실측: 양산2구역 200%·180%).

    P4 에서 배운 것과 같다: 순서가 의미를 뜻하지 않으므로 임의 선택은 오답이 된다.
    """
    from app.services.legal.gosi_coverage_service import parse_far_bcr_candidates

    text = "가. 용적률 ∘200% 이하\n나. 용적률 ∘180% 이하\n다. 건폐율 ⦁ 60% 이하"
    out = parse_far_bcr_candidates(text)
    assert out["far_pct"] == [200, 180], out
    assert out["bcr_pct"] == [60], out


def test_far_candidates_reject_out_of_range():
    """★법정 최대(중심상업 1500%)를 넘는 값은 오독이다 — 범위로 거른다."""
    from app.services.legal.gosi_coverage_service import parse_far_bcr_candidates

    out = parse_far_bcr_candidates("용적률 9999% · 용적률 200% · 건폐율 300%")
    assert out["far_pct"] == [200], out
    assert out["bcr_pct"] == [], out
    # ★양성 짝 — 범위 안 값은 실제로 통과한다(필터가 전부를 죽인 게 아니다).
    assert parse_far_bcr_candidates("건폐율 60%")["bcr_pct"] == [60]


def test_limits_note_says_candidate_not_applied():
    """★'적용값'이라 말하지 않는다 — 후보이고 확인이 필요하다."""
    from app.services.legal.gosi_coverage_service import _limits_note

    n = _limits_note({"available": True, "far_pct": [200, 180], "bcr_pct": [60]})
    assert n and "후보" in n
    assert "200%" in n and "180%" in n
    # 값이 여럿이면 **획지마다 다르다**는 사실을 말한다.
    assert "획지마다 값이 다릅니다" in n, n
    assert "확인하십시오" in n


def test_limits_note_single_value_does_not_claim_multiple():
    """★대조군 — 값이 하나면 '획지마다 다르다' 문구를 만들지 않는다(위양성 방지)."""
    from app.services.legal.gosi_coverage_service import _limits_note

    n = _limits_note({"available": True, "far_pct": [200], "bcr_pct": []})
    assert n and "200%" in n
    assert "획지마다" not in n
    # ★양성 짝 — 여럿이면 실제로 붙는다.
    assert "획지마다" in (_limits_note({"available": True, "far_pct": [200, 180], "bcr_pct": []}) or "")


def test_limits_note_is_silent_when_unavailable():
    """★★스캔본·추출 실패면 **아무 수치도 말하지 않는다**.

    라이브 실측: 내삼미2구역은 경기도보 **스캔본**(텍스트 13자)이고,
    사고 고시 내삼미3구역은 첨부가 **지형도면**뿐이라 수치가 없다.
    여기서 빈 후보를 '수치 없음'으로 내면 **없는 것과 못 읽은 것이 뭉개진다**.
    """
    from app.services.legal.gosi_coverage_service import _limits_note

    assert _limits_note(None) is None
    assert _limits_note({"available": False, "reason": "scanned_image", "far_pct": [], "bcr_pct": []}) is None
    assert _limits_note({"available": True, "far_pct": [], "bcr_pct": []}) is None
    # ★양성 짝 — 있으면 실제로 낸다.
    assert _limits_note({"available": True, "far_pct": [200], "bcr_pct": []}) is not None


def test_list_parser_captures_seq_for_detail_lookup():
    """★목록에서 `seq` 를 실어야 상세(첨부 PDF)로 갈 수 있다 — 없으면 P5 가 죽는다."""
    from app.services.legal.gosi_coverage_service import parse_gosi_rows

    rows = parse_gosi_rows(_REAL_HTML)
    assert all(r["seq"] for r in rows), [r["seq"] for r in rows]
    assert rows[0]["seq"] == "1"


# ── ★`fetch_gosi_limits` 오케스트레이션 — HTTP·PDF(외부 경계)만 대역하고 본체를 태운다 ──
#   변이감사가 잡았다: 순수 함수만 테스트해서 **다운로드·선택·판정이 통째로 무잠금**이었다.
#   이 세션에서 **세 번째** 같은 실수다.

_DET_HTML = """<html><body>
 <a href="javascript:download('/web/FileDownload.do', '/2025/12/23/620000/625885/고시문(원동7구역).pdf')">고시문</a>
 <a href="javascript:download('/web/FileDownload.do', '/2025/12/23/620000/625885/지형도면.jpg')">도면</a>
</body></html>"""


def _limits_client(pdf_bodies: dict[str, bytes], *, det: str = _DET_HTML):
    """상세는 HTML, 다운로드는 지정한 바이트를 돌려주는 가짜 전송층."""
    posts: list[dict[str, str]] = []

    def handler(request: _httpx.Request) -> _httpx.Response:
        if "gvGosiDet" in str(request.url):
            return _httpx.Response(200, content=det.encode("euc-kr", "replace"))
        raw = request.content.decode("euc-kr", "replace")
        posts.append({"raw": raw})
        for name, body in pdf_bodies.items():
            if name in raw:
                return _httpx.Response(200, content=body)
        return _httpx.Response(200, content="<script>alert('첨부파일이 없습니다.');</script>".encode("euc-kr"))

    c = _httpx.AsyncClient(transport=_httpx.MockTransport(handler))
    c._posts = posts  # type: ignore[attr-defined]
    return c


def test_download_body_is_euckr_encoded(monkeypatch):
    """★★EUC-KR 폼 인코딩 — **이 기능의 열쇠다**.

    UTF-8 로 보내면 세션·쿠키·Referer 가 다 맞아도 `alert('첨부파일이 없습니다.')` 만 온다.
    실측으로 이것 하나 때문에 막혀 있었다. 지워도 조용히 '수치 없음'이 되므로 반드시 잠근다.
    """
    import app.services.legal.gosi_coverage_service as M

    # ★본문 길이가 `_MIN_TEXT_CHARS` 를 넘어야 '스캔본'으로 분류되지 않는다
    #   (짧은 스텁을 썼다가 이 가드에 걸렸다 — 가드가 제대로 작동한다는 방증).
    monkeypatch.setattr(M, "_pdf_text",
                        lambda content, seq="": "용적률 ∘200% 이하\n" + "본문 " * 300)
    # '고시문' 의 EUC-KR 퍼센트 인코딩 — UTF-8 이었다면 이 키가 안 맞는다.
    c = _limits_client({"%B0%ED%BD%C3%B9%AE": b"%PDF-fake"})
    out = asyncio.run(M.fetch_gosi_limits("625885", client=c))
    assert out["available"] is True, out
    assert out["far_pct"] == [200]
    raw = c._posts[0]["raw"]  # type: ignore[attr-defined]
    # ★UTF-8 이었다면 '고시문' 이 %EA%B3%A0... 로 나간다.
    assert "%EA%B3%A0" not in raw, f"UTF-8 로 인코딩됐다: {raw[:80]}"
    assert "gosi=Y" in raw and "seq=625885" in raw


def test_scanned_pdf_reports_scanned_image(monkeypatch):
    """★스캔본은 **수치를 주장하지 않는다**(실측: 경기도보 스캔 텍스트 13자)."""
    import app.services.legal.gosi_coverage_service as M

    monkeypatch.setattr(M, "_pdf_text", lambda content, seq="": "  \n 1 \n")
    out = asyncio.run(M.fetch_gosi_limits("1", client=_limits_client({".pdf": b"%PDF-x"})))
    assert out["available"] is False and out["reason"] == "scanned_image"
    assert out["far_pct"] == [] and out["bcr_pct"] == []


def test_text_without_numbers_is_distinguished_from_scan(monkeypatch):
    """★'못 읽었다'와 '수치가 없다'를 **가른다** — 뭉개면 진단이 불가능해진다.

    실측: 사고 고시(내삼미3구역)는 첨부가 지형도면뿐이라 텍스트는 6,345자인데 수치가 없다.
    """
    import app.services.legal.gosi_coverage_service as M

    monkeypatch.setattr(M, "_pdf_text", lambda content, seq="": "지형도면 " * 400)
    out = asyncio.run(M.fetch_gosi_limits("1", client=_limits_client({".pdf": b"%PDF-x"})))
    assert out["available"] is False and out["reason"] == "no_numbers_in_text"
    # ★양성 짝 — 같은 경로가 수치 있는 텍스트에서는 available=True 를 낸다.
    monkeypatch.setattr(M, "_pdf_text", lambda content, seq="": "용적률 200%" + " x" * 400)
    assert asyncio.run(M.fetch_gosi_limits("1", client=_limits_client({".pdf": b"%PDF-x"})))["available"] is True


def test_non_pdf_attachment_is_skipped(monkeypatch):
    """`.jpg` 첨부는 대상이 아니다 — PDF 만 받는다(불필요한 대용량 다운로드 방지)."""
    import app.services.legal.gosi_coverage_service as M

    det = """<a href="javascript:download('/web/FileDownload.do', '/x/도면.jpg')">도면</a>"""
    out = asyncio.run(M.fetch_gosi_limits("1", client=_limits_client({}, det=det)))
    assert out["available"] is False and out["reason"] == "pdf_attachment_absent"


def test_download_failure_is_reported(monkeypatch):
    """다운로드가 PDF 를 못 주면 **정직하게 실패**로 낸다(빈 수치를 '없음'으로 내지 않는다)."""
    import app.services.legal.gosi_coverage_service as M

    out = asyncio.run(M.fetch_gosi_limits("1", client=_limits_client({})))  # 항상 alert HTML
    assert out["available"] is False and out["reason"] == "download_failed"


def test_picks_the_pdf_with_most_text(monkeypatch):
    """★첨부가 여럿이면 **텍스트가 가장 많은 것**을 고른다(스캔본 대신 고시문)."""
    import app.services.legal.gosi_coverage_service as M

    det = ("""<a href="javascript:download('/web/FileDownload.do', '/x/scan.pdf')">a</a>"""
           """<a href="javascript:download('/web/FileDownload.do', '/x/real.pdf')">b</a>""")
    texts = {"scan": "짧다", "real": "용적률 200% 이하 " + "본문 " * 300}
    monkeypatch.setattr(M, "_pdf_text",
                        lambda content, seq="": texts["scan" if content == b"%PDF-s" else "real"])
    c = _limits_client({"scan.pdf": b"%PDF-s", "real.pdf": b"%PDF-r"}, det=det)
    out = asyncio.run(M.fetch_gosi_limits("1", client=c))
    assert out["available"] is True and out["far_pct"] == [200]
    assert out["source_file"] == "real.pdf", out


# ── ★수치가 **고지까지 흐르는가**(소비처 배선) ─────────────────────────────────────
#   변이가 잡았다: 진입점 테스트가 `limits` 를 한 번도 태우지 않아 배선이 무잠금이었다.
#   이 저장소의 반복 결함('정의만 하고 소비처 0')이 여기서 재발할 뻔했다.

def _run_with_limits(monkeypatch, *, rows, known, limits):
    import app.services.legal.gosi_coverage_service as M

    async def fake_fetch(sgg, end, **kw):
        return rows, True, "20240821"

    async def fake_known(sgg, bbox):
        return known

    async def fake_limits(seq, **kw):
        return limits

    monkeypatch.setattr(M, "fetch_recent_gosi_adaptive", fake_fetch)
    monkeypatch.setattr(M, "_vworld_known_dates", fake_known)
    monkeypatch.setattr(M, "fetch_gosi_limits", fake_limits)
    M._CACHE.clear()
    return asyncio.run(M.gosi_coverage_for_region("41370", "BOX(1,2,3,4)", sigungu_name="오산시"))


def test_limits_reach_the_notice(monkeypatch, rows):
    """★읽은 수치가 **화면 계약까지** 도달한다 — 배선이 끊기면 사용자는 영영 못 본다."""
    out = _run_with_limits(
        monkeypatch, rows=rows, known={"20240229"},
        limits={"available": True, "far_pct": [200], "bcr_pct": [60]},
    )
    assert out["notice"] is not None
    assert out["notice"]["limits_note"], "수치가 고지에 실리지 않았다(배선 끊김)"
    assert "200%" in out["notice"]["limits_note"]
    assert "후보" in out["notice"]["limits_note"]


def test_unavailable_limits_leave_the_notice_intact(monkeypatch, rows):
    """★수치를 못 읽어도 **결손 고지 자체는 나간다** — 수치는 부가물이지 전제가 아니다.

    실측: 정작 사고 고시(내삼미3구역)가 이 경우다(첨부가 스캔본+도면뿐).
    여기서 고지까지 사라지면 P3 가 퇴행한다.
    """
    out = _run_with_limits(
        monkeypatch, rows=rows, known={"20240229"},
        limits={"available": False, "reason": "scanned_image", "far_pct": [], "bcr_pct": []},
    )
    assert out["notice"] is not None, "수치가 없다고 결손 고지까지 사라졌다"
    assert out["notice"]["limits_note"] is None
    assert "제2025-274호" in out["notice"]["reason"]
    # ★양성 짝 — 같은 실행에서 수치가 있으면 실려 나간다.
    ok = _run_with_limits(monkeypatch, rows=rows, known={"20240229"},
                          limits={"available": True, "far_pct": [200], "bcr_pct": []})
    assert ok["notice"]["limits_note"] is not None


def test_limits_not_fetched_when_no_gap(monkeypatch, rows):
    """★결손이 없으면 PDF 를 받지 않는다 — 불필요한 3~4MB 다운로드 금지."""
    import app.services.legal.gosi_coverage_service as M

    called: list[str] = []

    async def spy(seq, **kw):
        called.append(seq)
        return {"available": False, "far_pct": [], "bcr_pct": []}

    monkeypatch.setattr(M, "fetch_gosi_limits", spy)
    out = _run_with_limits(monkeypatch, rows=rows, known={"20240229", "20251223"},
                           limits={"available": False, "far_pct": [], "bcr_pct": []})
    assert out["notice"] is None
    assert called == [], f"결손이 없는데 PDF 를 받았다: {called}"
