"""배포/롤백 스크립트의 **락 계약**을 잠근다.

왜 이 테스트가 있나 (2026-08-06 실측):
    서버 홈에만 있던 ``~/rollback-web.sh`` 의 동시실행 가드가 이랬다::

        LOCK=/tmp/propai_deploy.lock
        if [ -f "$LOCK" ]; then echo "배포 진행 중"; exit 1; fi

    그런데 ``safe-deploy.sh`` 의 락은 **원자적 mkdir 로 만든 디렉터리**다.
    디렉터리에 ``-f`` 는 **항상 거짓**이라, 이 가드는 한 번도 발동한 적이 없다.
    (배포가 실제로 도는 중에 ``-d`` 는 참, ``-f`` 는 거짓임을 실측했다.)
    그래서 빌드/재생성 도중 롤백이 끼어들어 ``propai-web:oracle`` 태그를
    서로 덮을 수 있었다 — 조용한 경합이라 헬스체크로는 절대 안 잡힌다.

    "가드가 있다"와 "가드가 동작한다"는 다르다. 락 **경로**와 **획득 방식**이
    두 스크립트에서 같아야만 상호배제가 성립하므로, 그 일치를 여기서 잠근다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
SAFE_DEPLOY = SCRIPTS_DIR / "safe-deploy.sh"
ROLLBACK_WEB = SCRIPTS_DIR / "rollback-web.sh"


def _read(path: Path) -> str:
    """★주석을 걷어낸 **실행 코드**만 돌려준다.

    저장소에 이미 박혀 있는 함정: 소스를 grep 으로 검사하면 주석이 코드로 읽힌다.
    이 파일 자체가 그 함정에 걸렸었다 — rollback-web.sh 가 옛 결함을 주석으로
    *설명*하는데 그게 결함으로 판정됐다. 반대로 더 중요한 건, **주석 처리된 가드는
    가드가 아니라는 것**이다. 주석을 지우고 봐야 "가드가 실제로 실행되는가"를 잠근다.
    """
    assert path.is_file(), f"배포 자산이 저장소에 없다: {path}"
    raw = path.read_text(encoding="utf-8")
    # 공허진리 방지 — 빈 파일이면 아래 부재 검사들이 전부 통과해 버린다.
    assert len(raw) > 500, f"내용이 너무 짧다({len(raw)}자) — 검사 대상이 비었을 수 있다: {path}"
    code = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    assert len(code) > 300, f"주석 제거 후 실행 코드가 거의 없다({len(code)}자): {path}"
    return code


def _lock_paths(text: str) -> set[str]:
    """스크립트가 참조하는 락 경로를 모은다(변수 대입값 기준)."""
    return set(re.findall(r'LOCK(?:DIR|FILE)?="?\$\{?[A-Z_]+:-([^"}\s]+)\}?"?', text)) | set(
        re.findall(r'LOCK(?:DIR|FILE)?="([^"$\s]+)"', text)
    )


def test_두_스크립트가_같은_락_경로를_쓴다() -> None:
    deploy_locks = _lock_paths(_read(SAFE_DEPLOY))
    rollback_locks = _lock_paths(_read(ROLLBACK_WEB))

    assert deploy_locks, "safe-deploy.sh 에서 락 경로를 찾지 못했다 — 패턴이 낡았을 수 있다"
    assert rollback_locks, "rollback-web.sh 에서 락 경로를 찾지 못했다 — 패턴이 낡았을 수 있다"
    assert deploy_locks & rollback_locks, (
        f"락 경로가 어긋난다: 배포={deploy_locks} 롤백={rollback_locks}. "
        "경로가 다르면 두 스크립트는 서로를 전혀 막지 못한다."
    )


def test_롤백도_배포와_같은_원자적_mkdir_로_락을_획득한다() -> None:
    deploy = _read(SAFE_DEPLOY)
    rollback = _read(ROLLBACK_WEB)

    # 전제 재확인 — 배포 쪽이 mkdir 락을 쓰고 있어야 이 계약이 의미를 가진다.
    assert re.search(r'mkdir\s+"\$LOCKDIR"', deploy), (
        "safe-deploy.sh 가 더 이상 mkdir 락을 쓰지 않는다 — 이 테스트의 전제가 바뀌었다. "
        "락 방식을 바꿨다면 rollback-web.sh 도 같이 바꾸고 이 테스트를 갱신할 것."
    )
    assert re.search(r'mkdir\s+"\$LOCKDIR"', rollback), (
        "rollback-web.sh 가 mkdir 로 락을 획득하지 않는다 — 배포와 상호배제되지 않는다."
    )


@pytest.mark.parametrize("script", [ROLLBACK_WEB, SAFE_DEPLOY], ids=["rollback-web", "safe-deploy"])
def test_디렉터리_락을_파일로_검사하지_않는다(script: Path) -> None:
    """``[ -f "$LOCK…" ]`` 는 디렉터리 락에 **항상 거짓**이다 — 공허한 가드의 재발을 막는다."""
    text = _read(script)
    offenders = re.findall(r'\[\s+-f\s+"\$(?:LOCK|LOCKDIR|LOCKFILE)[^"]*"\s+\]', text)
    assert not offenders, (
        f"{script.name}: 디렉터리 락을 -f 로 검사한다({offenders}). "
        "-f 는 디렉터리에 항상 거짓이라 이 가드는 발동하지 않는다. -d 를 쓰거나 mkdir 로 획득할 것."
    )


def test_sw_상수는_따옴표로_뽑는다() -> None:
    """``propai-v[0-9]*[a-z-]*`` 류 정규식은 끝자리 숫자를 잘라 멀쩡한 값을 틀리게 읽는다(실측)."""
    text = _read(ROLLBACK_WEB)
    assert "propai-v[0-9]" not in text, (
        "sw 상수를 절단형 정규식으로 뽑고 있다 — 접미사에 숫자가 오면 잘린다. "
        'grep -m1 "^const CACHE_NAME" | cut -d\'"\' -f2 처럼 따옴표로 뽑을 것.'
    )
    assert 'cut -d\'"\' -f2' in text, "sw 상수 추출이 따옴표 기반이 아니다"
