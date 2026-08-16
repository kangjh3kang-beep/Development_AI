"""sw 캐시명 파생 계약 — **사람이 올리지 않는다. 빌드가 만든다.**

★왜 (2026-08-16):
    종전에는 배포마다 사람이 `sw.js` 의 `CACHE_NAME` 문자열을 올렸다. 그 결과
      ① **범프 전용 PR 이 85개** 쌓였다(각각 CI 약 16분 + 채번 조율. 세 세션이 1분 안에
         같은 번호를 채번한 사고도 났다)
      ② **순서 결함(CLAUDE.md E-22)** 이 상시 존재했다 — 범프가 기능 PR 보다 먼저 머지되면
         그 기능이 앱셸 캐시에 가려진다. `#644` 가 실제로 그렇게 새어 나갔다
      ③ 그래서 **자동배포를 켤 수 없었다**(머지마다 배포되면 ②가 상시화된다)
    빌드가 만들면 **순서라는 것이 존재하지 않게 되어** ②가 원리적으로 사라진다.

★이 테스트가 지키는 것은 문구가 아니라 **배선**이다. 네 자리가 다 살아 있어야 값이 흐른다:
    safe-deploy.sh(산출·export) → docker-compose.yml(build arg) → Dockerfile.web(ARG/ENV·치환) → sw.js(앵커)
  한 곳만 끊겨도 조용히 옛 캐시명이 나가거나 치환이 안 된 채 배포된다.

★그리고 **치환 실패가 조용하면 지금보다 나쁘다** — 모든 배포가 같은 캐시명을 쓰게 되어
  앱셸 캐시가 **영원히 무효화되지 않는다**. 그래서 Dockerfile 이 3중으로 막고(fail closed),
  이 테스트가 그 가드들이 **실재하는지**를 잠근다.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_PLATFORM = _REPO / "propai-platform"
_SW = _PLATFORM / "apps" / "web" / "public" / "sw.js"
_DOCKERFILE = _PLATFORM / "Dockerfile.web"
_COMPOSE = _PLATFORM / "docker-compose.yml"
_DEPLOY = _PLATFORM / "scripts" / "safe-deploy.sh"

_DEV_PLACEHOLDER = 'const CACHE_NAME = "propai-vdev-local";'


def _read(p: Path) -> str:
    assert p.exists(), f"{p} 가 없다 — 배선의 한 자리가 사라졌다."
    return p.read_text(encoding="utf-8")


def test_sw_상수는_손으로_올린_버전이_아니라_치환_앵커다() -> None:
    """`propai-v<숫자>-<설명>` 같은 **손 채번 형태**가 남아 있으면 실패한다."""
    src = _read(_SW)
    assert _DEV_PLACEHOLDER in src, (
        f"sw.js 에 치환 앵커가 없다. Dockerfile.web 이 이 문자열을 찾아 바꾸므로, "
        f"형식을 바꾸려면 Dockerfile 도 함께 바꿔야 한다. 기대: {_DEV_PLACEHOLDER!r}"
    )
    # 실행되는 상수 선언만 본다(주석의 예시 문자열은 제외 — 위 독스트링과 sw.js 주석에
    # `propai-v002612-e527b6e8` 같은 **예시**가 일부러 들어 있다. 주석을 코드로 읽으면
    # 정상을 위반으로 신고한다 — 위양성도 결함이다).
    decls = [
        ln for ln in src.splitlines()
        if re.match(r'\s*const\s+CACHE_NAME\s*=', ln) and not ln.lstrip().startswith("//")
    ]
    assert len(decls) == 1, f"CACHE_NAME 선언이 {len(decls)}건 — 정확히 하나여야 한다: {decls}"
    hand_bumped = re.search(r'const CACHE_NAME = "propai-v\d+-', decls[0])
    assert not hand_bumped, (
        f"손으로 채번한 캐시명이 남아 있다: {decls[0].strip()}\n"
        "이 상수는 빌드가 만든다 — 범프 PR 을 다시 만들지 마라(그 방식이 E-22 순서 결함의 원인이다)."
    )


def test_배선_네_자리가_모두_살아_있다() -> None:
    """한 곳만 끊겨도 값이 안 흐른다 — **네 자리를 각각** 단언한다."""
    deploy = _read(_DEPLOY)
    assert "APP_BUILD_ID=" in deploy and "export APP_BUILD_ID" in deploy, (
        "safe-deploy.sh 가 APP_BUILD_ID 를 만들지·export 하지 않는다 — 빌드에 값이 도달하지 못한다."
    )
    assert "rev-list --count" in deploy and "rev-parse --short" in deploy, (
        "APP_BUILD_ID 가 커밋에서 파생되지 않는다(seq·shortsha 둘 다 필요)."
    )

    compose = _read(_COMPOSE)
    assert re.search(r"APP_BUILD_ID:\s*\$\{APP_BUILD_ID", compose), (
        "docker-compose.yml 의 web build args 에 APP_BUILD_ID 통로가 없다 — "
        "safe-deploy 가 export 해도 Dockerfile 까지 가지 못한다."
    )

    dockerfile = _read(_DOCKERFILE)
    assert "ARG APP_BUILD_ID" in dockerfile, "Dockerfile.web 에 ARG APP_BUILD_ID 가 없다."
    assert "ENV NEXT_PUBLIC_APP_VERSION=${APP_BUILD_ID}" in dockerfile, (
        "NEXT_PUBLIC_APP_VERSION 을 같은 값에서 파생하지 않는다 — 텔레메트리가 캐시키 폴백으로 "
        "되돌아간다(그게 종전 상태였고, 그래서 캐시명 형식 변경이 텔레메트리에 샜다)."
    )


def test_치환이_조용히_실패할_수_없다() -> None:
    """3중 가드가 **실재**하는지. 조용한 미치환은 캐시를 영원히 고정시킨다(지금보다 나쁘다)."""
    d = _read(_DOCKERFILE)
    guards = {
        "인자 비었음 감지": 'if [ -z "${APP_BUILD_ID}" ]',
        "치환 앵커 존재 확인": f"grep -q 'const CACHE_NAME = \"propai-vdev-local\";'",
        "치환 결과 검증": 'grep -q "const CACHE_NAME = \\"${APP_BUILD_ID}\\";"',
    }
    missing = [name for name, needle in guards.items() if needle not in d]
    assert not missing, (
        f"Dockerfile.web 의 치환 가드가 빠졌다: {missing}\n"
        "가드가 없으면 치환 실패가 **조용히** 통과하고, 모든 배포가 같은 캐시명을 써서 "
        "앱셸 캐시가 영원히 무효화되지 않는다."
    )
    assert "set -eu" in d, "치환 RUN 에 `set -eu` 가 없다 — 중간 실패가 무시된다."


def test_소비처_계약이_유지된다() -> None:
    """캐시명 형식을 바꿔도 **읽는 쪽**이 살아 있어야 한다(소비처를 실제로 열어 확인했다)."""
    collector = _PLATFORM / "apps" / "web" / "lib" / "growth" / "event-collector.ts"
    src = _read(collector)
    # 접두사만 보는 형태여야 한다 — 숫자·설명 형식에 의존하면 파생값에서 깨진다.
    assert 'startsWith("propai-")' in src, (
        "event-collector 가 접두사가 아닌 형식에 의존한다 — 파생 캐시명에서 앱버전 조회가 깨진다."
    )
    # 1차 소스가 주입되면 캐시키 폴백은 애초에 안 탄다(이 PR 이 그 주입을 추가했다).
    assert "NEXT_PUBLIC_APP_VERSION" in src, "1차 소스 참조가 사라졌다."

    rollback = _PLATFORM / "scripts" / "rollback-web.sh"
    r = _read(rollback)
    assert "cut -d" in r and "CACHE_NAME" in r, (
        "rollback-web.sh 가 상수를 따옴표로 뽑지 않는다 — 형식 의존 정규식은 파생값에서 잘린다."
    )
