"""DB-backed VCS — 기존 FeasibilityVCS와 동일한 API, PostgreSQL 저장.

서버 재시작 후에도 모든 커밋 이력이 보존된다.
"""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.feasibility_vcs import FeasibilityBranch, FeasibilityCommit, FeasibilityTag


def compute_sha(data: dict[str, Any]) -> str:
    """스냅샷 데이터 -> SHA1 해시."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha1(serialized.encode()).hexdigest()


class FeasibilityVCSDB:
    """수지분석 버전관리 시스템 (DB 영구 저장)."""

    def __init__(self, db: AsyncSession, project_id: uuid.UUID, tenant_id: uuid.UUID):
        self.db = db
        self.project_id = project_id
        self.tenant_id = tenant_id

    async def _ensure_default_branch(self) -> FeasibilityBranch:
        """main 브랜치가 없으면 생성."""
        result = await self.db.execute(
            select(FeasibilityBranch).where(
                FeasibilityBranch.project_id == self.project_id,
                FeasibilityBranch.tenant_id == self.tenant_id,
                FeasibilityBranch.name == "main",
            )
        )
        branch = result.scalar_one_or_none()
        if not branch:
            branch = FeasibilityBranch(
                project_id=self.project_id,
                tenant_id=self.tenant_id,
                name="main",
                is_default=True,
            )
            self.db.add(branch)
            await self.db.flush()
        return branch

    async def _get_current_branch(self) -> FeasibilityBranch:
        """현재 활성 브랜치 조회."""
        result = await self.db.execute(
            select(FeasibilityBranch).where(
                FeasibilityBranch.project_id == self.project_id,
                FeasibilityBranch.tenant_id == self.tenant_id,
                FeasibilityBranch.is_default == True,
            )
        )
        branch = result.scalar_one_or_none()
        if not branch:
            branch = await self._ensure_default_branch()
        return branch

    async def commit(self, snapshot: dict[str, Any], message: str, author: str = "") -> dict:
        """스냅샷 커밋 (DB 저장)."""
        sha = compute_sha(snapshot)
        branch = await self._get_current_branch()

        # 동일 스냅샷 중복 방지
        existing = await self.db.execute(
            select(FeasibilityCommit).where(
                FeasibilityCommit.project_id == self.project_id,
                FeasibilityCommit.sha == sha,
            )
        )
        if existing.scalar_one_or_none():
            return {"sha": sha, "message": message, "timestamp": datetime.utcnow().isoformat(), "duplicate": True}

        commit_record = FeasibilityCommit(
            project_id=self.project_id,
            tenant_id=self.tenant_id,
            sha=sha,
            parent_sha=branch.head_sha,
            message=message,
            snapshot=snapshot,
            author=author,
            branch_name=branch.name,
        )
        self.db.add(commit_record)

        # HEAD 갱신
        branch.head_sha = sha
        await self.db.flush()

        return {
            "sha": sha,
            "parent_sha": commit_record.parent_sha,
            "message": message,
            "author": author,
            "timestamp": commit_record.created_at.isoformat() if commit_record.created_at else datetime.utcnow().isoformat(),
        }

    async def log(self, max_count: int = 50) -> list[dict]:
        """현재 브랜치의 커밋 이력 (최신 순)."""
        branch = await self._get_current_branch()
        if not branch.head_sha:
            return []

        # Walk the parent chain
        result_list: list[dict] = []
        sha: str | None = branch.head_sha
        seen: set[str] = set()

        while sha and len(result_list) < max_count and sha not in seen:
            seen.add(sha)
            result = await self.db.execute(
                select(FeasibilityCommit).where(
                    FeasibilityCommit.project_id == self.project_id,
                    FeasibilityCommit.sha == sha,
                )
            )
            commit = result.scalar_one_or_none()
            if not commit:
                break
            result_list.append({
                "sha": commit.sha,
                "parent_sha": commit.parent_sha,
                "message": commit.message,
                "author": commit.author,
                "timestamp": commit.created_at.isoformat() if commit.created_at else "",
                "branch_name": commit.branch_name,
            })
            sha = commit.parent_sha

        return result_list

    async def diff(self, sha_a: str, sha_b: str) -> dict:
        """두 커밋 간 diff."""
        result_a = await self.db.execute(
            select(FeasibilityCommit).where(
                FeasibilityCommit.project_id == self.project_id,
                FeasibilityCommit.sha == sha_a,
            )
        )
        result_b = await self.db.execute(
            select(FeasibilityCommit).where(
                FeasibilityCommit.project_id == self.project_id,
                FeasibilityCommit.sha == sha_b,
            )
        )
        ca = result_a.scalar_one_or_none()
        cb = result_b.scalar_one_or_none()

        if not ca or not cb:
            return {"error": "커밋을 찾을 수 없습니다"}

        snap_a = ca.snapshot or {}
        snap_b = cb.snapshot or {}
        changes: dict[str, Any] = {}
        for key in set(snap_a.keys()) | set(snap_b.keys()):
            old_val = snap_a.get(key)
            new_val = snap_b.get(key)
            if old_val != new_val:
                changes[key] = {"old": old_val, "new": new_val}

        return {"sha_a": sha_a, "sha_b": sha_b, "changes": changes}

    async def rollback(self, target_sha: str) -> dict | None:
        """특정 커밋으로 롤백 (원본 보존 — 새 커밋 생성)."""
        result = await self.db.execute(
            select(FeasibilityCommit).where(
                FeasibilityCommit.project_id == self.project_id,
                FeasibilityCommit.sha == target_sha,
            )
        )
        target = result.scalar_one_or_none()
        if not target:
            return None

        return await self.commit(
            snapshot=target.snapshot,
            message=f"rollback to {target_sha[:8]}",
        )

    async def create_branch(self, name: str, from_sha: str | None = None) -> dict:
        """브랜치 생성."""
        branch = await self._get_current_branch()
        sha = from_sha or branch.head_sha

        new_branch = FeasibilityBranch(
            project_id=self.project_id,
            tenant_id=self.tenant_id,
            name=name,
            head_sha=sha,
            is_default=False,
        )
        self.db.add(new_branch)
        await self.db.flush()
        return {"name": name, "head_sha": sha}

    async def switch_branch(self, name: str) -> bool:
        """브랜치 전환."""
        result = await self.db.execute(
            select(FeasibilityBranch).where(
                FeasibilityBranch.project_id == self.project_id,
                FeasibilityBranch.tenant_id == self.tenant_id,
            )
        )
        branches = result.scalars().all()
        found = False
        for b in branches:
            if b.name == name:
                b.is_default = True
                found = True
            else:
                b.is_default = False
        if found:
            await self.db.flush()
        return found

    async def tag(self, name: str, sha: str | None = None) -> str:
        """태그 생성."""
        branch = await self._get_current_branch()
        target = sha or branch.head_sha
        if not target:
            raise ValueError("태그 대상 SHA가 없습니다")

        tag_record = FeasibilityTag(
            project_id=self.project_id,
            tenant_id=self.tenant_id,
            name=name,
            sha=target,
        )
        self.db.add(tag_record)
        await self.db.flush()
        return target
