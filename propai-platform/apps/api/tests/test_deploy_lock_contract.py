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


# ── 서버 역할 가드 (2026-08-17 추가) ────────────────────────────────────────
#
# 왜 있나 (실사고):
#     168(백엔드)에서 `safe-deploy.sh` 를 돌렸다. 그 스크립트는 158(프론트) 전용이라
#     **트래픽을 받지 않는 compose 스택**만 갱신하고 "성공"을 찍었다.
#     그날 #630·#653·#662 가 배포된 줄 알았으나, 실서비스(caddy → propai-api-800x)
#     컨테이너 안은 **전부 0** 이었다.
#
#     검증도 못 잡았다: 그 스크립트는 `$VERIFY_BASE_URL/ko` 를 보는데 백엔드엔 프론트가
#     없어 **web=404** 가 났고, 그걸 `WARN 검증미흡` 으로만 찍었다. 사람이 "백엔드 전용이라
#     당연"이라고 해석해 경고가 배경이 됐다.
#
#     → 그래서 **시작 지점에서** 서로를 배타적으로 잠근다. 여기서는 그 가드가
#       조용히 사라지지 않도록 **실행 라인**에 존재하는지 확인한다.

INFRA_DIR = Path(__file__).resolve().parents[3] / "infra"
ZERO_DOWNTIME = INFRA_DIR / "deploy-zero-downtime.sh"

# (스크립트, 기대하는 판별 방향) — 방향이 **반대**여야 배타 잠금이 성립한다.
_ROLE_GUARDS = [
    (SAFE_DEPLOY, "present"),   # Caddyfile 이 **있으면** 백엔드 → 중단
    (ZERO_DOWNTIME, "absent"),  # Caddyfile 이 **없으면** 백엔드 아님 → 중단
]


def _executable_lines(path: Path) -> list[str]:
    """주석·빈 줄을 걷어낸 **실행되는 줄**만 돌려준다.

    ★이 저장소는 소스 검사가 주석에 뚫린 사고를 반복했다(가드를 주석 처리하고
      임포트만 남겨도 초록이었다). 그래서 검사 대상을 실행 라인으로 좁힌다 —
      "주석에 가드를 적어 두는 것"으로는 이 테스트를 통과할 수 없다.
    """
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return out


@pytest.mark.parametrize(
    ("script", "sense"), _ROLE_GUARDS, ids=["safe-deploy", "zero-downtime"]
)
def test_배포_스크립트는_서버역할_가드를_갖는다(script: Path, sense: str) -> None:
    """각 배포 스크립트가 **자기 서버가 맞는지** 시작 지점에서 확인하고 아니면 멈춘다."""
    assert script.exists(), f"{script} 가 없다 — 경로가 바뀌었으면 이 테스트도 고칠 것"
    lines = _executable_lines(script)
    # ★공허한 초록 방지: 대상이 실제로 읽혔는지 먼저 단언한다.
    #   파일을 못 읽거나 전부 주석이면 아래 검사가 "위반 0" 으로 통과해 버린다.
    assert len(lines) > 30, f"{script.name}: 실행 라인이 {len(lines)}줄뿐 — 대상을 못 읽었다"

    guard_lines = [ln for ln in lines if "caddy/Caddyfile" in ln]
    assert guard_lines, (
        f"{script.name}: 서버 역할 가드가 **실행 라인에 없다**. "
        "배포 스크립트를 잘못된 서버에서 돌리면 조용히 성공을 찍는다(2026-08-17 실사고)."
    )

    joined = " ".join(guard_lines)
    if sense == "present":
        assert re.search(r'\[\s+-f\s+"\$HOME/caddy/Caddyfile"\s+\]', joined), (
            f"{script.name}: 프론트 전용 스크립트는 Caddyfile 이 **있을 때** 중단해야 한다"
        )
    else:
        assert re.search(r'\[\s+!\s+-f\s+"\$HOME/caddy/Caddyfile"\s+\]', joined), (
            f"{script.name}: 백엔드 전용 스크립트는 Caddyfile 이 **없을 때** 중단해야 한다"
        )

    # ★파일 전체에서 `exit N` 을 찾으면 **가드와 무관한 줄**에 걸린다.
    #   실제로 safe-deploy.sh 의 디스크부족 `exit 7` 때문에, 가드의 종료코드를 바꾸는
    #   변이가 **살아남았다**(2026-08-17 변이 검증에서 적발). 그래서 블록으로 좁힌다.
    block = _guard_block(script)
    assert block, f"{script.name}: 가드 블록을 잘라 내지 못했다"
    assert any(re.search(r"\bexit 10\b", ln) for ln in block), (
        f"{script.name}: 역할 불일치는 **전용 종료코드 10** 으로 끝나야 한다 — "
        "다른 실패와 구분되지 않으면 운영자가 원인을 못 읽는다"
    )


def _guard_block(path: Path) -> list[str]:
    """``~/caddy/Caddyfile`` 을 검사하는 ``if`` 블록의 실행 라인만 잘라 낸다.

    가드에 대한 단언이 **가드 밖의 우연한 문자열**로 충족되는 것을 막는다.
    """
    lines = _executable_lines(path)
    start = next((i for i, ln in enumerate(lines) if "caddy/Caddyfile" in ln), None)
    if start is None:
        return []
    block: list[str] = []
    for ln in lines[start:]:
        block.append(ln)
        if ln == "fi":
            break
    return block


def test_역할가드_종료코드는_다른_실패와_겹치지_않는다() -> None:
    """운영자가 종료코드만 보고 '서버를 잘못 골랐다'를 식별할 수 있어야 한다.

    ★이 테스트가 생긴 이유: 처음에는 가드를 ``exit 7`` 로 썼는데, ``safe-deploy.sh`` 는
      이미 **디스크 부족**에 7 을 쓰고 있었다. 의미가 겹치면 진단이 흐려지고,
      실제로 그 중복 때문에 종료코드 변이가 잡히지 않았다.
    """
    for script, _sense in _ROLE_GUARDS:
        lines = _executable_lines(script)
        start = next((i for i, ln in enumerate(lines) if "caddy/Caddyfile" in ln), None)
        assert start is not None, f"{script.name}: 가드가 없다"
        end = start
        while end < len(lines) and lines[end] != "fi":
            end += 1

        codes = {c for ln in lines[start : end + 1] for c in re.findall(r"\bexit (\d+)", ln)}
        assert len(codes) == 1, f"{script.name}: 가드 블록의 종료코드가 하나가 아니다({codes})"
        code = codes.pop()

        outside = [
            ln
            for i, ln in enumerate(lines)
            if not (start <= i <= end) and re.search(rf"\bexit {code}\b", ln)
        ]
        assert not outside, (
            f"{script.name}: 역할가드 종료코드 {code} 가 다른 실패에도 쓰인다 → {outside}. "
            "겹치면 운영자가 원인을 구분할 수 없다."
        )


def test_두_배포_스크립트의_가드는_서로_반대여야_한다() -> None:
    """같은 방향이면 배타 잠금이 성립하지 않는다 — 한 서버에서 둘 다 돌거나 둘 다 막힌다."""
    senses = set()
    for script, sense in _ROLE_GUARDS:
        guard = " ".join(ln for ln in _executable_lines(script) if "caddy/Caddyfile" in ln)
        negated = bool(re.search(r'\[\s+!\s+-f', guard))
        senses.add((script.name, negated))
        assert negated == (sense == "absent"), f"{script.name}: 가드 방향이 뒤집혔다"
    assert len({neg for _, neg in senses}) == 2, (
        "두 스크립트의 가드 방향이 같다 — 배타 잠금이 성립하지 않는다"
    )


# ── 백엔드 빌드 식별자 · 배포 검증 (2026-08-17 추가) ────────────────────────
#
# 왜 있나 (실사고):
#     배포 후 확인을 **호스트 파일시스템의 소스**로 했다. 그 경로는 `git reset --hard` 로
#     늘 최신이라 **무엇을 배포하든 통과**한다. 그래서 `#630`·`#653`·`#662` 가 반영된 줄
#     알았으나 **실서비스 컨테이너 안은 전부 0** 이었다.
#
#     프론트는 `#658` 이후 **sw 끝 sha** 로 배포 커밋을 읽을 수 있었는데 백엔드에는 그 수단이
#     없었다 — 그 **비대칭**이 오보의 구조적 원인이다. 이제 이미지가 `APP_BUILD_ID` 를 들고
#     있고, 배포 스크립트가 **실행 컨테이너에 직접 물어** 대조한다(Caddy 전환 **전**).

DOCKERFILE_ORACLE = Path(__file__).resolve().parents[3] / "Dockerfile.oracle"


def test_백엔드_이미지는_빌드식별자를_들고_있다() -> None:
    """`Dockerfile.oracle` 이 `APP_BUILD_ID` 를 받아 런타임 ENV 로 박는다."""
    assert DOCKERFILE_ORACLE.exists(), f"{DOCKERFILE_ORACLE} 없음 — 경로가 바뀌었으면 이 테스트도 고칠 것"
    lines = _executable_lines(DOCKERFILE_ORACLE)
    assert len(lines) > 15, f"실행 라인이 {len(lines)}줄뿐 — 대상을 못 읽었다"

    assert any(re.match(r"ARG\s+APP_BUILD_ID", ln) for ln in lines), (
        "Dockerfile.oracle 에 `ARG APP_BUILD_ID` 가 없다 — 이미지가 어느 커밋인지 말할 수 없다"
    )
    assert any(re.match(r"ENV\s+APP_BUILD_ID=", ln) for ln in lines), (
        "`ENV APP_BUILD_ID=` 가 없다 — build-arg 는 런타임에 남지 않으므로 "
        "`docker exec … printenv` 로 되읽을 수 없다"
    )
    # ★빈 값으로 조용히 나가면 검증이 "무엇이 떴는지 모른다"로 되돌아간다.
    assert any('-z "${APP_BUILD_ID}"' in ln for ln in lines), (
        "APP_BUILD_ID 가 비었을 때 빌드를 죽이는 fail-closed 검사가 없다"
    )


def test_배포는_실행컨테이너에_직접_물어_대조한다() -> None:
    """`docker exec … printenv APP_BUILD_ID` 로 **떠 있는 것**을 확인한다.

    ★소스·저장소 상태를 근거로 쓰면 안 된다 — 그게 이 사고의 원인이었다.
    """
    lines = _executable_lines(ZERO_DOWNTIME)
    verify = [ln for ln in lines if "printenv APP_BUILD_ID" in ln]
    assert verify, (
        "deploy-zero-downtime.sh 가 실행 컨테이너에 APP_BUILD_ID 를 묻지 않는다. "
        "호스트 소스 grep 은 `git reset --hard` 때문에 무엇을 배포하든 통과한다."
    )
    assert any("docker exec" in ln for ln in verify), (
        "printenv 를 **컨테이너 안에서** 실행해야 한다(`docker exec`)"
    )
    assert any('--build-arg' in ln and "APP_BUILD_ID" in ln for ln in lines), (
        "빌드에 `--build-arg APP_BUILD_ID` 를 넘기지 않는다 — 이미지에 값이 안 박힌다"
    )


def test_이미지_정리는_dangling_한정이어야_한다() -> None:
    """``docker image prune`` 에 ``-a`` 를 붙이면 **롤백 자산이 사라진다**.

    ★`-a` 는 참조되지 않는 **태그 이미지까지** 지운다 → `propai-api:prev` 소멸.
      그러면 이 스크립트의 자동 롤백이 **조용히 무효**가 되고, 실패한 배포를 되돌릴 수단이
      없어진 뒤에야 드러난다. dangling 한정은 태그 있는 이미지를 건드리지 않는다.
    """
    # ★prune 을 **실행하는** 줄만 본다. `safe-deploy.sh` 에는
    #   `pgrep -f "docker system prune|builder prune"` 처럼 **진행 중인지 감지**하는 줄이 있는데,
    #   그것을 위반으로 신고하면 정상 코드를 막는다(첫 판에서 실제로 그렇게 빨개졌다 —
    #   이 저장소가 반복해서 데인 "가드의 위양성도 결함이다").
    executed = 0
    for script in (ZERO_DOWNTIME, SAFE_DEPLOY):
        for ln in _executable_lines(script):
            if not re.search(r"(?:^|[|&;]\s*)(?:sudo\s+)?docker\s+\w+\s+prune\b", ln):
                continue
            if re.search(r"\b(pgrep|pkill|ps)\b", ln):
                continue  # 감지·조회 줄은 대상이 아니다
            executed += 1
            assert not re.search(r"prune\b[^|]*\s(-\w*a\w*|--all)\b", ln), (
                f"{script.name}: prune 에 -a/--all 이 붙어 있다 → {ln}\n"
                "롤백 자산(propai-api:prev)과 베이스 이미지가 삭제된다. dangling 한정으로 둘 것."
            )
            assert "system prune" not in ln, (
                f"{script.name}: `docker system prune` 은 빌드 캐시·네트워크까지 건드린다"
                "(과거 빌드를 죽인 사고). `docker image prune -f` 만 쓸 것."
            )

    # ★공허한 초록 방지: prune 실행 줄이 0개면 위 단언은 한 번도 돌지 않는다.
    #   이 PR 이 `deploy-zero-downtime.sh` 에 dangling 정리를 넣었으므로 최소 1개여야 한다.
    assert executed >= 1, (
        "prune 실행 줄을 하나도 찾지 못했다 — 정리가 사라졌거나 패턴이 대상을 놓쳤다. "
        "둘 다 이 테스트가 잡아야 할 상태다."
    )


def test_빌드식별자는_의존성설치_뒤에_있어야_한다() -> None:
    """``ARG APP_BUILD_ID`` 가 설치 **앞**에 오면 매 배포가 의존성을 재빌드한다.

    ``ARG`` 값이 바뀌면 **그 이후 모든 레이어의 캐시가 무효화**된다. `APP_BUILD_ID` 는 커밋마다
    바뀌므로, 설치 앞에 두면 `apt-get`·`pip install`(2.4GB 이미지의 대부분)이 매번 다시 돌고
    **dangling 축적도 함께 커진다**.

    ★`Dockerfile.web` 이 `pnpm install` **뒤**에 두는 것과 같은 이유다 — 그 위치가 **계약**이고
      우연이 아니라는 것을 여기서 잠근다(2026-08-17 통합자 리뷰에서 제기된 리스크).
    """
    lines = DOCKERFILE_ORACLE.read_text(encoding="utf-8").splitlines()

    def first(pattern: str) -> int:
        for i, ln in enumerate(lines):
            if re.match(pattern, ln.strip()):
                return i
        return -1

    pip = first(r"RUN pip install")
    apt = first(r"RUN apt-get")
    arg = first(r"ARG APP_BUILD_ID")

    # ★공허한 초록 방지: 세 앵커가 모두 실제로 있어야 비교가 의미를 갖는다.
    assert pip >= 0, "`RUN pip install` 을 못 찾았다 — Dockerfile 구조가 바뀌었으면 이 테스트도 고칠 것"
    assert apt >= 0, "`RUN apt-get` 을 못 찾았다"
    assert arg >= 0, "`ARG APP_BUILD_ID` 가 없다"

    assert arg > pip, (
        f"ARG APP_BUILD_ID({arg + 1}줄)가 `RUN pip install`({pip + 1}줄) **앞**에 있다. "
        "커밋마다 값이 바뀌므로 의존성 설치 캐시가 매 배포 무효화된다 — 설치 뒤로 옮길 것."
    )
    assert arg > apt, (
        f"ARG APP_BUILD_ID({arg + 1}줄)가 `RUN apt-get`({apt + 1}줄) **앞**에 있다."
    )


# ── 배포 자산이 **실행 가능한 상태인가** (2026-08-17 추가) ──────────────────
#
# 왜 있나 (실사고 — 이 락 자체의 구멍이었다):
#     머지 충돌이 `deploy-zero-downtime.sh` 에 `<<<<<<<`/`>>>>>>>` 마커를 남겼는데
#     **위의 모든 계약 테스트가 그대로 통과했다**(13 passed). 마커가 남은 스크립트는
#     실행하면 문법 오류로 죽는다 — 즉 락이 "가드가 있는가"만 보고
#     **"이 파일이 실행될 수 있는가"** 를 보지 않았다.
#
#     ★배포 자산은 그 자체가 실행물이다. 내용 계약을 아무리 잠가도
#       **파일이 깨져 있으면 배포가 시작조차 못 한다** — 그게 더 큰 사고다.

_SHELL_ASSETS = [SAFE_DEPLOY, ROLLBACK_WEB, ZERO_DOWNTIME]


@pytest.mark.parametrize("script", _SHELL_ASSETS, ids=lambda p: p.name)
def test_배포_스크립트에_머지충돌_마커가_없다(script: Path) -> None:
    """`<<<<<<<`·`=======`·`>>>>>>>` 가 남으면 실행 즉시 문법 오류로 죽는다."""
    raw = script.read_text(encoding="utf-8")
    assert len(raw) > 500, f"{script.name}: 내용이 너무 짧다({len(raw)}자) — 대상을 못 읽었다"
    offenders = [
        f"{i}: {ln[:40]}"
        for i, ln in enumerate(raw.splitlines(), 1)
        if ln.startswith(("<<<<<<<", ">>>>>>>")) or ln.rstrip() == "======="
    ]
    assert not offenders, f"{script.name}: 머지 충돌 마커가 남아 있다 → {offenders}"


@pytest.mark.parametrize("script", _SHELL_ASSETS, ids=lambda p: p.name)
def test_배포_스크립트가_문법적으로_유효하다(script: Path) -> None:
    """``bash -n`` 으로 파싱된다 — 배포 자산은 그 자체가 실행물이다.

    ★내용 계약(가드 존재·종료코드·prune 옵션)을 다 잠가도 **파일이 깨져 있으면**
      배포가 시작조차 못 한다. 실제로 충돌 마커가 남은 채 위 13개 테스트가 통과했다.
    """
    import shutil
    import subprocess

    bash = shutil.which("bash")
    assert bash, "bash 를 찾을 수 없다 — 이 검사는 bash 가 있는 환경을 전제한다"
    proc = subprocess.run(  # noqa: S603
        [bash, "-n", str(script)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, (
        f"{script.name}: bash -n 실패(exit {proc.returncode})\n{proc.stderr.strip()[:500]}"
    )


def test_빌드가_캐시를_썼는지_로그에_남긴다() -> None:
    """빌드 출력을 통째로 버리면 **느려졌을 때 원인을 못 가린다**.

    2026-08-18 첫 VERIFY-BUILD 배포가 **699초**(기준선 39초의 18배)였는데,
    빌드 줄이 `docker build … | tail -2` 라 `Using cache` 가 버려져
    *첫 적용 비용인지* / *dangling prune 의 간접 영향인지* 를 **사후에 가릴 수 없었다**.

    ★관측은 가장 먼저 사라지는 코드다(당장 아무것도 안 하므로). 그래서 잠근다.
    """
    lines = _executable_lines(ZERO_DOWNTIME)

    build = [ln for ln in lines if "docker build" in ln]
    assert build, "docker build 줄을 찾지 못했다 — 스크립트 구조가 바뀌었으면 이 테스트도 고칠 것"

    # ★출력을 파이프로 흘려 버리면 캐시 정보가 남지 않는다.
    piped_away = [ln for ln in build if re.search(r"docker build[^|]*\|\s*(tail|head)\b", ln)]
    assert not piped_away, (
        f"docker build 출력을 곧바로 tail/head 로 버린다 → {piped_away}. "
        "파일로 받아 캐시 히트를 센 뒤 요약만 출력할 것."
    )

    assert any("CACHE_HITS" in ln for ln in lines), (
        "빌드 캐시 히트를 세지 않는다 — 배포가 느려져도 원인을 가릴 수 없다"
    )
    # ★`grep -c` 는 매칭 0 에서 exit 1 이고(pipefail+set -e 아래 배포 중단),
    #   결과에 개행이 섞이면 정수 비교가 깨진다. 둘 다 방어했는지 확인한다.
    cache_line = next(ln for ln in lines if ln.startswith("CACHE_HITS="))
    assert "|| true" in cache_line, f"grep -c 실패(매칭 0)를 흡수하지 않는다 → {cache_line}"
    assert "tr -d" in cache_line, (
        f"grep -c 결과를 한 줄로 정규화하지 않는다 → {cache_line}. "
        "개행이 섞이면 `[: integer expression expected` 가 난다(2026-08-18 실측)."
    )


def test_빌드_실패시_로그를_노출한다() -> None:
    """빌드가 죽었을 때 **화면에 아무것도 안 나오면** 원인을 찾을 수 없다.

    ★2026-08-19 회귀(자백): `#699` 가 캐시 히트를 세려고 빌드 출력을 파일로 돌리면서
      **실패 시 출력이 0줄**이 됐다(종전 `| tail -2` 는 에러 2줄이라도 찍고 죽었다).
      `mktemp` 경로도 실패 전에 안 찍혀 **로그 위치조차** 알 수 없었다.
      관측을 넣으려다 진단을 더 나쁘게 만든 것이다 — **성공 경로만 보고 실패 경로를 안 봤다.**

    그래서 세 가지를 잠근다: ①로그 경로를 미리 알린다 ②빌드 실패를 감지한다
    ③실패 시 로그 꼬리를 노출한다.
    """
    lines = _executable_lines(ZERO_DOWNTIME)

    build = [i for i, ln in enumerate(lines) if "docker build" in ln]
    assert build, "docker build 줄을 찾지 못했다"
    bi = build[0]

    # ① 로그 경로를 빌드 **전에** 알린다 — 실패해도 어디를 볼지 알 수 있어야 한다.
    before = lines[:bi]
    assert any("BUILD_LOG" in ln and ln.startswith("echo") for ln in before), (
        "빌드 전에 로그 경로를 출력하지 않는다 — 실패하면 로그 위치조차 모른다"
    )

    # ② 실패를 감지한다(`if !` 로 감싸거나 종료코드를 검사한다).
    assert lines[bi].startswith("if ! ") or any(
        "BUILD_LOG" in ln and "tail -40" in ln for ln in lines[bi : bi + 8]
    ), "빌드 실패를 감지·처리하지 않는다 — set -e 로 조용히 죽으면 화면에 아무것도 안 남는다"

    # ③ 실패 시 로그 꼬리를 노출한다.
    tail_lines = [ln for ln in lines[bi : bi + 8] if re.search(r"tail -\d+ \"\$BUILD_LOG\"", ln)]
    assert any("40" in ln for ln in tail_lines), (
        "실패 시 로그 꼬리(tail -40)를 노출하지 않는다 — 성공 시의 tail -2 만으로는 원인을 못 본다"
    )


def test_전환_전에_컨테이너_소스와_호스트_소스를_대조한다() -> None:
    """VERIFY-BUILD 는 *"어느 커밋을 빌드했는가"* 만 답한다.

    빌드 캐시가 옛 레이어를 재사용하면 ``APP_BUILD_ID`` 만 새로 박히고 **소스는 낡을 수 있다**
    — 그러면 VERIFY-BUILD 는 OK 인데 서비스는 옛 코드다. 그 층을 VERIFY-SOURCE 가 닫는다.

    ★2026-08-19 실측 계기: 168 라이브의 `ordinance_service.py` 가 **미머지 브랜치 HEAD** 와
      같고 `origin/main` 과 달랐다(전수 대조 782 중 1건).
    """
    lines = _executable_lines(ZERO_DOWNTIME)

    # ① 컨테이너 안과 호스트 양쪽에서 해시를 뜬다.
    in_container = [ln for ln in lines if "docker exec" in ln and "md5sum" in ln]
    assert in_container, (
        "컨테이너 안에서 소스 해시를 뜨지 않는다 — 호스트만 보면 `git reset --hard` 때문에 "
        "무엇을 배포하든 통과한다"
    )
    on_host = [ln for ln in lines if "md5sum" in ln and "docker exec" not in ln]
    assert on_host, "호스트 소스 해시를 뜨지 않는다 — 비교 대상이 없다"

    # ② 정렬 없이 비교하면 내용이 같아도 전부 불일치가 된다(첫 판 위양성 110건).
    assert all("sort -k2" in ln for ln in in_container + on_host), (
        "md5sum 출력을 파일명 기준(`sort -k2`)으로 정렬하지 않는다 — "
        "find 순서 차이만으로 전부 불일치가 된다"
    )

    # ③ ★대조군: 목록이 비었는지 먼저 단언해야 한다.
    #    경로를 틀리면 빈 목록이 나오는데 파이프 종료코드는 0 이라 "드리프트 없음"으로 읽힌다.
    guard = [ln for ln in lines if re.search(r'\[\s+"\$_CN"\s+-eq\s+0\s+\]', ln)]
    assert guard, (
        "소스 목록이 비었는지 검사하지 않는다 — 경로 오류가 '드리프트 없음'으로 읽힌다"
    )

    # ④ 불일치면 전환하지 않고 신앱을 제거한다(fail-closed).
    #    ★fail-closed 는 `if` 블록 **안**에 있지 판정 줄에 있지 않다 — 블록으로 잘라 본다
    #    (첫 판에서 판정 줄만 보고 단언했다가 빨개졌다: 검사가 코드 구조를 표현하지 못했다).
    assert any("_DRIFT" in ln for ln in lines), "드리프트 판정 변수를 쓰지 않는다"
    start = next(i for i, ln in enumerate(lines) if ln.startswith("if [") and "_DRIFT" in ln)
    end = start
    while end < len(lines) and lines[end] != "fi":
        end += 1
    guard_block = lines[start : end + 1]
    assert any("rm -f" in ln for ln in guard_block), (
        "드리프트 감지 시 신앱을 제거하지 않는다 — 잘못된 컨테이너가 남는다"
    )
    assert any("exit 1" in ln for ln in guard_block), (
        "드리프트 감지 시 배포를 중단하지 않는다(fail-closed 아님)"
    )


# ── 배포 워크플로가 **어느 서버용인지** (2026-08-20 추가) ────────────────────
#
# 왜 있나:
#     `.github/workflows/deploy-cloudflare.yml` 은 `scripts/safe-deploy.sh` 를 실행한다.
#     그 스크립트는 **158(프론트) 전용**이고, 백엔드(168)는 `infra/deploy-zero-downtime.sh` 다.
#     그런데 워크플로 어디에도 그 사실이 적혀 있지 않았다(서버 언급 0건).
#     → `ORACLE_SSH_HOST` 에 168 을 넣으면 45분 타임아웃까지 간 뒤에야 `exit 10` 으로 막힌다.
#       "자동배포를 켰다"가 실제로는 **158 만** 켠 것이라는 사실도 드러나지 않는다.

WORKFLOW = Path(__file__).resolve().parents[4] / ".github" / "workflows" / "deploy-cloudflare.yml"


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), f"배포 워크플로가 없다: {WORKFLOW}"
    raw = WORKFLOW.read_text(encoding="utf-8")
    assert len(raw) > 1000, f"내용이 너무 짧다({len(raw)}자) — 대상을 못 읽었다"
    return raw


def test_배포_워크플로는_대상_서버를_밝힌다() -> None:
    """`safe-deploy.sh` 를 실행한다면 **프론트 전용**임이 문서에 있어야 한다."""
    raw = _workflow_text()
    assert "safe-deploy.sh" in raw, (
        "이 테스트는 워크플로가 safe-deploy.sh 를 쓴다는 전제 위에 있다 — "
        "배포 경로가 바뀌었으면 이 테스트도 고칠 것"
    )
    assert "deploy-zero-downtime.sh" in raw, (
        "백엔드 정본(infra/deploy-zero-downtime.sh)이 어디에도 언급되지 않는다. "
        "이 워크플로가 158 전용이라는 사실과 168 의 대안을 함께 적어야 "
        "'자동배포 부활'이 158 만이라는 것이 드러난다."
    )


def test_배포_워크플로는_대상_서버_역할을_배포_전에_확인한다() -> None:
    """잘못된 호스트를 **45분 타임아웃 전에** 잡는다.

    ★판별 근거는 `safe-deploy.sh` 의 역할 가드와 **같아야** 한다(`~/caddy/Caddyfile`).
      두 곳이 다른 근거를 쓰면 한쪽만 고쳐져 조용히 갈린다.
    """
    raw = _workflow_text()
    assert "caddy/Caddyfile" in raw, (
        "배포 전 서버 역할 확인이 없다 — 168 을 물리면 배포를 한참 돌린 뒤에야 exit 10 으로 막힌다"
    )

    # ★가드와 같은 근거를 쓰는지 대조한다(대조군: 가드 쪽에 그 문자열이 실재해야 성립).
    guard = " ".join(_executable_lines(SAFE_DEPLOY))
    assert "caddy/Caddyfile" in guard, (
        "safe-deploy.sh 의 역할 가드가 사라졌다 — 워크플로 preflight 의 전제가 무너진다"
    )
