"""자가성장 엔진 Phase 4 — L2 Draft PR 봇(설계서 §6.3).

improvement_agent 가 생성한 제안 아티팩트(platform_insights.insight_type=
'improvement_proposal') 를 읽어, **GH_TOKEN 이 있을 때만** Draft PR 을 생성한다.

흐름(GH_TOKEN 있을 때):
  1) 제안 아티팩트의 affected_files 화이트리스트 재검증(improvement_agent.is_path_allowed).
  2) 브랜치 growth/auto-fix/{insight_id} 생성.
  3) 변경 diff 커밋(★단, 이 봇은 패치를 자동 적용하지 않는다 — 제안서/진단을
     PR 본문으로 담은 **빈 변경 또는 제안 문서만** 커밋. 실제 코드 수정은 사람).
  4) `gh pr create --draft`(라벨 auto-proposed). main 직접 push 금지.

★현 환경: gh 미인증(GH_TOKEN 없음) → **PR 생성 스킵, 아티팩트만 기록**(graceful
degradation). pr_status='artifact_only' 로 갱신하고 그대로 둔다.

안전경계(절대 준수):
- 절대 자동 머지/배포/스키마 변경 금지. PR 은 항상 **Draft**.
- main·운영 브랜치 직접 push 금지(브랜치는 growth/auto-fix/* 만).
- 변경파일 화이트리스트(마이그레이션/배포/시크릿 제외) — improvement_agent 가 강제.
- 전 조치 admin_audit_log(actor='growth_engine').

best-effort: 어떤 예외도 워커를 죽이지 않는다.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

_ACTOR = "growth_engine"

# 절대 push 금지 브랜치(안전경계).
PROTECTED_BRANCHES = ("main", "master", "develop", "production")
PR_LABEL = "auto-proposed"
BRANCH_PREFIX = "growth/auto-fix/"


def _gh_available() -> bool:
    """gh CLI + GH_TOKEN 인증 가용 여부. 둘 중 하나라도 없으면 graceful skip.

    GH_TOKEN 은 secret_store(load_into_env)가 os.environ 에 오버레이하거나 CI 시크릿.
    """
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        return False
    try:
        r = subprocess.run(["gh", "--version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _get_celery_app():
    try:
        from app.tasks.celery_app import app
        return app
    except (ImportError, RuntimeError):
        return None


async def _audit(action: str, target: str | None, detail: dict[str, Any]) -> None:
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=_ACTOR, actor_role="system",
            action=f"growth.pr.{action}", target=target, detail=detail,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("PR audit 실패: %s", str(e)[:120])


async def _mark_pr_status(db, proposal_id: str, status: str,
                          extra: dict[str, Any] | None = None) -> None:
    """제안 아티팩트의 pr_status 를 갱신(jsonb merge). best-effort."""
    import json

    from sqlalchemy import text

    patch = {"pr_status": status}
    if extra:
        patch.update(extra)
    try:
        await db.execute(text(
            "UPDATE platform_insights "
            "SET metrics_json = COALESCE(metrics_json,'{}'::jsonb) || CAST(:p AS jsonb) "
            "WHERE id = :id AND insight_type = 'improvement_proposal'"
        ), {"p": json.dumps(patch, ensure_ascii=False, default=str), "id": proposal_id})
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("pr_status 갱신 실패(%s): %s", proposal_id, str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def _process_proposals(db, *, limit: int = 5) -> dict[str, Any]:
    """draft_only 상태 제안 아티팩트를 처리한다.

    GH_TOKEN 없으면 전부 'artifact_only' 로 마킹(PR 미생성). 있으면 Draft PR 생성 시도.
    반환: {"processed","pr_created","artifact_only"}.
    """
    from sqlalchemy import text

    from app.services.growth import improvement_agent

    summary = {"processed": 0, "pr_created": 0, "artifact_only": 0}

    rows = (await db.execute(text(
        "SELECT id, metrics_json FROM platform_insights "
        "WHERE insight_type='improvement_proposal' AND status='open' "
        "  AND COALESCE(metrics_json->>'pr_status','') = 'draft_only' "
        "ORDER BY created_at DESC LIMIT :lim"
    ), {"lim": limit})).fetchall()

    gh_ok = _gh_available()

    for r in rows:
        proposal_id = str(r[0])
        meta = r[1] if isinstance(r[1], dict) else {}
        files = [f for f in (meta.get("affected_files") or []) if isinstance(f, str)]
        summary["processed"] += 1

        # 화이트리스트 재검증(저장 시점 이후 정책변경 방어).
        if files and not all(improvement_agent.is_path_allowed(f) for f in files):
            await _mark_pr_status(db, proposal_id, "rejected_path")
            await _audit("rejected", proposal_id, {"reason": "path_not_allowed", "files": files})
            continue

        if not gh_ok:
            # ★graceful degradation: gh 미인증 → 아티팩트만 보존(PR 미생성).
            await _mark_pr_status(db, proposal_id, "artifact_only")
            summary["artifact_only"] += 1
            await _audit("skipped", proposal_id,
                         {"reason": "gh_unauthenticated", "note": "GH_TOKEN 없음 — 제안 아티팩트만 보존"})
            continue

        # GH_TOKEN 있을 때만: Draft PR 생성 시도(코드 자동수정 없이 제안서만 커밋).
        created = _create_draft_pr(proposal_id, meta)
        if created.get("ok"):
            await _mark_pr_status(db, proposal_id, "pr_created",
                                  {"pr_url": created.get("pr_url")})
            summary["pr_created"] += 1
            await _audit("created", proposal_id,
                         {"pr_url": created.get("pr_url"), "draft": True, "label": PR_LABEL})
        else:
            await _mark_pr_status(db, proposal_id, "pr_failed",
                                  {"error": str(created.get("error"))[:200]})
            await _audit("failed", proposal_id, {"error": str(created.get("error"))[:200]})

    return summary


def _create_draft_pr(proposal_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Draft PR 생성(gh). 안전경계: 새 브랜치만·draft·자동머지 금지.

    이 봇은 패치를 자동 적용하지 않는다 — 제안서(PROPOSAL.md)만 커밋해 사람이
    리뷰·구현하도록 한다. 실패는 graceful(error 반환).
    """
    branch = f"{BRANCH_PREFIX}{proposal_id}"
    if any(branch == b or branch.startswith(b + "/") for b in PROTECTED_BRANCHES):
        return {"ok": False, "error": "protected_branch"}

    proposal = meta.get("proposal") or {}
    body = (
        f"## 자동 생성 개선 제안 (L2, 사람 승인 필수)\n\n"
        f"- 근거 인사이트: {meta.get('source_insight_id')}\n"
        f"- confidence: {meta.get('confidence')}\n"
        f"- requires_approval: **true** (자동 머지 금지)\n\n"
        f"### 진단\n{proposal.get('diagnosis','')}\n\n"
        f"### 근본원인\n{proposal.get('root_cause','')}\n\n"
        f"### 제안 변경\n{proposal.get('proposed_change','')}\n\n"
        f"### 영향 파일\n{proposal.get('affected_files', [])}\n\n"
        f"### 리스크\n{proposal.get('risk','')}\n\n"
        f"### 테스트 제안\n{proposal.get('test_suggestion','')}\n\n"
        f"> 이 PR 은 자동 생성 Draft 입니다. 코드 변경은 사람이 구현·리뷰·머지하세요."
    )
    try:
        # gh pr create --draft. base 는 현재 기본 브랜치(gh 가 자동 판단), head 는 새 브랜치.
        # ★실제 브랜치 push 는 CI 환경의 git 자격증명에 의존. 여기서는 gh 위임.
        proc = subprocess.run(
            ["gh", "pr", "create", "--draft", "--title",
             f"[auto-proposed] 개선 제안 {proposal_id[:8]}",
             "--body", body, "--label", PR_LABEL, "--head", branch],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            return {"ok": True, "pr_url": (proc.stdout or "").strip()}
        return {"ok": False, "error": (proc.stderr or proc.stdout or "").strip()[:300]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


async def _run_async() -> dict[str, Any]:
    from apps.api.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await _process_proposals(session)


def run_pr_bot() -> dict:
    """L2 PR 봇 배치 진입점. GH_TOKEN 없으면 아티팩트만 보존(graceful).

    동기 진입점(Celery 워커)에서 asyncio.run 으로 구동. best-effort.
    """
    import asyncio

    try:
        result = asyncio.run(_run_async())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_run_async())
        finally:
            loop.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("run_pr_bot 실패: %s", str(e)[:160])
        return {"processed": 0, "error": str(e)[:160]}

    logger.info("growth L2 PR봇: 처리 %d / PR생성 %d / 아티팩트만 %d",
                result.get("processed", 0), result.get("pr_created", 0),
                result.get("artifact_only", 0))
    return result


# Celery 태스크 등록(앱이 있을 때만).
_celery = _get_celery_app()
if _celery is not None:
    run_pr_bot = _celery.task(name="app.tasks.growth_pr_task.run_pr_bot")(run_pr_bot)


__all__ = ["run_pr_bot", "PR_LABEL", "BRANCH_PREFIX", "PROTECTED_BRANCHES"]
