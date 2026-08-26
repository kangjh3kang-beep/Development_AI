"""vitest 플레이크 판정기 계약 — **두 모집단을 가른다.**

왜: 2026-08-26 실측으로 `ci.yml` 의 `Frontend (type-check + lint + test)` 가
빨강의 **58%** 를 vitest-worker RPC 타임아웃으로 냈다(전수: 창 14일 · 이 잡이 빨간 런 67건 =
FLAKE 39 · **REAL 13** · UNKNOWN 15).
★초판 주석은 *"최근 실패 6/6"* 만 보고 *"진짜 결함을 잡은 적 0회"* 라 적었는데 **틀렸다** —
그 표본이 "최근 + 실패로 남은 런"으로 두 겹 잘려 있었다(성공한 게이트는 자기 증거를 지운다).
**REAL 13건이 이 파일이 지키는 것**이다.
그래서 그 서명일 때만 1회 재시도하도록 게이트를 고쳤다.

★이 파일이 잠그는 것은 **"재시도한다"가 아니라 "무엇을 재시도하지 않는가"** 다.
  판정기가 느슨해지면(예: 타임아웃 문자열만 보면) **진짜 실패가 재시도로 묻힌다** —
  그게 이 변경의 유일한 실질 위험이고, 아래 `REAL_WITH_TIMEOUT` 픽스처가 정확히 그 자리다.
  ★두 픽스처의 차이는 **`2 failed` 한 조각**이다. 그 차이가 판정을 뒤집지 못하면
  이 락은 잠금이 아니다(CLAUDE.md §지켜야 할 것 2).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_CLASSIFY = _REPO / "scripts" / "ci" / "vitest_flake_classify.sh"
_RETRY = _REPO / "scripts" / "ci" / "vitest_with_flake_retry.sh"
_CI_YML = _REPO / ".github" / "workflows" / "ci.yml"

_RPC = 'Error: [vitest-worker]: Timeout calling "onTaskUpdate"'

# ── 픽스처 ────────────────────────────────────────────────────────────────────
# ★요약 두 줄은 **실제 CI 로그에서 그대로 가져왔다**(run 32916207501, 2026-08-26).
#   손으로 지어내면 실물과 형식이 어긋나 판정기가 실물에서만 죽는다.
_SUMMARY_PASS = " Test Files  339 passed (339)\n      Tests  3091 passed | 17 todo (3108)\n     Errors  1 error"
_SUMMARY_FAIL = " Test Files  2 failed | 337 passed (339)\n      Tests  2 failed | 3089 passed (3091)"

FLAKE_LOG = f"✓ lib/region.test.ts (5 tests) 4ms\n{_RPC}\n{_SUMMARY_PASS}\n"
# ★핵심 대조군 — 진짜 실패와 그 타임아웃이 **같은 실행에** 났다.
REAL_WITH_TIMEOUT = f"✕ lib/broken.test.ts\n{_RPC}\n{_SUMMARY_FAIL}\n"
REAL_NO_TIMEOUT = f"✕ lib/broken.test.ts\n{_SUMMARY_FAIL}\n"
# 파일 단위만 실패(테스트 줄은 전량 통과)해도 진짜 실패다.
REAL_FILES_ONLY = (
    f"{_RPC}\n Test Files  1 failed | 338 passed (339)\n      Tests  3091 passed (3091)\n"
)
CRASH_NO_SUMMARY = "Error: Cannot find module 'x'\nELIFECYCLE Command failed with exit code 1.\n"
# ★"0 failed" 는 **실패 0건**이다 — REAL 이 아니다.
#   술어를 `[0-9]+ failed` 로 쓰면 이것이 REAL 로 잡혀 FLAKE 분기가 **영영 안 타면서 초록**이 된다.
#   현재 vitest 는 0 을 생략해 미발현이지만, 선언한 의도(failed >= 1)와 구현이 갈리면
#   그 자체가 결함이다(동료 세션 지적 → 실측으로 REAL 나오는 것 확인 후 교정).
_SUMMARY_ZERO_FAILED = (
    " Test Files  339 passed (339)\n      Tests  0 failed | 3091 passed (3091)"
)
ZERO_FAILED_LOG = f"{_RPC}\n{_SUMMARY_ZERO_FAILED}\n"
# ★가장 위험한 형태 — **요약은 없는데 타임아웃 서명은 있다**(부분 실행 후 크래시).
#   서명만 보면 FLAKE 로 읽히지만, 요약이 없으니 **무엇이 돌았는지 자체를 모른다.**
#   이 픽스처가 없어서 "요약 부재" 가드가 무잠금이었다(변이 M2 가 SURVIVED 로 짚었다) —
#   그 가드를 지워도 다른 픽스처는 전부 UNKNOWN 으로 흘러가 초록이었기 때문이다.
CRASH_WITH_TIMEOUT = f"✓ lib/a.test.ts (2 tests)\n{_RPC}\nELIFECYCLE Command failed with exit code 1.\n"
PASS_BUT_OTHER_FAILURE = f"{_SUMMARY_PASS.replace('Errors  1 error', 'Errors  0')}\nsome other failure\n"
# GitHub Actions 실물 형식 — 타임스탬프 + ANSI 색이 모든 줄에 붙는다.
GHA_FLAKE_LOG = "\n".join(
    f"2026-08-26T00:36:55.4623830Z \x1b[2m{line}\x1b[22m" for line in FLAKE_LOG.splitlines()
)


def _classify(text: str, tmp_path: Path) -> str:
    log = tmp_path / "vitest.log"
    log.write_text(text, encoding="utf-8")
    out = subprocess.run(
        ["bash", str(_CLASSIFY), str(log)], capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, f"판정기가 죽었다: rc={out.returncode} {out.stderr[:400]}"
    return out.stdout.strip()


# ── ①-a 픽스처 자체 검증(공허한 초록 방지) ────────────────────────────────────
def test_fixtures_actually_differ_where_it_matters() -> None:
    """두 픽스처가 **정말로** 한 조각만 다르고, 그 조각이 실재하는지 먼저 본다.

    ★이 단언이 없으면 픽스처를 잘못 만들었을 때(예: 둘 다 failed 없음)
      아래 판정 테스트가 **전부 통과하면서** 아무것도 잠그지 않는다.
    """
    assert _RPC in FLAKE_LOG and _RPC in REAL_WITH_TIMEOUT, "두 픽스처 모두 타임아웃 서명을 가져야 한다"
    assert "failed" not in _SUMMARY_PASS, "통과 요약에 failed 가 있으면 대조가 무의미하다"
    assert "2 failed" in _SUMMARY_FAIL, "실패 요약에 failed 가 없으면 대조가 무의미하다"


# ── ①-b 탐지 ─────────────────────────────────────────────────────────────────
def test_known_flake_is_flake(tmp_path: Path) -> None:
    assert _classify(FLAKE_LOG, tmp_path) == "FLAKE"


def test_zero_failed_is_not_a_real_failure(tmp_path: Path) -> None:
    """★`0 failed` 를 REAL 로 읽으면 FLAKE 분기가 조용히 도달 불가가 된다."""
    assert _classify(ZERO_FAILED_LOG, tmp_path) == "FLAKE"
    # 대조군: 같은 형식에서 1 이면 REAL 이어야 한다(술어가 숫자를 실제로 본다는 증명).
    one = ZERO_FAILED_LOG.replace("0 failed | 3091 passed", "1 failed | 3090 passed")
    assert _classify(one, tmp_path) == "REAL"


def test_real_github_actions_format_is_still_flake(tmp_path: Path) -> None:
    """타임스탬프·ANSI 가 붙은 **실물 형식**에서도 판정이 서야 한다."""
    assert _classify(GHA_FLAKE_LOG, tmp_path) == "FLAKE"


# ── ② 특이도 — ★여기가 이 파일의 존재 이유다 ──────────────────────────────────
@pytest.mark.parametrize(
    "name,text",
    [
        ("실패와 타임아웃이 같이 났다", REAL_WITH_TIMEOUT),
        ("타임아웃 없이 그냥 실패", REAL_NO_TIMEOUT),
        ("파일 단위만 실패", REAL_FILES_ONLY),
    ],
)
def test_real_failures_are_never_retried(name: str, text: str, tmp_path: Path) -> None:
    assert _classify(text, tmp_path) == "REAL", f"{name}: 재시도하면 진짜 결함이 묻힌다"


@pytest.mark.parametrize(
    "name,text",
    [
        ("요약 자체가 없다(수집 실패·크래시)", CRASH_NO_SUMMARY),
        ("★요약은 없는데 서명은 있다(부분 실행 후 크래시)", CRASH_WITH_TIMEOUT),
        ("전량 통과인데 서명이 없다", PASS_BUT_OTHER_FAILURE),
    ],
)
def test_unknown_failures_are_never_retried(name: str, text: str, tmp_path: Path) -> None:
    assert _classify(text, tmp_path) == "UNKNOWN", f"{name}: 모르면 재시도하지 않는다"


# ── ③ 배선 — 스크립트가 실제로 CI 에서 호출되는가 ────────────────────────────
def test_scripts_exist_and_are_executable() -> None:
    for p in (_CLASSIFY, _RETRY):
        assert p.is_file(), f"없음: {p}"


def test_ci_actually_calls_the_retry_wrapper() -> None:
    """★배선하지 않으면 이 스크립트는 **소비처 0** 인 장식이다.

    이 저장소는 "정의만 하고 소비처 0" 으로 여러 번 뚫렸다(CLAUDE.md §검증 규율 표).
    """
    yml = _CI_YML.read_text(encoding="utf-8")
    # 주석에 적어 두고 배선했다고 착각하는 것을 막는다 — 주석 줄을 걷어내고 본다.
    code = "\n".join(ln for ln in yml.splitlines() if not ln.lstrip().startswith("#"))
    assert "vitest_with_flake_retry.sh" in code, (
        "ci.yml 의 실행 라인에서 재시도 래퍼를 호출하지 않는다 — 스크립트가 무배선이다"
    )
    # 대조군: 이 조회기가 살아 있는지(반드시 있는 형제 스텝이 잡히는가).
    assert "pnpm type-check" in code, "조회기 사망 — ci.yml 을 제대로 읽지 못했다"


def test_retry_runs_at_most_once(tmp_path: Path) -> None:
    """★재시도는 **1회뿐**이어야 한다. 여러 번이면 "언젠가는 초록"이라 게이트가 무의미해진다.

    실패를 계속 내는 가짜 명령으로 실행 횟수를 센다(로그가 플레이크 서명을 내도록 만든다).
    """
    counter = tmp_path / "runs.txt"
    fake = tmp_path / "fake_vitest.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'echo x >> "{counter}"\n'
        f"printf '%s\\n' '{_RPC}'\n"
        f"printf '%s\\n' '{_SUMMARY_PASS}'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    out = subprocess.run(
        ["bash", str(_RETRY)],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/usr/bin:/bin", "VITEST_CMD": f"bash {fake}"},
    )
    runs = counter.read_text(encoding="utf-8").count("x")
    assert runs == 2, f"실행 {runs}회 — 최초 1회 + 재시도 1회여야 한다"
    assert out.returncode != 0, "두 번째도 실패했으면 게이트는 빨강이어야 한다"
