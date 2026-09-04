"""성장루프 계기판 프로브 — 낡은 생산자 재발 감시.
★대조군은 **같은 술어 구조**를 태워야 한다. DB 연결만 확인하는 대조군은
  문자열 리터럴이 깨졌을 때 0을 '깨끗함'으로 읽게 만든다(실제로 그럴 뻔했다)."""
import asyncio

from datetime import datetime, timezone
STOP = datetime(2026, 8, 24, 23, 0, 37, tzinfo=timezone.utc)

#: 서로 다른 생산자 표식이 "동시"로 볼 만큼 가까이 기록된 간격.
#: 배포 전환(블루-그린)은 초 단위라, 1분이면 승계와 병존을 가른다.
OVERLAP_WINDOW_SEC = 60


def is_stale_stack(spans):
    """잔재 스택인가 — **표식 종류 수가 아니라 시간 겹침**으로 판정한다.

    ★2026-08-26 실측 회귀: 종전 판정은 `표식 종류 > 1 → 잔재` 였다.
      그런데 STOP(2일 전) 이후 창에서는 **배포할 때마다 표식이 바뀌므로**
      두 번째 배포 이후로는 **영원히 위반**이었다. 계기판이 상시 exit 2 를
      내면 그 신호를 무시하는 습관이 생기고, 그때 진짜 잔재가 묻힌다.

    잔재 스택의 정의는 *"옛 빌드가 새 빌드와 **동시에** 쓴다"* 이다.
    승계(각자 자기 구간에만 씀)는 정상이며 배포마다 반드시 일어난다.

    spans: [(build_id, first_ts, last_ts), ...]  — 표식 있는 빌드만.
    반환: 겹치는 (a, b) 쌍의 목록. 비어 있으면 잔재 아님.
    """
    marked = [(b, f, l) for b, f, l in spans if b and b != "(표식없음)"]
    hits = []
    for i in range(len(marked)):
        for j in range(i + 1, len(marked)):
            b1, f1, l1 = marked[i]
            b2, f2, l2 = marked[j]
            # 두 구간이 OVERLAP_WINDOW_SEC 만큼 여유를 두고도 겹치는가
            latest_start = max(f1, f2)
            earliest_end = min(l1, l2)
            if (earliest_end - latest_start).total_seconds() >= -OVERLAP_WINDOW_SEC:
                hits.append((b1, b2))
    return hits



async def main():
    # ★DB 임포트는 함수 안에서 — 테스트가 `is_stale_stack` 만 가져갈 때
    #   app 패키지·드라이버가 없어도 임포트가 성공해야 한다.
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as s:
        now = (await s.execute(text("select now()"))).scalar()
        # ① 같은 술어로 **타입 전체**를 센다 = 진짜 양성 대조군(리터럴이 깨지면 여기가 0)
        ctrl = (await s.execute(text(
            "select count(*) from platform_insights "
            "where insight_type = 'latency_regression' "
            "  and created_at > now() - interval '24 hours'"))).scalar()
        # ★같은 술어를 **창 없이** 한 번 더 센다 — `ctrl` 이 0 일 때 그 이유를 가르기 위해서다.
        #   2026-09-02 실측: 술어 전체 **2,348건**(최신 08-28 17:30)인데 24h 는 **0**.
        #   즉 리터럴·스키마는 멀쩡하고 **시스템이 유휴**였다. 둘을 뭉치면 계기판이
        #   "검사기 사망(exit 3)"을 **영구히** 내고, 상시 3 은 곧 무시된다 — 이 파일의
        #   형제(`integrator_dashboard.sh`)가 `#868` 에서 이미 값을 치른 형태다.
        ctrl_all = (await s.execute(text(
            "select count(*) from platform_insights "
            "where insight_type = 'latency_regression'"))).scalar()
        # ② 그중 불가능 행(severity='info')을 정지 전후로 가른다
        post, pre = (await s.execute(text(
            "select count(*) filter (where created_at >= :cut), "
            "       count(*) filter (where created_at <  :cut) "
            "from platform_insights "
            "where insight_type = 'latency_regression' and severity = 'info' "
            "  and created_at > now() - interval '24 hours'"), {"cut": STOP})).first()
        # ③ 정지 이후 아무 인사이트라도 쓰였는가(엔진 생존)
        alive = (await s.execute(text(
            "select count(*) from platform_insights where created_at >= :cut"),
            {"cut": STOP})).scalar()
        # ④ ★★"이 단언이 참이 되는 다른 경로" 를 닫는다.
        #   `impossible_post=0` 은 **그 서명(latency_regression+info)을 가진 생산자**가
        #   없다는 뜻일 뿐이다. **다른 빌드**의 잔재 스택은 이 검사를 그냥 통과한다.
        #   → 생산자 표식(PR #826)이 붙으면 **빌드 종류 수**로 직접 센다.
        #     표식이 아직 없으면(전부 null) 그 사실을 **명시**한다 — 0 을 청결로 읽지 않게.
        #   ★판정은 **종류 수가 아니라 시간 겹침**이다(is_stale_stack 참조).
        #     구간까지 함께 가져와야 승계와 병존을 가를 수 있다.
        builds = (await s.execute(text(
            "select coalesce(metrics_json->>'producer_build_id', '(표식없음)') AS b, count(*),"
            "       min(created_at), max(created_at) "
            "from platform_insights where created_at >= :cut group by 1 order by 2 desc"),
            {"cut": STOP})).all()
        bs = ",".join("%s=%s" % (b, c) for b, c, _f, _l in builds) or "(행없음)"
        overlaps = is_stale_stack([(b, f, l) for b, _c, f, l in builds])
        ov = ";".join("%s~%s" % (a, b) for a, b in overlaps) or "none"
        print("PROBE now=%s ctrl_type_total=%s ctrl_type_alltime=%s "
              "impossible_post=%s impossible_pre=%s "
              "engine_alive=%s builds=%s overlap=%s"
              % (now.strftime("%Y-%m-%d %H:%M"), ctrl, ctrl_all, post, pre, alive, bs, ov))

if __name__ == "__main__":  # ★임포트만으로 DB 에 붙지 않는다(테스트가 순수 함수를 태운다)
    asyncio.run(main())
