"""지연 **버스트** 프로브 — 계기판이 못 보던 것을 본다.

## 왜 (2026-08-27 실측)

하루에 최소 **5회**, ~10분짜리 지연 버스트가 났다. 최대 **69,503ms**
(`/api/v1/zoning/parcel-boundaries` @07:05Z). **두 세션이 라이브로 그걸 못 봤다** —
우연히 로그인을 시도한 시각(08:06~08:13Z)에만 알아챘고, 그보다 **1시간 이르고 훨씬 심한**
07:05 버스트는 아무도 안 보고 지나갔다.

★**`/health` 폴링으로는 구조적으로 못 잡는다.** `/health` 는 **그 순간**만 말한다 —
지나간 버스트를 되짚을 수 없다. `platform_events` 는 **사후 판정이 된다.**

## 무엇으로 판정하는가 — ★**동시성**

한 라우트만 느린 것과 **여러 라우트가 같은 5분에 동시에** 느린 것은 다른 사실이다.
후자는 **공통 경로**(DB·풀러·네트워크)를 가리킨다. 실측된 버스트는 전부 후자였다:

    07:05Z  history 19396 · parcel-boundaries **69503** · me 19227 · projects 20248 · status 2369
    08:50Z  parcel-boundaries 18323 · me 298 · projects 2107 · login 8760

그래서 이 프로브는 버스트를 세는 데 그치지 않고 **몇 개 라우트가 동시에 걸렸는지**로
`multi_route` / `single_route` 를 가른다.
"""

import asyncio

#: 버킷 크기(분). 실측 버스트가 ~10분이라 그보다 작아야 경계에서 안 뭉갠다.
BUCKET_MIN = 5

#: 이 p95(ms)를 넘는 버킷만 버스트 후보. 정상 라우트도 수백~수천 ms 가 나오므로
#: 그보다 확실히 위. ★단 `/api/v1/analysis/comprehensive` 처럼 **정상적으로 163초**
#: 걸리는 장기작업이 있어, 이 값만으로 「장애」라 부르지 않는다(아래 동시성 판정 참조).
BURST_P95_MS = 5000

#: 버킷당 최소 표본 — 1~2건짜리 우연을 버스트라 부르지 않는다.
BURST_MIN_N = 3

#: 이 수 이상의 **서로 다른 라우트**가 같은 버킷에 걸리면 공통 경로 의심.
MULTI_ROUTE_MIN = 3


def classify_buckets(rows):
    """(bucket, route, n, p95) 목록 → 버킷별 판정.

    반환: [(bucket, route_count, max_p95, kind)] — `kind` 는
    `multi_route`(공통 경로 의심) 또는 `single_route`(그 라우트 자체 문제일 수 있음).

    ★**순수 함수다** — DB 없이 태울 수 있다. 판정 규칙을 락이 직접 검증하게 하려는 것이며,
      기존 `growth_stale_producer_probe.is_stale_stack` 과 같은 구조다.
    """
    by_bucket: dict = {}
    for bucket, route, _n, p95 in rows:
        slot = by_bucket.setdefault(bucket, {"routes": set(), "max_p95": 0})
        slot["routes"].add(route)
        slot["max_p95"] = max(slot["max_p95"], p95)
    out = []
    for bucket in sorted(by_bucket):
        slot = by_bucket[bucket]
        count = len(slot["routes"])
        kind = "multi_route" if count >= MULTI_ROUTE_MIN else "single_route"
        out.append((bucket, count, slot["max_p95"], kind))
    return out


async def main(hours: int = 6):
    # ★DB 임포트는 함수 안에서 — 락이 `classify_buckets` 만 가져갈 때
    #   app 패키지·드라이버가 없어도 임포트가 성공해야 한다(형제 프로브와 같은 규율).
    from sqlalchemy import text

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        now = (await s.execute(text("select now()"))).scalar()
        params = {"hrs": hours, "p95": BURST_P95_MS, "minn": BURST_MIN_N,
                  "bmin": BUCKET_MIN}
        # ★양성 대조군을 **같은 술어**로 먼저 센다 — 이게 0 이면 「버스트 0」은
        #   청결이 아니라 **조회 실패**다(수집이 멈췄거나 컬럼이 바뀌었거나).
        total_buckets = (await s.execute(text(
            "SELECT count(*) FROM ("
            "  SELECT 1 FROM platform_events"
            "  WHERE event_type IN ('api_call','llm_call') AND latency_ms IS NOT NULL"
            "    AND created_at >= now() - make_interval(hours => :hrs)"
            "  GROUP BY date_trunc('hour', created_at)"
            "         + make_interval(mins => (extract(minute from created_at)::int"
            "                                  / :bmin) * :bmin),"
            "         COALESCE(route, service)"
            ") t"), params)).scalar()

        rows = (await s.execute(text(
            "SELECT date_trunc('hour', created_at)"
            "       + make_interval(mins => (extract(minute from created_at)::int"
            "                                / :bmin) * :bmin) AS b,"
            "       COALESCE(route, service) AS k, count(*) AS n,"
            "       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95 "
            "FROM platform_events "
            "WHERE event_type IN ('api_call','llm_call') AND latency_ms IS NOT NULL "
            "  AND created_at >= now() - make_interval(hours => :hrs) "
            "GROUP BY 1, 2 "
            "HAVING count(*) >= :minn "
            "   AND percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms) > :p95 "
            "ORDER BY 1, 4 DESC"), params)).all()

    judged = classify_buckets([(b, k, n, float(p)) for b, k, n, p in rows])
    multi = [j for j in judged if j[3] == "multi_route"]
    worst = max((j[2] for j in judged), default=0)
    top = ";".join(
        "%s/%dr/%dms" % (b.strftime("%H:%M"), c, int(p)) for b, c, p, _k in multi[:6]
    ) or "none"
    print("PROBE now=%s window_h=%s scanned_buckets=%s burst_buckets=%s "
          "multi_route=%s worst_p95_ms=%s top=%s"
          % (now.strftime("%Y-%m-%d %H:%M"), hours, total_buckets,
             len(judged), len(multi), int(worst), top))


if __name__ == "__main__":  # ★임포트만으로 DB 에 붙지 않는다(락이 순수 함수를 태운다)
    asyncio.run(main())
