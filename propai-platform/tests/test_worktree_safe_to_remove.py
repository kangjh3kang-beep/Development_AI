"""worktree_safe_to_remove.sh 계약 락.

★왜 이 파일이 있는가 — 2차 적대 리뷰가 **fail-open 두 자리**를 변이로 실증했고,
그때 이 도구를 태우는 테스트가 **0건**이었다. 「조회기가 죽으면 SAFE」는 이 저장소가
반복해서 데인 클래스다(§조회기가 죽으면 본판정과 대조군이 똑같이 빈다).

각 테스트는 **두 모집단**을 같은 실행에서 대조한다 — 하나만 보면 「전부 SAFE」나
「전부 UNSAFE」를 내는 구현도 통과하기 때문이다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "worktree_safe_to_remove.sh"


def sh(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return sh("git", "-C", repo, *args)


def verdict(wt: str, *extra: str) -> tuple[str, int]:
    """(::VERDICT= 값, 종료코드). ★판정은 산문이 아니라 이 줄에서 읽는다."""
    p = sh("bash", str(SCRIPT), wt, *extra)
    v = ""
    for line in p.stdout.splitlines():
        if line.startswith("::VERDICT="):
            v = line.split("=", 1)[1].strip()
    return v, p.returncode


@pytest.fixture()
def repo():
    """원격이 있는 스크래치 저장소 + 워크트리 하나. 실저장소를 건드리지 않는다."""
    root = tempfile.mkdtemp(prefix="wtsafe_")
    origin, work = os.path.join(root, "origin"), os.path.join(root, "work")
    sh("git", "init", "-q", "--bare", "-b", "main", origin)
    sh("git", "init", "-q", "-b", "main", work)
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        git(work, "config", k, v)
    Path(work, "a.txt").write_text("a\n")
    Path(work, ".gitignore").write_text(".env\nnode_modules/\nnext-env.d.ts\n")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "init")
    git(work, "remote", "add", "origin", origin)
    git(work, "push", "-q", "origin", "main")
    git(work, "fetch", "-q", "origin")
    yield work, root
    shutil.rmtree(root, ignore_errors=True)


def _wt(work: str, root: str, name: str, *opts: str, commitish: str | None = None) -> str:
    """git worktree add [<opts>] <path> [<commit-ish>] — ★경로가 commit-ish 앞이다."""
    path = os.path.join(root, name)
    args = ["worktree", "add", *opts, path]
    if commitish:
        args.append(commitish)
    r = git(work, *args)
    # ★실패를 단언한다 — 안 그러면 이후 모든 단언이 「대상 없음」으로 공허해진다.
    assert r.returncode == 0, f"worktree add 실패: {r.stderr}"
    assert os.path.isdir(path), path
    return path


def test_script_exists_and_is_executable():
    """대조군: 이 파일이 없으면 아래 전부가 공허하게 통과한다."""
    assert SCRIPT.is_file(), SCRIPT
    assert os.access(SCRIPT, os.X_OK)


class TestFailOpen:
    """★조회기가 죽으면 SAFE 가 나오면 안 된다 — 2차 리뷰가 변이로 잡은 결함."""

    def test_status_failure_is_undecided_not_safe(self, repo):
        work, root = repo
        wt = _wt(work, root, "wt_idx", "--detach", commitish="HEAD")
        clean, _ = verdict(wt, "--no-pr", "대조군")
        assert clean == "SAFE", "대조군이 SAFE 가 아니면 아래 단언이 공허하다"

        # 인덱스를 손상시켜 git status 를 실패시킨다
        gitdir = git(wt, "rev-parse", "--absolute-git-dir").stdout.strip()
        Path(gitdir, "index").write_bytes(b"\x00\x01\x02")
        v, rc = verdict(wt, "--no-pr", "조회기 사망")
        assert v != "SAFE", f"★죽은 조회기가 SAFE 를 냈다 (rc={rc})"
        assert v == "UNDECIDED" and rc == 2, (v, rc)

    def test_reachability_failure_is_not_safe(self, repo):
        """도달성 조회가 실패하면 SAFE 가 아니어야 한다(변이로 확인)."""
        work, root = repo
        wt = _wt(work, root, "wt_reach", "--detach", commitish="HEAD")
        assert verdict(wt, "--no-pr", "대조군")[0] == "SAFE"

        mutated = Path(root, "mutated.sh")
        src = SCRIPT.read_text()
        old = 'for-each-ref --contains "$LOCAL"'
        assert old in src, "변이 지점이 사라졌다 — 락이 낡았다"
        mutated.write_text(src.replace(old, 'for-each-ref --contains NO_SUCH_REF_XYZ'))
        p = sh("bash", str(mutated), wt, "--no-pr", "변이")
        assert "::VERDICT=SAFE" not in p.stdout, "★도달성 조회가 죽었는데 SAFE 를 냈다"


class TestIgnoredFiles:
    """★git status --porcelain 은 ignored 를 안 보는데 remove 는 지운다."""

    def test_env_blocks_but_regenerable_does_not(self, repo):
        work, root = repo
        wt = _wt(work, root, "wt_ign", "--detach", commitish="HEAD")

        # 모집단A: 재생 가능한 것만 → SAFE 여야(위양성 방지 · §A-6)
        os.makedirs(os.path.join(wt, "node_modules", "x"), exist_ok=True)
        Path(wt, "node_modules", "x", "a.js").write_text("x")
        Path(wt, "next-env.d.ts").write_text("// auto-generated")
        assert verdict(wt, "--no-pr", "재생 가능")[0] == "SAFE", "재생물이 막으면 위양성이 결함"

        # 모집단B: .env 추가 → UNSAFE 여야
        Path(wt, ".env").write_text("SECRET=1\n")
        v, rc = verdict(wt, "--no-pr", ".env")
        assert (v, rc) == ("UNSAFE", 1), f"★ignored .env 를 놓쳤다 ({v}, {rc})"

    def test_ignored_file_really_is_deleted_by_remove(self, repo):
        """근거 재확인: 이 위험이 실재하는가(가드가 지키는 대상의 존재 증명)."""
        work, root = repo
        wt = _wt(work, root, "wt_del", "--detach", commitish="HEAD")
        env = Path(wt, ".env")
        env.write_text("SECRET=1\n")
        assert git(wt, "status", "--porcelain").stdout.strip() == "", "porcelain 이 ignored 를 봤다면 전제가 바뀐 것"
        r = git(work, "worktree", "remove", wt)
        assert r.returncode == 0, r.stderr
        assert not env.exists(), "★전제 붕괴: remove 가 ignored 를 안 지운다면 이 가드는 불필요하다"


class TestReachability:
    """★remove 는 refs/heads 를 지우지 않는다 — 손실은 detached 일 때만."""

    def test_branch_attached_local_commit_is_safe(self, repo):
        work, root = repo
        wt = _wt(work, root, "wt_br", "-b", "feat/local-only")
        Path(wt, "b.txt").write_text("b\n")
        git(wt, "add", "-A")
        git(wt, "commit", "-qm", "로컬 전용 커밋")
        v, rc = verdict(wt, "--no-pr", "브랜치 부착")
        assert (v, rc) == ("SAFE", 0), (
            f"★브랜치가 붙어 있으면 커밋은 refs/heads 에 남는다 — UNSAFE 는 위양성 ({v})"
        )

    def test_detached_unreachable_commit_is_unsafe(self, repo):
        work, root = repo
        wt = _wt(work, root, "wt_det", "--detach", commitish="HEAD")
        assert verdict(wt, "--no-pr", "대조군")[0] == "SAFE", "대조군이 SAFE 여야 아래가 유의미"
        Path(wt, "c.txt").write_text("c\n")
        git(wt, "add", "-A")
        git(wt, "commit", "-qm", "detached 전용 커밋")
        v, rc = verdict(wt, "--no-pr", "detached 고아")
        assert (v, rc) == ("UNSAFE", 1), f"★유일 소유자인 커밋을 놓쳤다 ({v}, {rc})"

    def test_squash_merged_branch_is_not_falsely_blocked(self, repo):
        """★git cherry 를 쓰면 여기서 위양성이 난다(2차 리뷰 MAJOR-1)."""
        work, root = repo
        wt = _wt(work, root, "wt_sq", "-b", "feat/to-squash")
        for i in range(3):
            Path(wt, f"s{i}.txt").write_text(f"{i}\n")
            git(wt, "add", "-A")
            git(wt, "commit", "-qm", f"조각 {i}")
        git(wt, "push", "-q", "origin", "feat/to-squash")
        git(work, "fetch", "-q", "origin")
        # main 에 스쿼시로 반영 — patch-id 가 원본들과 달라진다
        git(work, "merge", "-q", "--squash", "feat/to-squash")
        git(work, "commit", "-qm", "squash: 세 조각을 하나로")
        git(work, "push", "-q", "origin", "main")
        git(wt, "fetch", "-q", "origin")

        cherry = git(wt, "cherry", "origin/main", "HEAD").stdout
        plus = sum(1 for l in cherry.splitlines() if l.startswith("+"))
        assert plus > 0, "★전제 붕괴: cherry 가 스쿼시를 견딘다면 이 락의 근거가 사라진다"

        v, rc = verdict(wt, "--no-pr", "스쿼시 반영됨")
        assert (v, rc) == ("SAFE", 0), (
            f"★cherry 축의 위양성이 재발했다 — 원격에 있는데 UNSAFE ({v}, cherry '+'={plus})"
        )


class TestRefusals:
    def test_missing_path_and_subdir_and_anonymous_exemption(self, repo):
        work, root = repo
        wt = _wt(work, root, "wt_ref", "--detach", commitish="HEAD")
        assert verdict(os.path.join(root, "없는경로"))[1] == 2
        sub = os.path.join(wt, "sub", "dir")
        os.makedirs(sub, exist_ok=True)
        assert verdict(sub, "--no-pr", "하위")[1] == 2
        assert sh("bash", str(SCRIPT), wt, "--no-pr").returncode == 2  # 사유 누락

    def test_main_worktree_is_refused(self, repo):
        work, _ = repo
        v, rc = verdict(work, "--no-pr", "메인 워크트리")
        assert (v, rc) == ("UNSAFE", 1), f"★메인 워크트리에 제거를 권했다 ({v})"

    def test_locked_worktree_is_refused(self, repo):
        work, root = repo
        wt = _wt(work, root, "wt_lock", "--detach", commitish="HEAD")
        assert verdict(wt, "--no-pr", "대조군")[0] == "SAFE"
        git(work, "worktree", "lock", "--reason", "다른 세션이 장기 실행 중", wt)
        v, rc = verdict(wt, "--no-pr", "잠김")
        assert (v, rc) == ("UNSAFE", 1), f"★잠긴 워크트리에 제거를 권했다 ({v})"


class TestConfirmedRiskIsNotDowngraded:
    """★MINOR-1: 축1 이 판정 불가로 나가도 이미 확정된 위험을 버리면 안 된다."""

    def test_env_risk_survives_pr_lookup_failure(self, repo):
        work, root = repo
        wt = _wt(work, root, "wt_keep", "--detach", commitish="HEAD")  # detached → 축1 판정 불가
        Path(wt, ".env").write_text("SECRET=1\n")
        v, rc = verdict(wt)  # --no-pr 없이 → 축1 이 undecided 로 나가려 한다
        assert v == "UNSAFE" and rc == 1, (
            f"★확정된 .env 위험이 UNDECIDED 로 강등됐다 ({v}, {rc})"
        )
