"""토지이음 고시목록 파서 **파손 감지** (2026-08-23 · P3 후속).

★결함(실측): 파싱 0건이 곧 **"전건 확보"** 로 판정됐다.

    got = parse_gosi_rows(html)
    if not got:
        complete = True     # ← 파서가 깨져도 "완전히 확인했다"가 된다
        break

  HTTP 200 정상 + HTML 구조 변경 → 파싱 `[]` → `complete=True` →
  `find_uncovered([], …)` = [] → **"결손 없음"으로 조용히 통과**한다.
  파서 파손과 진짜 0건이 **구분되지 않고**, 오히려 "확인 완료" 신호가 붙었다.
  → 이 서비스의 존재 이유(결손 탐지)가 **조용히 0** 이 된다.

★라이브 실측(2026-08-23 · 오산 41370)으로 판별 마커를 확정했다 — 두 모집단:

    결과있음(2024~2026) : rows=50 · gvGosiDet.jsp=50 · 빈상태문구 **없음**
    진짜 0건(1990년)     : rows=0  · gvGosiDet.jsp=0  · **`조회된 데이터가 없습니다.`**

  토지이음은 빈 결과에 **명시적 신호**를 낸다. 그래서
    0건 + 신호 있음 → 진짜 0건(확신) / 0건 + 신호 없음 → **파손 의심**.

★위양성 방향이 안전하다: 문구가 바뀌면 `complete=False`(침묵)가 되지
  "결손 없음"(거짓 안심)이 되지 않는다 — 이 서비스의 설계 철학과 같은 방향이다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.legal import gosi_coverage_service as g  # noqa: E402

# ── 라이브에서 실제로 받은 형태의 축소 픽스처 ────────────────────────────────
_EMPTY_PAGE = """<html><body><table><thead><tr><th>고시일</th></tr></thead><tbody>
<tr><td colspan="4">조회된 데이터가 없습니다.</td></tr>
</tbody></table></body></html>"""

_BROKEN_PAGE = """<html><body><div class="new-layout">
<div class="row"><span>2026-01-05</span><span>제2026-1호</span></div>
</div></body></html>"""   # 구조가 바뀌어 파서가 못 읽는다 + 빈상태 신호도 없다

_ROWS_PAGE = """<html><body><table><tbody>
<tr><td>2026-01-05</td><td title="오산시 고시 제2026-1호">제2026-1호</td>
<td>[신규] 지구단위계획구역 결정</td><td>도시계획과</td>
<td><a href="/web/gs/gv/gvGosiDet.jsp?seq=12345">상세</a></td></tr>
</tbody></table></body></html>"""


def test_A_진짜_0건은_빈상태_신호로_확신한다():
    assert g.parse_gosi_rows(_EMPTY_PAGE) == []          # 전제 가드
    assert g.looks_like_empty_result(_EMPTY_PAGE) is True


def test_B_파손_페이지는_빈상태_신호가_없어_구분된다():
    """★두 모집단이 갈리는 지점 — 둘 다 rows=0 인데 판정이 달라야 한다."""
    assert g.parse_gosi_rows(_BROKEN_PAGE) == []          # 전제 가드: 똑같이 0건이다
    assert g.looks_like_empty_result(_BROKEN_PAGE) is False


def test_C_항목이_있는_페이지는_파서가_읽는다_대조군():
    rows = g.parse_gosi_rows(_ROWS_PAGE)
    assert len(rows) == 1, "파서 자체가 죽으면 위 두 테스트가 공허해진다"
    assert rows[0]["date"] == "2026-01-05"
    assert rows[0]["seq"] == "12345"


@pytest.mark.asyncio
async def test_D_파손이면_complete_False_로_침묵한다(monkeypatch):
    """★핵심 배선: 파손 시 '전건 확보'라고 말하면 결손 탐지가 조용히 0이 된다."""
    class _Resp:
        status_code = 200
        content = _BROKEN_PAGE.encode("euc-kr", "replace")

        def raise_for_status(self):
            return None

    class _Client:
        async def get(self, url, params=None):
            return _Resp()

        async def aclose(self):
            return None

    rows, complete = await g.fetch_recent_gosi("41370", "20240101", "20260823", client=_Client())
    assert rows == []
    assert complete is False, "파손인데 '전건 확보'로 나갔다 — 거짓 안심"


@pytest.mark.asyncio
async def test_E_진짜_0건이면_complete_True_무회귀(monkeypatch):
    """★음성 대조군: 정상 빈 결과까지 파손으로 몰면 탐지가 매번 침묵한다(위양성)."""
    class _Resp:
        status_code = 200
        content = _EMPTY_PAGE.encode("euc-kr", "replace")

        def raise_for_status(self):
            return None

    class _Client:
        async def get(self, url, params=None):
            return _Resp()

        async def aclose(self):
            return None

    rows, complete = await g.fetch_recent_gosi("41370", "19900101", "19900102", client=_Client())
    assert rows == []
    assert complete is True, "진짜 0건까지 파손 취급하면 정상 동작이 막힌다"


@pytest.mark.asyncio
async def test_F_이미_행을_읽었으면_빈_다음페이지는_파손이_아니다():
    """★위양성 잠금 — 기존 회귀망이 잡아 준 케이스.

    1페이지 50건(꽉 참) → 2페이지 빈 페이지는 **페이징 끝**이지 파손이 아니다.
    이미 행을 읽었다는 것 자체가 **파서가 작동한 증거**다.
    """
    # 1p: 행이 있는 정상 페이지 / 2p: 빈 페이지(빈상태 신호도 없음 = 파손과 같은 모양)
    seq = iter([_ROWS_PAGE, "<html><body><div>빈 페이지·빈상태 신호 없음</div></body></html>"])

    class _Resp:
        def __init__(self, html): self.content = html.encode("euc-kr", "replace")
        def raise_for_status(self): return None

    class _Client:
        async def get(self, url, params=None): return _Resp(next(seq))
        async def aclose(self): return None

    rows, complete = await g.fetch_recent_gosi("41370", "20240101", "20260823", client=_Client())
    assert len(rows) >= 1, "전제: 1페이지에서 행을 읽어야 한다"
    assert complete is True, "이미 읽은 행이 있으면 빈 다음 페이지는 정상 종료다"


#   ※로그 문자열 변이 생존은 **의도된 미잠금**이다 — 사람이 읽는 진단 메시지이지
#     계약이 아니다(문구를 잠그면 정상적인 문구 개선이 위반으로 신고된다).
# ── 파서 건강 **영속 관측** (2026-08-23) ────────────────────────────────────
#   ★#764 와 같은 패턴을 반복하지 않는다: 감지 로직만 보고 emit 을 안 보면
#     관측이 통째로 사라져도 초록이다(1차 변이에서 실제로 전부 생존했다).


@pytest.fixture
def observed(monkeypatch):
    events: list[tuple[str, dict]] = []
    from app.services.growth import capture_service

    monkeypatch.setattr(capture_service, "record_event",
                        lambda et, props=None: events.append((et, props or {})))
    return events


def _client_of(html: str):
    class _Resp:
        content = html.encode("euc-kr", "replace")

        def raise_for_status(self): return None

    class _Client:
        async def get(self, url, params=None): return _Resp()
        async def aclose(self): return None

    return _Client()


@pytest.mark.asyncio
async def test_G_파손이면_broken_True_로_영속_관측한다(observed):
    await g.fetch_recent_gosi("41370", "20240101", "20260823", client=_client_of(_BROKEN_PAGE))

    obs = [e for e in observed if e[0] == g.GOSI_PARSER_OBSERVATION_EVENT]
    assert obs, "파손을 관측하지 않으면 '언제부터 깨졌나'를 영영 못 잰다"
    et, props = obs[0]
    assert et == "gosi_parser_observation"          # 프로덕션 조회 키
    assert props["service"] == "gosi_coverage"      # analyzer 가 COALESCE(route,service) 로 읽는다
    assert props["surface"] == "api"
    assert props["payload"]["broken"] is True
    assert props["payload"]["sigungu_code"] == "41370"
    # ★진단 지표를 잠근다 — 파손 시 "페이지가 어떻게 달랐나"를 재는 값이다.
    assert props["payload"]["page_len"] > 0, "파손 페이지 크기를 안 남기면 원인 추적이 끊긴다"


@pytest.mark.asyncio
async def test_H_정상이면_broken_False_로_남는다_분모(observed):
    """★성공 경로가 없으면 '몇 번 중 몇 번 깨졌나'를 못 센다 — 분모가 사라진다."""
    await g.fetch_recent_gosi("41370", "19900101", "19900102", client=_client_of(_EMPTY_PAGE))

    obs = [e for e in observed if e[0] == g.GOSI_PARSER_OBSERVATION_EVENT]
    assert obs
    assert obs[0][1]["payload"]["broken"] is False   # ★G와 갈리는 지점
    # ★건강 지표 — 정상 경로에서 몇 건을 읽었는지가 분모의 실체다.
    assert obs[0][1]["payload"]["row_count"] == 0, "진짜 0건 조회의 row_count"


@pytest.mark.asyncio
async def test_I_F4a_자동토글_신호를_만들지_않는다(observed):
    await g.fetch_recent_gosi("41370", "20240101", "20260823", client=_client_of(_BROKEN_PAGE))

    for event_type, props in observed:
        assert event_type != "verify_result"
        assert "severity" not in props
        assert "recommended_action" not in props
