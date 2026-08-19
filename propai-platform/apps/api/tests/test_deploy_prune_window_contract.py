"""배포 스크립트의 `image prune` 이 **직전 빌드 캐시를 지우지 않는지** 잠근다.

★왜 (2026-08-19):
    `deploy-zero-downtime.sh` 는 **레거시 빌더**로 빌드한다(빌드 로그 `Step N/20` ·
    `Successfully built` · BuildKit `#N` 줄 0). 레거시 빌더의 캐시는 **중간 이미지 그 자체**다.
    그래서 `docker image prune -f` 가 매 배포 시작에 **직전 빌드의 캐시를 통째로 지웠다**.

    실측(168 실서버 · prune 전후 대조):
        [전] docker history propai-api:latest  실제ID 20 / <missing>  9
             docker images -f dangling=true    →  2      ← ★필터가 보여주는 것
             sudo docker image prune -f        →  487.6MB 회수
        [후] docker history propai-api:latest  실제ID  1 / <missing> 28   ← 19개 삭제

    ★**조회 도구가 보여주는 집합(2)과 명령이 지우는 집합(19)이 다르다.**
      "dangling 은 2개뿐이니 안전하다"는 판단이 그래서 두 번 틀렸다.

    결과: `빌드 캐시 재사용 = 0 / 20` 이 2회 연속(빌드 287초·279초).
    ★독립 대조군: **158(`safe-deploy.sh`)은 이 prune 이 없고 같은 레거시 빌더인데
      `Using cache` 6줄**이다. 같은 빌더 · 유일한 차이가 prune 유무 · 결과가 6 대 0.

★이 파일이 잠그는 것은 문구가 아니라 **범위 한정자의 실재**다.
    `--filter until=...` 이 사라지면 캐시가 다시 죽고, 그 손실은 **조용하다**
    (배포는 성공하고 4분만 더 걸린다 — 아무도 실패로 보지 않는다).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests._scan_guard import read

_REPO = Path(__file__).resolve().parents[4]
_PLATFORM = _REPO / "propai-platform"
_ZDT = _PLATFORM / "infra" / "deploy-zero-downtime.sh"
_SAFE = _PLATFORM / "scripts" / "safe-deploy.sh"

# `sudo docker image prune ...` 한 줄을 뽑는다(주석 줄은 배제 — 주석에 예시가 들어 있다).
_PRUNE_RX = re.compile(r"^\s*(?!#)(?:sudo\s+)?docker\s+image\s+prune\b[^\n]*", re.MULTILINE)


def _prune_lines(text: str) -> list[str]:
    return [m.group(0).strip() for m in _PRUNE_RX.finditer(text)]


def test_전제_prune_줄이_실재한다() -> None:
    """★공허한 초록 방지 — prune 줄이 0건이면 아래 단언은 전부 자동 통과한다."""
    lines = _prune_lines(read(_ZDT, must_exist_reason="168 배포 정본"))
    assert len(lines) == 1, (
        f"`docker image prune` 줄이 {len(lines)}건 — 정확히 1건이어야 한다. "
        f"구조가 바뀌었으면 이 테스트도 함께 고칠 것: {lines}"
    )


def test_prune_은_시간창으로_한정된다() -> None:
    """`--filter until=...` 이 없으면 **직전 빌드 캐시가 매번 죽는다.**"""
    line = _prune_lines(read(_ZDT, must_exist_reason="168 배포 정본"))[0]
    assert "--filter" in line and "until=" in line, (
        "`docker image prune` 이 시간창 없이 돈다 — 레거시 빌더의 캐시(중간 이미지)를 "
        "매 배포마다 통째로 지운다(실측: 캐시 히트 0/20 · 빌드 287초). "
        f"`--filter \"until=24h\"` 를 붙일 것. 현재: {line!r}"
    )


# ★**결합 단축 플래그**(`-af`)까지 잡아야 한다. 이 저장소의 역사적 사고가 바로 그 형태였다
#   (주석: *"과거 `docker system prune -af` 가 빌드를 죽인 사고"*).
#   처음 쓴 `(?<![\w-])-a(?![\w-])` 는 `-a` 단독만 잡아 **변이 `-af` 가 생존했다**(실측).
#   그리고 정상 표기를 막으면 안 된다(§회귀망 A.6) — `-f` 와 `--filter` 는 통과해야 한다.
_ALL_FLAG_RX = re.compile(r"(?<![\w-])-[a-zA-Z]*a[a-zA-Z]*(?![\w-])|--all\b")


def test_prune_에_all_플래그가_없다() -> None:
    """★`-a` 는 **롤백 자산**(`propai-api:prev`)까지 지운다 — 실패한 배포를 되돌릴 수단이 사라진다."""
    line = _prune_lines(read(_ZDT, must_exist_reason="168 배포 정본"))[0]
    assert not _ALL_FLAG_RX.search(line), (
        f"`docker image prune` 에 `-a/--all`(결합형 `-af` 포함)이 붙었다 — "
        f"prev 롤백 자산이 사라져 자동 롤백이 조용히 무효가 된다: {line!r}"
    )


def test_all_플래그_검사기가_정상표기를_막지_않는다() -> None:
    """★가드의 **위양성**도 결함이다(§회귀망 A.6).

    잡아야 하는 것과 통과시켜야 하는 것을 **둘 다** 단언한다 — 한쪽만 두면
    "아무것도 안 잡는 가드"나 "정상 코드를 막는 가드"가 조용히 들어온다.
    """
    must_catch = ["-a", "-af", "-fa", "--all", "docker image prune -af --filter x"]
    must_pass = ["-f", '--filter "until=24h"', 'docker image prune -f --filter "until=24h"']
    for s in must_catch:
        assert _ALL_FLAG_RX.search(s), f"잡아야 하는데 못 잡는다: {s!r}"
    for s in must_pass:
        assert not _ALL_FLAG_RX.search(s), f"정상 표기를 위반으로 신고한다: {s!r}"


def test_대조군_158_에는_prune_이_없다() -> None:
    """★이 테스트가 잠그는 인과의 **대조군**이다.

    158 은 같은 레거시 빌더인데 prune 이 없어 `Using cache` 가 살아 있다(실측 6줄).
    누군가 "168 에 있으니 158 에도 넣자"는 대칭 논리로 prune 을 추가하면
    **프론트 빌드까지 느려진다** — 그래서 부재를 명시적으로 잠근다.

    ★부재를 잠그는 것이지 "디스크 관리가 필요 없다"는 뜻이 아니다.
      158 은 2026-08-17 에 디스크 90% 로 배포가 죽은 전례가 있다. 해법이 필요하다면
      **prune 이 아닌 다른 것**이어야 하고, 그때는 이 테스트를 근거와 함께 고칠 것.
    """
    lines = _prune_lines(read(_SAFE, must_exist_reason="158 배포 정본"))
    assert lines == [], (
        "158 `safe-deploy.sh` 에 `docker image prune` 이 들어왔다. 같은 레거시 빌더라 "
        "프론트 빌드 캐시가 죽는다(168 실측: 6줄 → 0줄). 시간창을 붙이거나 다른 해법을 쓸 것: "
        f"{lines}"
    )
