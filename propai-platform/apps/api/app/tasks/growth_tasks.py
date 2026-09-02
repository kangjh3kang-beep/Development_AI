"""자가성장 엔진 — 텔레메트리 적재 Celery 태스크(설계서 §4).

⚠️ Phase 1 정본은 main.py 의 인프로세스 flush 루프(_growth_flush_loop)다.
    같은 프로세스의 capture_service in-memory deque 를 드레인해 platform_events
    로 배치 INSERT 한다.

    이 Celery 경로는 별도 Celery 워커 프로세스에서 도는데, capture_service 의
    큐가 프로세스-로컬(모듈 전역 deque)이라 API 프로세스가 쌓은 이벤트가
    워커에는 보이지 않는다 → 현재 Celery 경로는 사실상 무동작이다.
    향후 큐를 Redis 등 공유 큐로 전환하면 이 태스크가 실질 활성화된다.
    (코드는 그대로 두되 오해를 막기 위해 역할을 명시.)

flush_growth_events: in-memory 큐(capture_service)의 이벤트를 platform_events
로 배치 INSERT 한다. Celery Beat 가 5초 주기로 호출(celery_app.py 등록).

Celery 워커는 동기 컨텍스트이므로 `run_async_batch` 로 async flush_batch 를 구동한다.
DB 는 새 AsyncSession 1개를 열어 사용(요청 세션과 무관). best-effort: 어떤
예외도 워커를 죽이지 않는다.
"""

from __future__ import annotations

import logging

from app.tasks._async_batch import run_async_batch

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Celery 앱을 지연 임포트한다(rate_tasks 선례)."""
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


async def _flush_async() -> int:
    """큐를 platform_events 에 비운다. 적재 건수 반환.

    ★**배수 사본이 여기 하나 더 있었다**(독립 적대 렌즈 실측 2026-08-29). 상한이
      리터럴 `500` 으로 굳어 `_FLUSH_LIMIT` 과 따로 놀았고, 청크 상한 `20` 도 따로였다.
      그래서 *"배수 로직은 `drain_until_empty` 하나뿐"* 이라고 적은 주석이 **거짓**이었다
      — 셋이었다. 사본이 갈리면 **하나가 낡는데 아무도 모른다.**
    → 공용 헬퍼로 위임한다. 상한은 그 안에서 상수에서 파생된다.
    """
    from app.services.growth import capture_service
    from apps.api.database.session import AsyncSessionLocal

    return await capture_service.drain_until_empty(AsyncSessionLocal)


def flush_growth_events() -> dict:
    """큐 → platform_events 배치 적재. Beat 5초 주기.

    반환: {"flushed": N}. 동기 진입점(Celery 워커)에서 `run_async_batch` 로 구동(루프 종료 전 커넥션 정리).
    """

    try:
        flushed = run_async_batch(lambda: _flush_async())
    except Exception as e:  # noqa: BLE001
        logger.warning("flush_growth_events 실패: %s", str(e)[:160])
        return {"flushed": 0, "error": str(e)[:160]}

    if flushed:
        logger.info("growth 이벤트 적재 %d건", flushed)
    return {"flushed": flushed}


# ── 분석 배치(Phase 2, 설계서 §5.1) ─────────────────────────────────────────
# flush 와 달리 analyze 는 DB(platform_events)를 읽어 인사이트를 산출하므로
# 별도 Celery 워커에서도 정상 동작한다(프로세스-로컬 큐에 의존하지 않음).

async def _analyze_async(window_hours: int = 1) -> int:
    """직전 window_hours 시간을 분석해 platform_insights 를 생성한다."""
    from app.services.growth import analyzer
    from apps.api.database.session import AsyncSessionLocal

    w0, w1 = analyzer.default_window(hours=window_hours)
    async with AsyncSessionLocal() as session:
        insights = await analyzer.analyze_window(session, w0, w1)
    return len(insights)


def analyze_growth(window_hours: int = 1) -> dict:
    """platform_events → platform_insights 분석 배치. Beat hourly/daily 호출.

    반환: {"insights": N}. 동기 진입점(Celery 워커)에서 `run_async_batch` 로 구동(루프 종료 전 커넥션 정리).
    best-effort: 어떤 예외도 워커를 죽이지 않는다.
    """

    try:
        n = run_async_batch(lambda: _analyze_async(window_hours))
    except Exception as e:  # noqa: BLE001
        logger.warning("analyze_growth 실패: %s", str(e)[:160])
        return {"insights": 0, "error": str(e)[:160]}

    if n:
        logger.info("growth 인사이트 %d건 생성", n)
    return {"insights": n}


# ── 자가치유 평가 배치(Phase 3, 설계서 §6.1) ────────────────────────────────
# healing_rules.evaluate 가 open 인사이트/이벤트를 보고 heal 액션을 결정·실행한다.
# analyze 와 동일하게 DB(platform_insights/platform_events)를 읽으므로 별도 Celery
# 워커에서도 정상 동작(프로세스-로컬 큐 비의존). 각 액션 실행은 best-effort 예외격리.

async def _heal_async() -> dict:
    """1회 heal 평가 사이클을 새 AsyncSession 으로 구동한다."""
    from app.services.growth import healing_rules
    from apps.api.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await healing_rules.evaluate(session)


def evaluate_healing() -> dict:
    """heal 평가 배치(healing_rules → heal_actions). Beat 10분 주기 호출.

    반환: healing_rules.evaluate 요약 dict. 동기 진입점에서 `run_async_batch` 구동.
    best-effort: 어떤 예외도 워커를 죽이지 않는다.
    """

    try:
        result = run_async_batch(lambda: _heal_async())
    except Exception as e:  # noqa: BLE001
        logger.warning("evaluate_healing 실패: %s", str(e)[:160])
        return {"executed": 0, "error": str(e)[:160]}

    if result.get("executed") or result.get("escalated"):
        logger.info("growth heal: 실행 %d / 차단 %d / 에스컬레이션 %d",
                    result.get("executed", 0), result.get("blocked", 0),
                    result.get("escalated", 0))
    return result


# ── L1 자가수정 평가 배치(Phase 4, 설계서 §6.2) ─────────────────────────────
# feature_flags.evaluate 가 open 인사이트/이벤트를 보고 L1 자동수정(임계보정·피처
# 토글·프롬프트 A/B 채택)을 결정·실행한다. heal 과 동일하게 DB 를 읽으므로 별도
# Celery 워커에서도 정상 동작(프로세스-로컬 큐 비의존). 가드(캡·쿨다운)·롤백·감사는
# healing_rules/platform_settings 를 재사용하므로 안전.

async def _correct_async() -> dict:
    """1회 L1 자가수정 평가 사이클을 새 AsyncSession 으로 구동한다."""
    from app.services.growth import feature_flags
    from apps.api.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await feature_flags.evaluate(session)


def evaluate_correction() -> dict:
    """L1 자가수정 평가 배치(feature_flags.evaluate). Beat 주기 호출(analyze 후속).

    반환: feature_flags.evaluate 요약 dict. 동기 진입점에서 `run_async_batch` 구동.
    best-effort: 어떤 예외도 워커를 죽이지 않는다.
    """

    try:
        result = run_async_batch(lambda: _correct_async())
    except Exception as e:  # noqa: BLE001
        logger.warning("evaluate_correction 실패: %s", str(e)[:160])
        return {"applied": 0, "error": str(e)[:160]}

    if result.get("applied"):
        logger.info("growth L1 자가수정: 적용 %d / 차단 %d",
                    result.get("applied", 0), result.get("blocked", 0))
    return result


# ── L2 개선제안 생성 배치(Phase 4, 설계서 §6.3) ─────────────────────────────
# improvement_agent.generate_proposals 가 propose_pr critical 인사이트 → 진단+패치
# 제안 아티팩트를 생성·저장한다(코드 자동변경 없음, 제안만). 이어서 growth_pr_task 가
# GH_TOKEN 있을 때만 Draft PR 을 생성(없으면 아티팩트만 보존 = graceful). 둘 다 best-effort.

async def _improve_async() -> dict:
    """1회 L2 제안 생성 + PR봇 처리를 새 AsyncSession 으로 구동한다."""
    from app.services.growth import improvement_agent
    from apps.api.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        gen = await improvement_agent.generate_proposals(session)
    # PR봇은 별도 진입점(GH_TOKEN 가드·동기 subprocess) — 같은 사이클에서 이어 호출.
    try:
        from app.tasks.growth_pr_task import _run_async as _pr_run
        pr = await _pr_run()
    except Exception:  # noqa: BLE001
        pr = {"processed": 0}
    return {"generated": gen, "pr_bot": pr}


def evaluate_improvement() -> dict:
    """L2 개선제안 배치(improvement_agent + PR봇). Beat 일배치 후속.

    반환: {"generated": {...}, "pr_bot": {...}}. best-effort.
    """

    try:
        result = run_async_batch(lambda: _improve_async())
    except Exception as e:  # noqa: BLE001
        logger.warning("evaluate_improvement 실패: %s", str(e)[:160])
        return {"generated": {}, "error": str(e)[:160]}

    gen = result.get("generated") or {}
    if gen.get("proposed"):
        logger.info("growth L2: 제안 %d건 생성", gen.get("proposed", 0))
    return result


async def _retention_async() -> dict:
    from app.core.database import async_session_factory
    from app.services.growth.insight_retention import supersede_stale_insights

    async with async_session_factory() as session:
        return await supersede_stale_insights(session)


def cleanup_insights() -> dict:
    """승계된 옛 인사이트를 `superseded` 로 전이(정리 배치).

    ★왜 필요했나(라이브 실측 2026-08-26): `platform_insights` 에 **정리 경로가 없어서**
      `open` 3,127 / `acknowledged` 16 이 됐고, `latency_regression` 만 30일 초과가
      1,212건이었다. 화면의 「열린 인사이트」가 **재고**를 세니 오늘 볼 것이 묻힌다.

    반환: `{"scanned_types": int, "superseded": int, "by_type": {...}}`. best-effort.
    """
    try:
        result = run_async_batch(lambda: _retention_async())
    except Exception as e:  # noqa: BLE001
        # ★★실패 로그를 성공과 **같은 접두**(`growth 정리:`)로 낸다(2026-08-27 독립 리뷰 H4).
        #   종전엔 `cleanup_insights 실패` 라, 계획서가 선언한 라이브 프로브
        #   `docker logs … | grep 'growth 정리'` 에 **안 걸렸다** — 즉 *"배치가 터졌다"* 와
        #   *"beat 가 아예 안 돌았다"* 가 운영자에게 **똑같이 보였다.**
        #   이 서비스는 `RuntimeError` 로 *"조용한 0건 금지"* 를 선언해 두었는데,
        #   호출자가 그것을 `{"superseded": 0}` 으로 되돌리고 있었다.
        logger.error("growth 정리: **실패** — %s", str(e)[:200])
        return {"status": "failed", "superseded": 0, "error": str(e)[:200]}
    # ★0건일 때도 로그를 남긴다 — 배치가 안 돈 것과 정리할 게 없는 것은 다른 사실이다.
    logger.info("growth 정리: %s 승계 전이 %d건 %s",
                result.get("status", "ok"), result.get("superseded", 0),
                result.get("by_type") or "{}")
    return result


# Celery 태스크 등록(앱이 있을 때만; 미설치 환경에서도 함수는 직접 호출 가능).
_celery = _get_celery_app()
if _celery is not None:
    flush_growth_events = _celery.task(
        name="app.tasks.growth_tasks.flush_growth_events"
    )(flush_growth_events)
    analyze_growth = _celery.task(
        name="app.tasks.growth_tasks.analyze_growth"
    )(analyze_growth)
    evaluate_healing = _celery.task(
        name="app.tasks.growth_tasks.evaluate_healing"
    )(evaluate_healing)
    evaluate_correction = _celery.task(
        name="app.tasks.growth_tasks.evaluate_correction"
    )(evaluate_correction)
    evaluate_improvement = _celery.task(
        name="app.tasks.growth_tasks.evaluate_improvement"
    )(evaluate_improvement)
    cleanup_insights = _celery.task(
        name="app.tasks.growth_tasks.cleanup_insights"
    )(cleanup_insights)
