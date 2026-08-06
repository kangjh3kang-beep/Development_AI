"""MOLIT 쿼터 보호 회귀락 — 재시도 정책과 캐시 수명.

★배경(실측 2026-08-06): 토지 통계는 **30개월 창**이 필요한데(6개월로는 강남조차 동 단위가
무너진다), 30개월 × 여러 지역을 매번 조회하다 **`HTTP 429 × 60건`** 을 만났다.
그 시점엔 `retry_if_exception_type(httpx.HTTPStatusError)` 때문에 **실제 호출이 3배**였다.

속도는 문제가 아니었다(병렬 30회 0.7초). 제약은 **일일 쿼터**다.
"""

from __future__ import annotations

from datetime import datetime

import httpx


def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://apis.data.go.kr/test")
    res = httpx.Response(status, request=req)
    return httpx.HTTPStatusError("boom", request=req, response=res)


def test_quota_and_permission_errors_are_not_retried() -> None:
    """429·403 은 재시도하지 않는다 — **재시도가 상황을 악화시킨다**.

    429 는 일일 쿼터 초과라 다시 물어보면 남은 쿼터만 태우고 차단이 길어진다.
    403 도 같은 키로 재차 물어봐야 답이 달라지지 않는다.

    ★두 모집단을 가른다 — 재시도하면 **안 되는** 것과 **해야 하는** 것이 서로 다른 답을
    내야 한다(둘 다 같은 답이면 이 검사는 아무것도 잠그지 못한다).
    """
    # ★지연 import — 모듈 수준에서 끌면 prometheus 레지스트리가 중복 등록된다
    #   (기존 테스트들도 같은 관례를 쓴다).
    from apps.api.integrations.base_client import _is_retryable_http_error

    # 재시도해선 안 되는 쪽
    assert _is_retryable_http_error(_http_error(429)) is False
    assert _is_retryable_http_error(_http_error(403)) is False
    # 재시도가 실제로 도움이 되는 쪽(일시적 실패)
    assert _is_retryable_http_error(_http_error(500)) is True
    assert _is_retryable_http_error(_http_error(503)) is True
    # HTTP 오류가 아닌 것은 이 판정의 대상이 아니다
    assert _is_retryable_http_error(ValueError("nope")) is False


def test_settled_months_are_cached_longer_than_recent_ones() -> None:
    """과거 월은 오래 캐시한다 — 30개월 창을 매번 새로 받으면 쿼터가 버티지 못한다.

    ★두 모집단을 가른다 — 최근 월과 과거 월이 **서로 다른 TTL** 을 받아야 한다.
    """
    from apps.api.integrations.molit_client import _TTL_RECENT, _TTL_SETTLED, _deal_ymd_ttl

    now = datetime(2026, 8, 1)
    # 최근 구간(6개월 이내) — 지연 신고·계약 해제가 아직 반영될 수 있다
    assert _deal_ymd_ttl("202608", now=now) == _TTL_RECENT
    assert _deal_ymd_ttl("202603", now=now) == _TTL_RECENT
    assert _deal_ymd_ttl("202602", now=now) == _TTL_RECENT
    # 확정 구간(6개월 초과)
    assert _deal_ymd_ttl("202601", now=now) == _TTL_SETTLED
    assert _deal_ymd_ttl("202412", now=now) == _TTL_SETTLED
    # ★실제로 다르다 — 같으면 위 단언들이 공허해진다
    assert _TTL_SETTLED > _TTL_RECENT


def test_unparseable_month_falls_back_to_short_ttl() -> None:
    """월을 못 읽으면 **짧은 쪽**으로 간다 — 모르는 것을 오래 들고 있지 않는다."""
    from apps.api.integrations.molit_client import _TTL_RECENT, _deal_ymd_ttl

    now = datetime(2026, 8, 1)
    for bad in ("", "abcd", "2026", "202613", "20260a", None):
        assert _deal_ymd_ttl(bad, now=now) == _TTL_RECENT, bad

    # ★★`202600`(월 0)이 **월 범위 가드를 판별하는 유일한 케이스**다.
    #   `202613`(월 13)으로는 못 잡는다 — 경과가 음수(8-13=-5)라 가드가 없어도 어차피
    #   짧은 쪽으로 떨어지기 때문이다. 반면 월 0 은 경과가 8개월로 계산돼, 가드가 없으면
    #   **장기 캐시로 새어 나간다**.
    #   ★이 구멍은 `scripts/mutate_changed.py` 가 찾았다 — 내가 고른 변이 목록엔 없었다.
    assert _deal_ymd_ttl("202600", now=now) == _TTL_RECENT, (
        "월 범위 가드가 없으면 깨진 월이 장기 캐시로 새어 나간다"
    )


def test_paged_collect_actually_uses_the_tiered_ttl() -> None:
    """★TTL 함수를 만들어 놓고 **수집부가 안 쓰면** 쿼터는 그대로 탄다.

    변이 실증: `cache_ttl=_deal_ymd_ttl(deal_ymd)` 를 `cache_ttl=86400` 으로 되돌려도
    다른 검사들은 전부 통과했다 — 함수의 **동작**만 잠그고 **배선**은 비어 있었다.
    이 저장소에서 "정의는 했는데 소비처 0" 이 반복해서 나온 그 형태다.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "integrations" / "molit_client.py"
    code = "\n".join(
        ln for ln in src.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    )
    assert "cache_ttl=_deal_ymd_ttl(deal_ymd)" in code, (
        "실거래 페이지 수집이 월별 TTL 을 쓰지 않는다 — 30개월 창을 매번 새로 받게 된다"
    )
    # 종전의 고정 TTL 이 그 자리에 남아 있으면 안 된다.
    assert "cache_ttl=86400," not in code.split("_paged_collect")[-1][:2000], (
        "수집부에 고정 TTL 이 남아 있다"
    )


def test_retry_decorator_actually_uses_the_predicate() -> None:
    """★판정 함수를 만들어 놓고 **데코레이터가 안 쓰면** 아무 소용이 없다.

    이 저장소에서 "정의는 했는데 소비처가 0" 이 반복해서 나왔다(배선 층 미변이).
    소스에서 종전 형태(`retry_if_exception_type(httpx.HTTPStatusError)`)가 사라지고
    새 술어가 실제로 걸렸는지 확인한다.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "integrations" / "base_client.py"
    # ★주석·독스트링은 제외하고 **실행되는 줄**만 본다. 종전 형태를 설명하는 주석이
    #   남아 있는 것은 정상이고(왜 바꿨는지 기록), 그걸 위반으로 세면 오탐이다.
    code_lines = [
        ln for ln in src.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    ]
    text = "\n".join(code_lines)
    assert "retry=retry_if_exception(_is_retryable_http_error)" in text, (
        "재시도 술어가 데코레이터에 배선되지 않았다"
    )
    assert "retry_if_exception_type(httpx.HTTPStatusError)" not in text, (
        "종전의 '모든 HTTP 오류 재시도' 가 남아 있다 — 429 도 3회 재시도된다"
    )
