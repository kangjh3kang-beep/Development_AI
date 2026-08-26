"""성장루프 계기판 프로브 — 낡은 생산자 재발 감시.
★대조군은 **같은 술어 구조**를 태워야 한다. DB 연결만 확인하는 대조군은
  문자열 리터럴이 깨졌을 때 0을 '깨끗함'으로 읽게 만든다(실제로 그럴 뻔했다)."""
import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

from datetime import datetime, timezone
STOP = datetime(2026, 8, 24, 23, 0, 37, tzinfo=timezone.utc)

async def main():
    async with AsyncSessionLocal() as s:
        now = (await s.execute(text("select now()"))).scalar()
        # ① 같은 술어로 **타입 전체**를 센다 = 진짜 양성 대조군(리터럴이 깨지면 여기가 0)
        ctrl = (await s.execute(text(
            "select count(*) from platform_insights "
            "where insight_type = 'latency_regression' "
            "  and created_at > now() - interval '24 hours'"))).scalar()
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
        builds = (await s.execute(text(
            "select coalesce(metrics_json->>'producer_build_id', '(표식없음)') AS b, count(*) "
            "from platform_insights where created_at >= :cut group by 1 order by 2 desc"),
            {"cut": STOP})).all()
        bs = ",".join("%s=%s" % (b, c) for b, c in builds) or "(행없음)"
        print("PROBE now=%s ctrl_type_total=%s impossible_post=%s impossible_pre=%s "
              "engine_alive=%s builds=%s"
              % (now.strftime("%Y-%m-%d %H:%M"), ctrl, post, pre, alive, bs))

asyncio.run(main())
