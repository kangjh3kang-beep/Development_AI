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

# ★리터럴 "scripts/worktree_safe_to_remove.sh" 를 남긴다 — 형제 락
# (test_ci_path_filter_covers_locked_scripts.py)이 테스트 파일에서 경로를 **파생**시키는데,
# Path(...) 조합형은 그 정규식에 안 걸려 이 스크립트가 CI 필터 감시에서 **보이지 않는다**.
_REL = "scripts/worktree_safe_to_remove.sh"
SCRIPT = Path(__file__).resolve().parents[2] / _REL


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
    # ★dist/ 를 넣어야 「무시된 디렉토리」 경로를 태운다.
    #   없으면 `?? dist/`(미추적)로 잡혀 **다른 축**이 UNSAFE 를 내고, 그러면
    #   테스트가 초록/빨강을 내더라도 의도한 자리를 안 본다.
    Path(work, ".gitignore").write_text(
        ".env\nnode_modules/\nnext-env.d.ts\ndist/\n"
    )
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

    def test_secret_inside_collapsed_ignored_dir_blocks(self, repo):
        """★3차 리뷰 MAJOR-1 — git 은 `!! dist/` 로 **디렉토리를 접어** 보고한다.

        그래서 안에 `.env` 가 있어도 **항목 이름만 보면 안 보인다.** 종전 구현은
        경로 세그먼트 매칭이라 `dist/` 아래 전부가 「재생 가능」을 상속했고,
        실측으로 `dist/.env` 가 remove 에 **소실**됐다.
        """
        work, root = repo
        # 모집단A: 접힌 빌드 디렉토리 안에 비밀 → 보존해야 한다
        wa = _wt(work, root, "wt_dsec", "--detach", commitish="HEAD")
        os.makedirs(os.path.join(wa, "dist"), exist_ok=True)
        Path(wa, "dist", ".env").write_text("SECRET=prod\n")
        # ★전제: git 이 실제로 디렉토리를 접는지 확인(안 접으면 이 테스트가 다른 것을 태운다)
        raw = git(wa, "status", "--porcelain", "--ignored=matching").stdout
        assert "dist" in raw, raw
        va, rca = verdict(wa, "--no-pr", "접힌 디렉토리 안 비밀")
        assert (va, rca) == ("UNSAFE", 1), f"★dist/.env 를 놓쳤다 ({va}) — remove 가 지운다"

        # 모집단B: 같은 디렉토리에 순수 빌드산출만 → 막으면 위양성이 결함(§A-6)
        wb = _wt(work, root, "wt_dclean", "--detach", commitish="HEAD")
        os.makedirs(os.path.join(wb, "dist"), exist_ok=True)
        Path(wb, "dist", "bundle.js").write_text("console.log(1)\n")
        vb, rcb = verdict(wb, "--no-pr", "순수 빌드산출")
        assert (vb, rcb) == ("SAFE", 0), f"★빌드산출을 막으면 위양성이 결함 ({vb})"

    def test_dependency_tree_secret_lookalike_is_not_a_false_positive(self, repo):
        """★2차 MAJOR-3 재발 방지 — `.venv/**/cacert.pem` 은 정당한 재생물이다.

        deny-first 를 의존성 트리에까지 적용하면 위양성 86/108 이 되살아난다.
        """
        work, root = repo
        wt = _wt(work, root, "wt_deps", "--detach", commitish="HEAD")
        os.makedirs(os.path.join(wt, "node_modules", "pkg"), exist_ok=True)
        Path(wt, "node_modules", "pkg", "cacert.pem").write_text("-----BEGIN-----\n")
        v, rc = verdict(wt, "--no-pr", "의존성 트리 안 pem")
        assert (v, rc) == ("SAFE", 0), f"★의존성 트리를 막으면 위양성이 결함 ({v})"

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
        before = git(wt, "rev-parse", "HEAD").stdout.strip()
        Path(wt, "b.txt").write_text("b\n")
        git(wt, "add", "-A")
        git(wt, "commit", "-qm", "로컬 전용 커밋")
        # ★전제 가드 — 커밋이 실제로 생겼는지 먼저 단언한다.
        #   없으면 이 테스트는 「기본 상태가 SAFE」를 확인할 뿐이라 공허하다(3차 리뷰 MINOR-5).
        after = git(wt, "rev-parse", "HEAD").stdout.strip()
        assert after and after != before, "커밋이 안 생겼다 — 아래 단언이 공허해진다"
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


class TestAxisOrderPreservesConfirmedRisk:
    """★3차 리뷰 MINOR-1 — 확정된 사실이 뒤 축의 판정 불가에 버려지면 안 된다."""

    def test_lock_is_seen_even_when_pr_lookup_is_undecided(self, repo):
        work, root = repo
        wt = _wt(work, root, "wt_lockord", "--detach", commitish="HEAD")
        # 대조군(잠금 없음): detached 라 축1이 판정 불가 → UNDECIDED 여야 한다
        assert verdict(wt)[0] == "UNDECIDED", "대조군이 UNDECIDED 가 아니면 아래가 공허하다"
        git(work, "worktree", "lock", "--reason", "다른 세션 사용 중", wt)
        v, rc = verdict(wt)  # --no-pr 없이 → 축1은 여전히 판정 불가
        assert (v, rc) == ("UNSAFE", 1), (
            f"★잠김이라는 확정 사실이 축1 판정 불가에 버려졌다 ({v}, {rc})"
        )


class TestDebtsLeftOpen:
    """★닫지 않은 것을 초록 안에서 보이게 남긴다(§B-13).

    3차 적대 리뷰가 변이 19종 중 **6종 SURVIVED** 를 보고했다. 아래는 그중
    이번에 닫지 않기로 한 축이다 — 커밋 메시지에만 적으면 드러나지 않는다.
    """

    @pytest.mark.skip(reason="부채: 미구현 — 아래 todo 참조")
    def test_placeholder(self):
        pass

    def test_debts_are_declared(self):
        """부채 목록이 이 파일에 실재하는지 자기점검(문서가 조용히 사라지지 않게)."""
        src = Path(__file__).read_text(encoding="utf-8")
        for token in ("refs/remotes 축", "DIRTY 게이트", "축1(gh) 락 0건"):
            assert token in src, f"부채 선언이 사라졌다: {token}"


# ★it.todo 상당 — 닫지 않은 축을 이름으로 남긴다:
#   · "refs/remotes 축": 변이 `refs/heads refs/remotes` → `refs/heads` 가 SURVIVED.
#     판별 모집단(로컬 브랜치 없고 원격에만 있는 커밋에 detached)이 현재 인구 0이라 미추가.
#   · "DIRTY 게이트": 변이 `[ "$DIRTY" = "0" ]` → `[ 0 = 0 ]` 가 SURVIVED.
#     완화: `git worktree remove` 자신이 EXIT=128 로 거부하고 파일을 보존한다(3차 리뷰 실측).
#   · "축1(gh) 락 0건": 12건 중 gh 를 타는 경로가 없다(정보 축이라 판정을 뒤집지 않음).
#     계획서 §5 의 "각 축이 혼자서 판정을 뒤집는다"는 **축1에는 거짓**이다.


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
