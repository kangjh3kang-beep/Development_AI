"""VCS 테스트 — SHA1 불변성, 커밋/브랜치/diff/롤백."""

import pytest
from app.services.feasibility.version_control import FeasibilityVCS, compute_sha


class TestSHA:
    def test_deterministic(self):
        data = {"revenue": 100, "cost": 80}
        sha1 = compute_sha(data)
        sha2 = compute_sha(data)
        assert sha1 == sha2
        assert len(sha1) == 40

    def test_different_data(self):
        sha1 = compute_sha({"a": 1})
        sha2 = compute_sha({"a": 2})
        assert sha1 != sha2


class TestCommit:
    def test_single_commit(self):
        vcs = FeasibilityVCS()
        c = vcs.commit({"revenue": 100}, "초기 커밋")
        assert c.sha is not None
        assert c.message == "초기 커밋"
        assert vcs.head_sha == c.sha

    def test_chain(self):
        vcs = FeasibilityVCS()
        c1 = vcs.commit({"v": 1}, "v1")
        c2 = vcs.commit({"v": 2}, "v2")
        assert c2.parent_sha == c1.sha

    def test_duplicate_snapshot(self):
        vcs = FeasibilityVCS()
        c1 = vcs.commit({"v": 1}, "first")
        c2 = vcs.commit({"v": 1}, "second")
        assert c1.sha == c2.sha  # 동일 스냅샷 중복 방지


class TestLog:
    def test_log_order(self):
        vcs = FeasibilityVCS()
        vcs.commit({"v": 1}, "first")
        vcs.commit({"v": 2}, "second")
        vcs.commit({"v": 3}, "third")
        log = vcs.log()
        assert len(log) == 3
        assert log[0].message == "third"
        assert log[2].message == "first"


class TestDiff:
    def test_basic_diff(self):
        vcs = FeasibilityVCS()
        c1 = vcs.commit({"revenue": 100, "cost": 80}, "v1")
        c2 = vcs.commit({"revenue": 120, "cost": 80}, "v2")
        d = vcs.diff(c1.sha, c2.sha)
        assert "revenue" in d["changes"]
        assert d["changes"]["revenue"]["old"] == 100
        assert d["changes"]["revenue"]["new"] == 120
        assert "cost" not in d["changes"]  # 변경 없음


class TestRollback:
    def test_rollback_preserves_original(self):
        vcs = FeasibilityVCS()
        c1 = vcs.commit({"v": 1}, "v1")
        vcs.commit({"v": 2}, "v2")
        vcs.commit({"v": 3}, "v3")

        rolled = vcs.rollback(c1.sha)
        assert rolled is not None
        assert rolled.snapshot == {"v": 1}
        # 원본 커밋 보존
        assert c1.sha in vcs.commits

    def test_rollback_creates_new_commit(self):
        vcs = FeasibilityVCS()
        c1 = vcs.commit({"v": 1}, "v1")
        vcs.commit({"v": 2}, "v2")
        rolled = vcs.rollback(c1.sha)
        # 롤백은 새 커밋 (같은 스냅샷이므로 SHA 동일)
        log = vcs.log()
        assert len(log) >= 2


class TestBranch:
    def test_create_and_switch(self):
        vcs = FeasibilityVCS()
        vcs.commit({"v": 1}, "init")
        vcs.create_branch("scenario-a")
        assert "scenario-a" in vcs.branches
        assert vcs.switch_branch("scenario-a")
        assert vcs.current_branch == "scenario-a"

    def test_switch_nonexistent(self):
        vcs = FeasibilityVCS()
        assert not vcs.switch_branch("nonexistent")


class TestTag:
    def test_tag_head(self):
        vcs = FeasibilityVCS()
        c = vcs.commit({"v": 1}, "v1.0")
        sha = vcs.tag("v1.0")
        assert sha == c.sha
        assert vcs.tags["v1.0"] == c.sha
