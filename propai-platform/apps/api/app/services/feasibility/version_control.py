"""Git 방식 VCS — commit/branch/diff/rollback/tag/share.

SHA1 해시 기반 불변 스냅샷 관리.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from dataclasses import dataclass, field, asdict


@dataclass
class VCSCommit:
    """불변 커밋."""
    sha: str
    parent_sha: str | None
    message: str
    snapshot: dict[str, Any]
    author: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class VCSBranch:
    """브랜치."""
    name: str
    head_sha: str | None = None
    is_default: bool = False


def compute_sha(data: dict[str, Any]) -> str:
    """스냅샷 데이터 → SHA1 해시."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha1(serialized.encode()).hexdigest()


class FeasibilityVCS:
    """수지분석 버전관리 시스템 (인메모리)."""

    def __init__(self) -> None:
        self.commits: dict[str, VCSCommit] = {}
        self.branches: dict[str, VCSBranch] = {"main": VCSBranch(name="main", is_default=True)}
        self.tags: dict[str, str] = {}  # tag_name → sha

    @property
    def current_branch(self) -> str:
        for name, branch in self.branches.items():
            if branch.is_default:
                return name
        return "main"

    @property
    def head_sha(self) -> str | None:
        branch = self.branches.get(self.current_branch)
        return branch.head_sha if branch else None

    def commit(self, snapshot: dict[str, Any], message: str, author: str = "") -> VCSCommit:
        """스냅샷 커밋."""
        sha = compute_sha(snapshot)

        if sha in self.commits:
            return self.commits[sha]  # 동일 스냅샷 중복 방지

        c = VCSCommit(
            sha=sha,
            parent_sha=self.head_sha,
            message=message,
            snapshot=snapshot,
            author=author,
        )
        self.commits[sha] = c

        # HEAD 갱신
        branch_name = self.current_branch
        self.branches[branch_name].head_sha = sha

        return c

    def get_commit(self, sha: str) -> VCSCommit | None:
        return self.commits.get(sha)

    def log(self, max_count: int = 50) -> list[VCSCommit]:
        """현재 브랜치의 커밋 이력 (최신 순)."""
        result = []
        sha = self.head_sha
        while sha and len(result) < max_count:
            c = self.commits.get(sha)
            if not c:
                break
            result.append(c)
            sha = c.parent_sha
        return result

    def diff(self, sha_a: str, sha_b: str) -> dict[str, Any]:
        """두 커밋 간 diff."""
        ca = self.commits.get(sha_a)
        cb = self.commits.get(sha_b)
        if not ca or not cb:
            return {"error": "커밋을 찾을 수 없습니다"}

        snap_a = ca.snapshot
        snap_b = cb.snapshot
        changes: dict[str, Any] = {}

        all_keys = set(snap_a.keys()) | set(snap_b.keys())
        for key in all_keys:
            old_val = snap_a.get(key)
            new_val = snap_b.get(key)
            if old_val != new_val:
                changes[key] = {"old": old_val, "new": new_val}

        return {"sha_a": sha_a, "sha_b": sha_b, "changes": changes}

    def rollback(self, target_sha: str) -> VCSCommit | None:
        """특정 커밋으로 롤백 (원본 보존 — 새 커밋 생성)."""
        target = self.commits.get(target_sha)
        if not target:
            return None

        return self.commit(
            snapshot=target.snapshot,
            message=f"rollback to {target_sha[:8]}",
        )

    def create_branch(self, name: str, from_sha: str | None = None) -> VCSBranch:
        """브랜치 생성."""
        sha = from_sha or self.head_sha
        branch = VCSBranch(name=name, head_sha=sha)
        self.branches[name] = branch
        return branch

    def switch_branch(self, name: str) -> bool:
        """브랜치 전환."""
        if name not in self.branches:
            return False
        for b in self.branches.values():
            b.is_default = False
        self.branches[name].is_default = True
        return True

    def tag(self, name: str, sha: str | None = None) -> str:
        """태그 생성."""
        target = sha or self.head_sha
        if not target:
            raise ValueError("태그 대상 SHA가 없습니다")
        self.tags[name] = target
        return target
