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



#: 분석 상태 스냅샷이 사는 자리. ★**새 표면을 만들지 않는다** — `analyzer.py` 의
#: `ANALYSIS_STATUS_SETTING_KEY` 와 **같은 값**이다. 여기서 다시 정하면 두 곳이 갈린다.
ANALYSIS_SETTING_KEY = "growth_analysis"
#: 「돌았다」만 말하는 워터마크(TTL 없음). `state` 와 **다른 명제**라 둘 다 읽는다.
ANALYZE_WATERMARK_KEY = "growth_last_run.analyze"
#: 스케줄 스냅샷. ★`schedule.py` 의 `SCHEDULE_SNAPSHOT_KEY` 와 **같은 값**이다.
#:   잡별 «경과/주기» 를 싣는다 — 이것이 없으면 **「7일 전」이 정상인지 장애인지 못 가른다**
#:   (실측 2026-09-12: `learn` 9,471분 경과가 **정상**이었고 나는 장애로 의심했다).
SCHEDULE_SETTING_KEY = "growth_schedule"

#: 프로브가 이 필드를 **아예 안 준다**(옛 사본)는 것을 나타내는 표식.
#: ★`"idle"` 이나 `""` 로 두면 «안 재 봤다»가 «축이 없다»로 읽힌다.
ASTATE_MISSING = "(필드없음)"
#: 설정 행 자체가 없다. ★정상 동작 중에는 **매 실행이 만료를 앞으로 민다** — 그러므로
#:   행 부재는 「유휴」가 아니라 **연속 미실행**이다.
#:   ★★**횟수를 여기서 단정하지 않는다**(2026-09-12 정정). 종전엔 «TTL(180분) > 주기(60분)
#:     이므로 3회» 라고 적었는데 그 **두 수가 손으로 복사**돼 있었다 — `schedule.py` 의
#:     주기나 `analyzer.py` 의 TTL 이 바뀌면 **사용자에게 나가는 사유가 조용히 거짓**이 된다
#:     (주기 60→90 이면 180/90=2 인데 문장은 여전히 «3회» 라고 말한다).
#:     주기는 이제 스냅샷에서 **파생**하고, TTL 은 이 프로브가 읽을 수 없으므로
#:     **횟수를 말하지 않는다** — 진단 못 하는 자리에서 진단하지 않는다.
ASTATE_ABSENT = "(행없음)"


def analysis_fields(arow, watermark):
    """설정 행 → 계기판이 `PROBE` 줄에서 뽑는 **다섯 값**.

    ★**순수 함수로 꺼낸 이유**(2026-09-12 변이 실측): 이 대응이 `main()` 안에 있을 때는
      DB 가 있어야만 태울 수 있어 **어떤 테스트도 도달하지 못했다** — `isinstance` 조건을
      무력화하고 네 줄을 지워도 **전부 SURVIVED**(변이 6건). 층이 안 태워지면 «N/N CAUGHT»
      는 그 사실의 가림막이다. 형제 `analysis_status_payload`(생산자 쪽)도 같은 이유로 순수다.

    반환: `(astate, aat, aaxes, ains, alast)` — 전부 문자열/None 이며 공백이 없다
      (계기판이 `grep -oE 'astate=[^ ]+'` 로 **공백 경계**로 뽑기 때문이다 —
       `axes` 는 원본에 공백이 있어 `_` 로 바꾸지 않으면 **뒤가 통째로 잘린다**).

    ★`None` 과 «dict 가 아닌 값» 을 **같이** 부재로 보낸다 — 둘 다 "이 스냅샷으로는
      판정 못 한다" 이고, 갈라 봐야 처방이 같다.
    """
    if isinstance(arow, dict):
        astate = str(arow.get("state") or ASTATE_ABSENT)
        aat = str(arow.get("at") or "-")
        aaxes = str(arow.get("axes") or "-").replace(" ", "_")
        ains = arow.get("insights")
        if ains is None:
            ains = "-"
    else:
        astate, aat, aaxes, ains = ASTATE_ABSENT, "-", "-", "-"
    alast = str(watermark).strip('"') if watermark else "-"
    return astate, aat, aaxes, ains, alast


#: 스냅샷이 **얼마나 낡으면** 「스케줄러가 안 돈다」고 볼 것인가.
#: ★이 값은 SSOT 의 사본이 **아니다** — 틱(60초)에 대한 **프로브의 관용치**다.
#:   그래서 손복사 금지 규율에 걸리지 않는다. 10분이면 틱 10회 연속 실패를 뜻한다.
SCHEDULE_STALE_MIN = 10


def schedule_fields(srow):
    """스케줄 스냅샷 행 → 계기판이 뽑는 **세 값**.

    반환: `(sat, sjobs, soverdue)` — 전부 문자열이고 **공백이 없다**
      (형제 `analysis_fields` 와 같은 이유: 계기판이 `[^ ]+` 로 공백 경계에서 뽑는다).
    """
    if isinstance(srow, dict):
        sat = str(srow.get("at") or "-")
        sjobs = str(srow.get("jobs") or "-").replace(" ", "_")
        soverdue = str(srow.get("overdue") or "-").replace(" ", "_")
    else:
        sat, sjobs, soverdue = "-", "-", "-"
    return sat, sjobs, soverdue


def schedule_verdict(sat, sjobs, soverdue, now):
    """스케줄이 건강한가 — ★**두 고장을 가른다.**

    이 함수가 있기 전에는 둘이 **같은 모양**이었다:
      ① 틱 루프는 도는데 **어떤 잡의 실행만 죽음** → 그 잡의 워터마크가 영구 지연.
         스냅샷 자신은 **신선**하다(매 틱 갱신되므로).
      ② **틱 루프 자체가 죽음** → 스냅샷도 같이 낡는다.
    ①은 종전에 **어떤 표면에도 나오지 않았다**(프론트는 ISO 문자열을 표시만 하고,
    이 프로브는 `analyze` 워터마크 하나만 읽었다).

    ★그리고 이 함수가 생긴 계기는 **내가 오독한 사건**이다(2026-09-12 13:11Z):
      `growth_last_run.learn` 9,471분 전을 보고 「6.6일째 멈췄다」고 의심했는데
      `learn` 주기가 **10080분(7일)** 이라 정상이었다. **경과만으로는 못 가른다.**

    반환: `("ok"|"obs"|"unknown", 사유)` — 형제 `analysis_verdict` 와 같은 어휘.
    """
    if sjobs == "-":
        return "unknown", (
            "스케줄 스냅샷이 없다 — 스케줄러가 도는지 **이 자리에서 못 가른다**"
            "(구버전 API 이거나 틱이 한 번도 안 돌았다)"
        )
    try:
        at = datetime.fromisoformat(str(sat).strip('"').replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "unknown", "스케줄 스냅샷의 `at` 을 읽지 못했다 — 나이를 못 재면 판정 불가"
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    age_min = int((now - at).total_seconds() // 60)
    if age_min >= SCHEDULE_STALE_MIN:
        return "obs", (
            "스케줄 스냅샷이 %d분 낡았다(관용 %d분) — **틱 루프**를 보라. "
            "잡 하나가 아니라 스케줄러 자신이 멈춘 모양이다" % (age_min, SCHEDULE_STALE_MIN)
        )
    if soverdue != "-":
        return "obs", (
            "틱은 돌고 있는데(스냅샷 %d분) **지연된 잡**이 있다: %s — "
            "그 잡의 실행 경로를 보라(경과/주기: %s)" % (age_min, soverdue, sjobs)
        )
    return "ok", "스케줄러가 돌고 모든 잡이 주기 안이다(경과/주기: %s)" % sjobs


def parse_axes(aaxes):
    """`"fal 0/0 lat 0/19"`(또는 `_` 로 이어 붙인 형태) → `[(이름, judged, total), …]`.

    ★계기판은 공백 경계로 뽑으므로 `analysis_fields` 가 공백을 `_` 로 바꾼다.
      **두 표기를 다 받는다** — 생산자 원본과 프로브 출력이 같은 함수로 읽혀야 한다.
    ★해석 못 한 조각은 **버리지 않고 무시하되**, 하나도 못 읽으면 **빈 목록**을 돌려준다
      (호출부가 「모른다」로 갈 수 있게 — 0 으로 뭉치지 않는다).
    """
    toks = str(aaxes or "").replace("_", " ").split()
    out = []
    i = 0
    while i < len(toks) - 1:
        name, pair = toks[i], toks[i + 1]
        if "/" in pair:
            a, _, b = pair.partition("/")
            try:
                out.append((name, int(a), int(b)))
                i += 2
                continue
            except ValueError:
                pass
        i += 1
    return out


#: ★**상수를 하나 만들었다가 지웠다**(기계 변이가 잡았다 · 2026-09-12).
#:   `ASTATE_NO_INPUT = "(입력없음)"` 를 선언해 놓고 **어디서도 쓰지 않았다** —
#:   줄을 통째로 지워도 **락 전부 초록**이었다(변이 SURVIVED).
#:   ***정의만 하고 소비처 0*** — 내가 이번 주에 남의 PR 에서 지적한 바로 그 형태다.
#:   구분은 `analysis_verdict` 가 **판정으로** 하고, 그 판정을 락이 태운다.
#:   상태 어휘를 새로 내보내려면 **소비처(계기판 표시·기계 판독)를 같은 커밋에** 만들어야 한다.


def analysis_verdict(astate, insights_24h, aaxes=None, analyze_period_min=None):
    """계기판 ③ 이 인사이트 24h 창 **0** 을 만났을 때 무엇이라 불러야 하는가.

    ★**순수 함수다** — DB 없이 태울 수 있고, 셸이 규칙을 다시 구현하지 않는다
      (형제 `is_stale_stack`·`latency_burst_probe.classify_buckets` 와 같은 구조).
      산문으로 주면 받는 쪽마다 다르게 구현한다 — 이 저장소가 이미 값을 치른 형태다.

    반환: `("ok"|"obs"|"unknown", 사람이 읽을 사유)`
      ok      — 설명된 상태. 「이상 없음」이라 불러도 되는 유일한 갈래
      obs     — 위반은 아니나 **이상 없음도 아니다**(계기판 exit 4)
      unknown — **안 재 봤다**. 0 과 절대 뭉치지 않는다

    ★네 모집단이 **서로 다른 값**을 내야 한다. 하나로 접으면 이 함수는 장식이다.

    ★**변이 생존을 여기 적는다**(2026-09-12 · 점수 부풀리기 방지): 아래 사유 **문구**를
      바꾸는 변이는 생존한다. **구멍이 아니다** — 계약은 `kind` 와 «각 모집단이 자기만의
      사유를 낸다» 이지 그 문장의 철자가 아니다. 문구를 단언하면 다듬을 때마다 깨지는
      취약한 락이 된다(§G-30). 대신 **다섯 입력이 다섯 개의 서로 다른 사유**를 내는지를
      락이 단언하고, 그것이 `astate == ASTATE_MISSING` 분기의 무력화를 잡는다.
    """
    if astate == ASTATE_MISSING:
        return "unknown", "프로브에 분석상태 필드가 없다 — 컨테이너의 프로브가 옛 사본이다"
    if astate == ASTATE_ABSENT:
        # ★행 부재를 「유휴」로 읽지 않는다 — 정상 동작 중엔 매 실행이 만료를 앞으로 민다.
        #   ★**횟수는 말하지 않는다**: 그러려면 TTL 이 필요한데 이 프로브는 못 읽는다.
        #     종전 문장의 `180`·`60` 은 **손으로 복사한 상수**였다(위 `ASTATE_ABSENT` 주석 참조).
        per = "" if not analyze_period_min else " · analyze 주기 %s분" % analyze_period_min
        return "obs", (
            "분석상태 행이 없다 — 만료됐다는 뜻이고 정상 동작 중엔 그럴 수 없다"
            "(연속 미실행%s · 횟수는 TTL 을 못 읽어 확정 불가)" % per
        )
    if astate == "starved":
        # ★★`starved` 는 **두 사실을 덮는다**(독립 리뷰 2026-09-12 · 라이브 실측이 그 증거):
        #     axes = "fal 0/0 lat 0/0 pay 0/1 qua 0/0"
        #       `0/1` → 표본이 쌓이는데 하한 미달  → **기다리면 된다**
        #       `0/0` → **입력이 아예 없다**        → **고쳐야 나온다**(수집 경로)
        #   생산자 판정식은 `judged_total > 0` 만 보므로 둘을 **같은 `starved`** 로 낸다.
        #   그런데 가르는 값(`total`)은 **이미 payload 에 실려 있다** — 안 읽었을 뿐이다.
        #   ***이 파일이 고치려던 결함(답이 이미 있는데 판정이 안 읽는다)이 한 층 안쪽에 있었다.***
        axes = parse_axes(aaxes)
        if not axes:
            # 축을 하나도 못 읽었다 = 이 스냅샷으로는 가를 수 없다. 0 으로 뭉치지 않는다.
            return "unknown", "판정한 축이 없는데 축 요약을 읽지 못했다 — 유휴인지 입력 0인지 가를 수 없다"
        with_input = [a for a in axes if a[2] > 0]
        if not with_input:
            # ★모든 축이 `total == 0` — 「표본 부족」이 아니라 **입력이 안 들어온다**.
            return "obs", (
                "판정한 축이 없고 **모든 축의 입력이 0**이다(%s) — 표본 부족이 아니라 수집 경로를 보라"
                % " ".join("%s %d/%d" % a for a in axes)
            )
        # ★사유에서 **원인 단정을 뺀다.** 종전 문구 「모든 축이 표본 하한 미달 — 고장이 아니다」는
        #   `0/0` 축이 있는 순간 **거짓**이고, 「고장이 아니다」는 재지 않은 진단이다.
        return "ok", (
            "판정한 축 0 — 입력이 있는 축 %d개는 하한 미달, 입력이 0인 축 %d개(%s)"
            % (len(with_input), len(axes) - len(with_input),
               " ".join("%s %d/%d" % a for a in axes))
        )
    if astate == "idle":
        return "obs", "커버리지 축 자체가 없다 — 분석기가 축을 하나도 못 돌렸다"
    if astate == "judged":
        if int(insights_24h or 0) > 0:
            return "ok", "판정했고 인사이트도 있다"
        # ★판정했다면서 24h 창이 비었다 = 두 관측이 **모순**이다. 침묵으로 두지 않는다.
        return "obs", "판정했다는데 24h 창이 비었다 — 발행·보존(supersede) 경로를 보라"
    return "unknown", "분석상태 값을 해석하지 못했다: %s" % (astate,)


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
        # ⑤ ★**분석기가 왜 아무 말도 안 하는지**를 같은 프로브가 가져온다.
        #   계기판은 여기서 «판정 불가» 를 찍고 있었는데, 그 답은 `analyzer.py` 가
        #   **이미 발행하고 있었다**(`growth_analysis` 설정키 · 프론트는 읽는다).
        #   빠진 것은 기능이 아니라 **이 레인의 소비처**였다.
        #   ★두 키를 **둘 다** 읽는다 — 워터마크는 「돌았다」를, 스냅샷은 「됐다/굶었다」를
        #     말한다. 다른 명제다.
        arow = (await s.execute(text(
            "select value from platform_settings where key = :k "
            "  and (ttl_expires_at is null or ttl_expires_at > now())"),
            {"k": ANALYSIS_SETTING_KEY})).scalar()
        wm = (await s.execute(text(
            "select value from platform_settings where key = :k"),
            {"k": ANALYZE_WATERMARK_KEY})).scalar()
        srow = (await s.execute(text(
            "select value from platform_settings where key = :k "
            "  and (ttl_expires_at is null or ttl_expires_at > now())"),
            {"k": SCHEDULE_SETTING_KEY})).scalar()
        astate, aat, aaxes, ains, alast = analysis_fields(arow, wm)
        sat, sjobs, soverdue = schedule_fields(srow)
        skind, swhy = schedule_verdict(sat, sjobs, soverdue, now)
        # ★**변이 생존 기록**(2026-09-12 · 2차 감사): 아래 `now.strftime` 의 **표시 형식**과
        #   워터마크 질의의 **문자열**을 바꾸는 변이는 생존한다. 구멍이 아니다 —
        #   전자는 사람이 읽는 표시이고(계약이 아니다), 후자는 «TTL 필터가 **없어야** 한다»
        #   쪽이 계약이라 락이 그 축을 대조군으로 단언한다
        #   (`test_status_query_filters_expired_rows`). 키 이름은 생산자에서 파생해 따로 잠갔다.
        print("PROBE now=%s ctrl_type_total=%s ctrl_type_alltime=%s "
              "impossible_post=%s impossible_pre=%s "
              "engine_alive=%s builds=%s overlap=%s "
              "astate=%s aat=%s aaxes=%s ains=%s alast=%s "
              "sat=%s sjobs=%s soverdue=%s skind=%s"
              % (now.strftime("%Y-%m-%d %H:%M"), ctrl, ctrl_all, post, pre, alive, bs, ov,
                 astate, aat, aaxes, ains, alast,
                 sat, sjobs, soverdue, skind))
        # ★사유는 사람이 읽는 줄로 따로 낸다(PROBE 줄은 공백 경계로 파싱되므로 못 싣는다).
        print("PROBE_SCHEDULE %s | %s" % (skind, swhy))

if __name__ == "__main__":  # ★임포트만으로 DB 에 붙지 않는다(테스트가 순수 함수를 태운다)
    asyncio.run(main())
