"""배포가 **모든 백그라운드 워커**에 도달한다는 계약을 잠근다.

왜 이 테스트가 있나 (2026-08-12 프로덕션 실측):
    백엔드 배포는 API 컨테이너만 블루-그린으로 교체한다. 워커는 대상이 아니다.
    2026-08-02 에 arq 가 이 사실에 걸려 배포에 정렬이 배선됐는데, **똑같은 처지의
    celery 3종(worker·beat·flower)은 스윕되지 않았다**. 그 결과:

        propai-celery-worker 이미지 = 2026-07-22 (3주 전)
        propai-api:latest          = 2026-08-11

    그 3주간 배포된 모든 백엔드 수정이 celery 가 실행하는 태스크
    (parcel_batch·rates·auction·growth·member PII 파기)에는 **한 번도 닿지 않았다**.
    컨테이너는 내내 ``Up`` 이었다 — 그래서 아무도 몰랐다.

★★이 파일의 첫 판은 **정적 문자열 검사**였고, 리뷰의 변이가 두 형태로 관통했다:

    1) ``log "… bash scripts/a1-align-workers.sh"``  — 호출을 지우고 **안내 문구만** 남겼는데
       통과했다. 배제 규칙이 ``^(echo|printf)`` 라는 **목록형**이라 래퍼 한 겹으로 뚫린다.
       (이 저장소의 형제 스크립트가 실제로 ``log()`` 스타일을 쓴다.)
    2) ``if false; then bash …; fi`` — 실행 줄에 **있기는 하다**. 정적 검사는 도달을 못 본다.

    그래서 정렬 진입점은 **실제로 실행해서** 확인한다(아래 `test_정렬_진입점을_실제로_실행하면…`).
    스텁을 옆에 두고 돌려, 두 워커 스크립트가 **정말 불렸는지**를 본다.
    배포 스크립트는 실행할 수 없으므로(도커 빌드·sudo·Caddy) 정적으로 남기되,
    호출을 **명령 위치**로 못박아 위 1)형 우회를 닫는다.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PLATFORM_DIR / "scripts"
DEPLOY_SCRIPT = PLATFORM_DIR / "infra" / "deploy-zero-downtime.sh"
ALIGN_SCRIPT = SCRIPTS_DIR / "a1-align-workers.sh"
ARQ_SCRIPT = SCRIPTS_DIR / "a1-arq-worker.sh"
WORKER_SETTINGS = PLATFORM_DIR / "apps" / "worker" / "main.py"

# 워커 정렬 스크립트 명명 규약 — 이 규약을 따라야 아래 파생 규칙이 새 워커를 포착한다.
WORKER_SCRIPT_GLOB = "a1-*.sh"
WORKER_SCRIPT_TOKEN = "worker"

# 셸에서 스크립트를 **부르는** 형태들. 좁게 잡으면 정상 코드를 위반으로 신고한다
# (실제로 `sh x.sh` 를 놓쳐 기준선이 빨개졌다 — 가드의 위양성도 결함이다).
_RUNNERS = r"(?:bash|sh|zsh|source|\.)"


def _code(path: Path) -> str:
    """★주석을 걷어낸 **실행 줄**만 돌려준다.

    소스를 그냥 grep 하면 주석이 코드로 읽힌다. 반대 방향도 중요하다 —
    **주석 안에 적힌 호출은 호출이 아니다**. 이 파일들은 결함의 내력을 주석에
    길게 적으므로(예: "종전에는 arq 만 정렬했다"), 걷어내지 않으면 지금은 하지 않는
    일을 하고 있다고 오판한다.
    """
    assert path.is_file(), f"배포 자산이 저장소에 없다: {path}"
    raw = path.read_text(encoding="utf-8")
    # 공허진리 방지 — 빈/짧은 파일이면 아래 검사들이 통째로 무의미해진다.
    assert len(raw) > 500, f"내용이 너무 짧다({len(raw)}자) — 검사 대상이 비었을 수 있다: {path}"
    code = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    assert len(code) > 300, f"주석 제거 후 실행 코드가 거의 없다({len(code)}자): {path}"
    return code


def _invocations(code: str, script_name: str) -> list[str]:
    """스크립트를 **명령 위치에서** 부르는 줄만 돌려준다.

    ★이 함수의 형태는 변이가 정했다. 처음엔 줄 아무 데나 ``bash x.sh`` 가 있으면
    호출로 셌는데, **안내 문구 안의 같은 문자열**이 검사를 만족시켰다::

        log "워커 정렬을 하려면: bash scripts/a1-align-workers.sh"   # 호출 아님

    ``echo``/``printf`` 만 배제하는 것은 목록형이라 래퍼 한 겹(``log()``)으로 뚫린다.
    그래서 배제 대신 **명령이 줄 맨 앞(또는 `if`/`&&`/`||`/`;` 직후)에 오는가**로 뒤집었다.
    문구 안의 호출은 앞에 다른 명령(``log``·``echo``·``cat``)이 있으므로 걸리지 않는다.
    """
    hits = []
    # ★줄이음(`\` 끝)을 먼저 합친다 — 줄 단위 판정은 `bash \`↵`  scripts/x.sh` 를 못 본다.
    #   인자가 길어지면 자연히 쓰는 표기라, 정상 리팩터를 위반으로 신고하게 된다.
    joined = re.sub(r"\\\n\s*", " ", code)
    for line in joined.splitlines():
        # ★따옴표 안은 명령이 아니다 — 여기서도 `_strip_quoted` 를 쓴다.
        #   이 한 줄이 빠져 있어서, 안내 문구에 세미콜론이 하나 들어간 것만으로
        #   (`log "실패시: cd repo; bash scripts/x.sh"`) 계약이 재개통됐다(변이 실증).
        #   ★같은 커밋이 alembic 쪽을 위해 만든 도구를 형제에 적용하지 않은 것이다 —
        #   두 형제가 서로 다른 방어를 쓰면 약한 쪽이 뚫린다.
        stripped = _neutralize_quoted_separators(line).strip()
        # 명령 위치: 줄 시작 · `if/then/else/do/{` 뒤 · `&&`/`||`/`;`/`|` 뒤 · `eval` 경유.
        pattern = (
            rf"(?:^|(?:^|[;&|{{])\s*(?:if|then|else|do|eval|\{{)\s+|[;&|{{]\s*)"
            # `eval "bash x.sh"` 처럼 러너가 따옴표 뒤에 오는 형태까지 허용한다
            # (허용 표기를 좁게 열거하면 정상 리팩터가 빨개진다 — 이 저장소의 반복 결함).
            rf"""(?:!\s*)?(?:eval\s+["']?)?{_RUNNERS}\s+\S*{re.escape(script_name)}(?:\s|$|;|["'])"""
        )
        if re.search(pattern, stripped):
            hits.append(stripped)
    return hits


def _strip_quoted(line: str) -> str:
    """따옴표 안 내용을 지운다 — **문구는 명령이 아니다**.

    ★이 함수도 변이가 만들었다. alembic 게이트 검사를 단순 문자열 탐색으로 썼더니,
    실행 블록을 통째로 지워도 다음 한 줄이 검사를 만족시켰다::

        echo "== DB 마이그레이션(alembic upgrade head, 신 컨테이너 내부) =="

    같은 결함(표기 vs 실행)을 **그 결함을 고치는 커밋 안에서** 재생산한 것이다.
    따옴표를 걷어내면 위 줄은 ``echo`` 만 남아 `docker exec` 를 찾지 못한다.
    """
    return re.sub(r"""(["']).*?\1""", "", line)


def _neutralize_quoted_separators(line: str) -> str:
    """따옴표 **안**의 셸 구분자만 무력화한다(내용은 남긴다).

    ★`_strip_quoted` 를 호출 검사에 그대로 쓸 수는 없다 — 정상 호출인
    ``bash "$SCRIPT_DIR/a1-arq-worker.sh"`` 는 경로가 따옴표 안이라 통째로 사라져
    **정상 코드가 위반으로 신고된다**(실측). 반대로 그냥 두면 안내 문구 안의
    세미콜론 하나가 새 명령 위치를 만들어 계약이 재개통된다::

        log "워커 정렬 실패시: cd repo; bash scripts/a1-align-workers.sh 로 재실행"

    그래서 따옴표 안에서는 **구분자만** 공백으로 바꾼다. 위 문구의 `bash` 는 앞에
    구분자가 없어 명령 위치가 아니게 되고, 따옴표 인자는 그대로 매칭된다.
    """

    def _blank(m: re.Match[str]) -> str:
        return re.sub(r"[;&|{}]", " ", m.group(0))

    return re.sub(r"""(["']).*?\1""", _blank, line)


def _worker_alignment_scripts() -> list[Path]:
    """정렬 대상 워커 스크립트를 **파생**시킨다(사람이 센 목록을 쓰지 않는다).

    ★한계를 정직하게 적는다: 이건 "목록 없음"이 아니라 **명명 규약에 의존하는 파생**이다.
    ``a1-flower.sh`` 처럼 이름에 ``worker`` 가 없으면 감시망 밖이다. 그래서 실패
    메시지에 규약을 적어, 새 워커를 만드는 사람이 규약을 알게 한다.
    """
    found = sorted(
        p
        for p in SCRIPTS_DIR.glob(WORKER_SCRIPT_GLOB)
        if WORKER_SCRIPT_TOKEN in p.name and p.name != ALIGN_SCRIPT.name
    )
    # 공허진리 가드 — 0개면 아래 "전부 배선됐다"가 자동으로 참이 된다.
    assert len(found) >= 2, (
        f"워커 정렬 스크립트를 {len(found)}개만 찾았다 — 파생 규칙이 낡았을 수 있다. "
        f"규약: {SCRIPTS_DIR.name}/{WORKER_SCRIPT_GLOB} 이면서 파일명에 "
        f"'{WORKER_SCRIPT_TOKEN}' 포함. 찾은 것: {[p.name for p in found]}"
    )
    return found


def _celery_alignment_script() -> Path:
    """celery 정렬 스크립트를 **파생**시킨다 — 스텁의 상태 전이 키를 리터럴로 박지 않는다.

    ★초판은 marker 이름을 ``"a1-backend-workers.sh.called"`` 로 하드코딩했다. 그래서
    명명 규약을 지킨 정상 리네임에도 테스트가 깨졌고, 실패 메시지가 **엉뚱한 곳**
    (정렬 진입점)을 지목했다 — 목록형을 없애려고 만든 테스트 안에 목록이 하나 남아
    오진까지 유발한 것이다(리뷰가 리네임 변이로 실증).
    """
    celery = [p for p in _worker_alignment_scripts() if "arq" not in p.name]
    assert len(celery) == 1, (
        f"celery 정렬 스크립트를 하나로 특정하지 못했다: {[p.name for p in celery]}"
    )
    return celery[0]


def _run_align(
    tmp_path: Path,
    *,
    initially_aligned: bool = False,
    partial_restart: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, list[Path]]:
    """정렬 진입점을 스텁과 함께 실제로 돌린다.

    docker 스텁은 **상태를 가진다**. 그래야 "드리프트 감지 → 재생성 → 사후 확인"이
    실제로 태워진다(늘 최신을 주면 재생성 분기가 아예 안 돌아 검사가 공허해진다).

    - 기본: 정렬 전 구 ID · celery 정렬이 돈 뒤 신 ID  → 정상 흐름
    - ``initially_aligned``: 처음부터 신 ID       → no-op 경로(재시작 안 함)
    - ``partial_restart``: 정렬 뒤에도 일부만 신 ID → 부분 재시작(버전 혼재)
    """
    sandbox = tmp_path / "scripts"
    sandbox.mkdir()
    shutil.copy2(ALIGN_SCRIPT, sandbox / ALIGN_SCRIPT.name)

    targets = _worker_alignment_scripts()
    celery_marker = sandbox / f"{_celery_alignment_script().name}.called"
    for script in targets:
        marker = sandbox / f"{script.name}.called"
        (sandbox / script.name).write_text(
            f"#!/usr/bin/env bash\ntouch {marker}\nexit 0\n", encoding="utf-8"
        )
        (sandbox / script.name).chmod(0o755)

    if initially_aligned:
        container_branch = 'echo "sha256:NEWNEWNEWNEW"'
    elif partial_restart:
        # 재생성 뒤에도 worker 만 신 이미지 — beat·flower 는 구 이미지로 남는다.
        container_branch = (
            f'if [ -f "{celery_marker}" ] && [ "$2" = "propai-celery-worker" ]; then '
            'echo "sha256:NEWNEWNEWNEW"; else echo "sha256:OLDOLDOLDOLD"; fi'
        )
    else:
        container_branch = (
            f'if [ -f "{celery_marker}" ]; then echo "sha256:NEWNEWNEWNEW"; '
            'else echo "sha256:OLDOLDOLDOLD"; fi'
        )

    docker_stub = tmp_path / "docker-stub.sh"
    docker_stub.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "image" ] && [ "$2" = "inspect" ]; then echo "sha256:NEWNEWNEWNEW"; exit 0; fi\n'
        'if [ "$1" = "inspect" ]; then\n'
        f"  {container_branch}\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker_stub.chmod(0o755)

    result = subprocess.run(
        ["bash", str(sandbox / ALIGN_SCRIPT.name)],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "DOCKER_BIN": str(docker_stub), "HOME": str(tmp_path)},
    )
    return result, sandbox, targets


def test_배포가_워커_정렬을_부른다() -> None:
    """배포 스크립트가 정렬 진입점을 **명령 위치에서** 부른다."""
    code = _code(DEPLOY_SCRIPT)
    calls = _invocations(code, ALIGN_SCRIPT.name)
    assert calls, (
        f"{DEPLOY_SCRIPT.name} 이 {ALIGN_SCRIPT.name} 를 부르지 않는다 — "
        "배포한 이미지가 워커에 도달하지 않는다(2026-07-22~08-11 에 실제로 그랬다). "
        "★언급이 아니라 호출이어야 한다: 안내 문구에 같은 경로가 적혀 있어도 그것은 "
        "호출이 아니다(변이로 실증됨)"
    )


def test_배포가_트래픽_전환_전에_마이그레이션_게이트를_지난다() -> None:
    """★이 잠금은 **내가 그것을 지웠기 때문에** 생겼다.

    저장소 사본을 서버 실물로 덮어써 "정본화"하면서, 저장소에만 있던
    ``alembic upgrade head`` 게이트가 조용히 사라졌다(리뷰가 적발). 그 게이트는
    코드-스키마 불일치로 로그인이 500 나던 2026-07-15 사고를 막으려고 넣은 것이다.

    순서까지 본다 — 마이그레이션은 **Caddy 전환보다 앞**이어야 한다. 뒤에 있으면
    새 스키마를 요구하는 코드가 이미 트래픽을 받고 있다.
    """
    code = _code(DEPLOY_SCRIPT)
    lines = code.splitlines()
    # ★"alembic upgrade head" 라는 **문자열**이 아니라, 그것을 실제로 **실행하는** 줄을 찾는다.
    #   안내 echo 도 같은 문자열을 담으므로(변이로 실증) 따옴표를 걷어낸 뒤 docker exec 를 본다.
    migrate_at = next(
        (
            i
            for i, ln in enumerate(lines)
            if "alembic upgrade head" in ln and "docker exec" in _strip_quoted(ln)
        ),
        None,
    )
    assert migrate_at is not None, (
        "배포가 alembic upgrade head 를 **실행**하지 않는다 — 새 코드가 요구하는 스키마 없이 "
        "트래픽이 전환된다(2026-07-15 사고). 한 번 조용히 삭제된 적이 있다. "
        "★안내 문구만 있는 것은 게이트가 아니다"
    )
    switch_at = next((i for i, ln in enumerate(lines) if "caddy reload" in ln.lower()), None)
    assert switch_at is not None, "Caddy 전환 지점을 찾지 못했다 — 패턴이 낡았을 수 있다"
    assert migrate_at < switch_at, (
        f"마이그레이션(줄 {migrate_at})이 트래픽 전환(줄 {switch_at}) 뒤에 있다 — "
        "새 스키마를 요구하는 코드가 이미 트래픽을 받는다"
    )


def test_포트_판정_폴백이_pipefail_에_죽지_않는다() -> None:
    """★내가 만든 회귀를 잠근다.

    `set -eo pipefail` 을 켠 뒤 이 대입이 그대로 남아 있으면::

        CUR=$(grep -oE 'localhost:[0-9]+' ~/caddy/Caddyfile | grep -oE '[0-9]+' | tail -1)
        [ -z "$CUR" ] && CUR=8000     # ← 도달 불가

    grep 의 '매칭 없음'(exit 1)이 파이프라인 종료코드로 승격되고 `set -e` 가 **이 대입에서**
    배포를 죽인다 — 바로 아래 폴백이, 정확히 그 경우를 위해 있는데 영원히 실행되지 않는다.
    실측: 종전은 `CUR=8000` 도달(exit 0), pipefail 은 **메시지 없이 exit 1**.
    """
    code = _code(DEPLOY_SCRIPT)
    has_pipefail = re.search(r"^\s*set\s+-[a-z]*o\s+pipefail|^\s*set\s+-o\s+pipefail", code, re.M)
    port_lines = [ln for ln in code.splitlines() if re.search(r"^\s*CUR=\$\(", ln)]
    assert port_lines, "포트 판정 대입을 찾지 못했다 — 패턴이 낡았을 수 있다"
    if has_pipefail:
        assert any("|| true" in ln for ln in port_lines), (
            "pipefail 을 켠 채 포트 판정 대입이 면제되지 않았다 — Caddyfile 에 "
            "localhost:<포트> 가 없으면 배포가 메시지 없이 죽고 폴백이 도달 불가가 된다. "
            f"해당 줄: {port_lines}"
        )


def test_마이그레이션_게이트가_실패하면_배포가_멈춘다() -> None:
    """★게이트의 존재 이유는 **fail-closed** 다 — 그것을 잠근다.

    앞 테스트는 "alembic 을 실행하는 줄이 전환보다 앞인가"만 본다. 그 줄이 **실패했을 때
    배포를 멈추는가**는 보지 않았고, 그래서 `… || true` 를 붙이면 초록인 채로
    2026-07-15 사고 방어가 사라졌다(리뷰 변이 실증).
    """
    code = _code(DEPLOY_SCRIPT)
    lines = code.splitlines()
    at = next(
        i
        for i, ln in enumerate(lines)
        if "alembic upgrade head" in ln and "docker exec" in _strip_quoted(ln)
    )
    line = lines[at]
    assert "|| true" not in line and "||true" not in line, (
        f"마이그레이션 실패가 무시된다(fail-open): {line.strip()}"
    )
    # 실패 경로가 배포를 중단하는가 — 같은 if 블록 안에서 exit 을 찾는다.
    window = "\n".join(lines[at : at + 4])
    assert re.search(r"\bexit\s+1\b", window), (
        "마이그레이션 실패 시 배포를 중단하지 않는다 — 새 스키마 없이 트래픽이 전환된다. "
        f"검사 구간:\n{window}"
    )


def test_빌드_실패가_은폐되지_않는다() -> None:
    """``git pull … | tail`` · ``docker build … | tail`` 은 tail 의 종료코드를 쓴다.

    ``set -e`` 만으로는 **빌드가 실패해도 배포가 계속되고** 옛 이미지로 스왑한 뒤
    "완료"를 찍는다. 이 저장소가 이미 문서화한 은폐 결함이고, 서버 실물에 그대로 있었다.
    """
    code = _code(DEPLOY_SCRIPT)
    lines = code.splitlines()
    on_at = next(
        (
            i
            for i, ln in enumerate(lines)
            if re.search(r"^\s*set\s+-[a-z]*o\s+pipefail|^\s*set\s+-o\s+pipefail", ln)
        ),
        None,
    )
    assert on_at is not None, (
        "배포 스크립트에 pipefail 이 없다 — `docker build … | tail` 이 실패를 삼켜 "
        "옛 이미지로 스왑한 뒤 성공을 보고한다"
    )
    build_at = next(
        (i for i, ln in enumerate(lines) if "docker build" in _strip_quoted(ln)), None
    )
    assert build_at is not None, "빌드 줄을 찾지 못했다 — 패턴이 낡았을 수 있다"
    assert on_at < build_at, (
        f"pipefail 이 빌드(줄 {build_at})보다 뒤(줄 {on_at})에 켜진다 — 빌드 실패가 그대로 은폐된다"
    )
    # ★그리고 빌드 전에 다시 꺼지지 않았는가. "파일 어딘가에 있는가"만 보면
    #   `set +o pipefail` 한 줄로 은폐가 부활한다(리뷰 변이 실증).
    off = [
        i
        for i, ln in enumerate(lines[on_at:build_at], start=on_at)
        if re.search(r"^\s*set\s+\+[a-z]*o\s+pipefail|^\s*set\s+\+o\s+pipefail", ln)
    ]
    assert not off, f"빌드 전에 pipefail 이 꺼진다(줄 {off}) — 은폐가 되살아난다"


def test_정렬_진입점을_실제로_실행하면_두_워커를_모두_부른다(tmp_path: Path) -> None:
    """★정적 검사가 못 보는 것 — **도달**을 실행으로 확인한다.

    `if false; then bash …; fi` 는 "실행 줄에 있다"를 만족하면서 아무것도 부르지 않는다.
    그래서 정렬 스크립트를 스텁 옆에 복사해 **실제로 돌리고**, 각 워커 스크립트가
    자기 마커를 남겼는지 본다. 도커도 서버도 필요 없다 — 스텁이 즉시 성공하고 끝난다.
    """
    result, sandbox, targets = _run_align(tmp_path)

    미호출 = [s.name for s in targets if not (sandbox / f"{s.name}.called").exists()]
    assert not 미호출, (
        f"{ALIGN_SCRIPT.name} 를 실행했는데 불리지 않은 워커 정렬 스크립트: {미호출}. "
        f"exit={result.returncode} stdout={result.stdout[-400:]!r}"
    )
    assert result.returncode == 0, (
        f"모든 워커 정렬이 성공했는데 진입점이 실패를 돌려줬다(exit={result.returncode}) — "
        f"호출부가 배포를 잘못 경고하게 된다. stderr={result.stderr[-400:]!r}"
    )
    # 공허진리 가드 — 드리프트 분기가 실제로 태워졌는지 확인한다.
    # 스텁이 늘 최신 ID 를 주면 재생성이 아예 안 돌고, 그러면 이 검사가 무의미해진다.
    assert "드리프트" in result.stdout, (
        f"드리프트 경로가 태워지지 않았다 — 스텁이 공허하다. stdout={result.stdout[-400:]!r}"
    )


def test_이미_최신이면_celery_를_재시작하지_않는다(tmp_path: Path) -> None:
    """★재시작은 공짜가 아니다 — 이 분기가 없으면 배포마다 배치가 끊긴다.

    systemd 유닛이 `docker stop -t 10` 이라 SIGTERM 10초 뒤 SIGKILL 이고, warm shutdown 이
    그 안에 못 끝나면 `task_acks_late=True` + Redis 브로커라 미ack 메시지가
    visibility_timeout(기본 1시간) 뒤에야 재전달된다 → 대량필지 배치가 처음부터 다시 돈다.
    arq 는 이미 이미지 ID 가 같으면 no-op 다. celery 도 같아야 한다.
    """
    result, sandbox, targets = _run_align(tmp_path, initially_aligned=True)

    celery = _celery_alignment_script()
    assert not (sandbox / f"{celery.name}.called").exists(), (
        f"이미 최신인데 {celery.name} 를 불렀다 — 매 배포마다 celery 가 재시작되고 "
        f"진행 중 배치가 끊긴다. stdout={result.stdout[-400:]!r}"
    )
    assert result.returncode == 0, f"no-op 경로가 실패를 돌려줬다: {result.stdout[-400:]!r}"


def test_정렬_후_이미지가_안_맞으면_실패로_보고한다(tmp_path: Path) -> None:
    """★부분 재시작이 조용히 남는 것을 잡는다.

    a1-backend-workers.sh 는 worker → flower → beat 순으로 재시작한다(set -e). 중간에서
    실패하면 **beat 는 구 이미지로 남는다** — 그런데 beat 는 이 PR 이 구하려던 태스크들의
    스케줄러다. '재생성했다'가 아니라 '지금 신 이미지로 돌고 있다'를 확인해야 한다.
    """
    result, _sandbox, _targets = _run_align(tmp_path, partial_restart=True)

    assert result.returncode != 0, (
        "정렬 후에도 이미지가 안 맞는데 성공을 돌려줬다 — 버전 혼재가 조용히 남는다. "
        f"stdout={result.stdout[-500:]!r}"
    )
    assert "불일치" in result.stdout, (
        f"어느 컨테이너가 안 맞는지 지목하지 않는다: {result.stdout[-500:]!r}"
    )


def test_정렬_진입점이_모든_워커_스크립트를_부른다() -> None:
    """새 워커 스크립트가 생기면 배선될 때까지 여기서 실패한다(정적·빠른 1차 방어)."""
    align = _code(ALIGN_SCRIPT)
    미배선 = [p.name for p in _worker_alignment_scripts() if not _invocations(align, p.name)]
    assert not 미배선, (
        f"{ALIGN_SCRIPT.name} 가 부르지 않는 워커 정렬 스크립트: {미배선} — "
        "배포가 그 워커에는 닿지 않는다"
    )


def test_arq_헬스체크가_HTTP_상속을_덮고_그_값에_결속된다() -> None:
    """워커는 HTTP 서버가 아니다 — 상속된 curl 헬스체크는 영원히 실패한다.

    실제로 3일 내내 ``unhealthy`` 였고 cron 은 정상 실행 중이었다.
    위양성이 상시화되면 **진짜 장애와 구분되지 않는다**(감시 마비).

    ★그리고 **결속**까지 본다. 첫 판은 ``--health-cmd`` 존재와 기본값만 봐서,
    ``docker run`` 인자만 ``curl -f http://…`` 로 되돌려도 초록이었다(변이 실증) —
    고쳤다고 선언한 그 결함이 가드 아래에서 되살아난다.
    """
    code = _code(ARQ_SCRIPT)

    # ① 기본값이 실제 대상(arq health 키)을 태운다
    defaults = [ln for ln in code.splitlines() if "ARQ_HEALTH_CMD" in ln and ":-" in ln]
    assert defaults, "ARQ_HEALTH_CMD 기본값을 찾지 못했다 — 패턴이 낡았을 수 있다"
    default = defaults[0]
    assert "curl" not in default and "http" not in default.lower(), (
        f"헬스체크를 다시 HTTP 로 걸었다: {default.strip()}"
    )
    assert "--check" in default, (
        f"arq 의 health 키를 읽지 않는다(실제 대상을 태우지 않는다): {default.strip()}"
    )

    # ② docker run 이 **그 변수를** 쓴다 — 리터럴을 박으면 ①이 장식이 된다
    bound = re.search(r'--health-cmd\s+"\$\{?ARQ_HEALTH_CMD\}?"', code)
    assert bound, (
        "--health-cmd 가 $ARQ_HEALTH_CMD 에 결속돼 있지 않다 — 기본값 검사가 장식이 된다. "
        "실제 docker run 인자를 확인하라"
    )


def test_health_키가_빨리_만료돼야_헬스체크가_공허하지_않다() -> None:
    """★이 단언이 없으면 앞의 헬스체크가 **위양성 초록**이 된다.

    arq 는 health 키 만료를 ``health_check_interval + 1`` 초로 건다
    (arq/worker.py: ``psetex(key, (health_check_interval + 1) * 1000, ...)``).
    기본값은 **3600** 이라, 워커가 죽어도 최대 1시간 동안 ``arq --check`` 가 성공한다.

    ★경계는 **양방향**이다. 너무 길면 죽은 워커가 초록이고(위 문단), 너무 짧으면
    루프를 막는 정상 작업(모델 재학습·대용량 IFC 파싱) 중에 **일하는 워커가 빨개진다**.
    상한만 걸었다가 그 반대편을 놓치는 것이 이 저장소의 반복 결함이다.
    """
    src = WORKER_SETTINGS.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    hits = [ln for ln in code.splitlines() if "health_check_interval" in ln]
    assert hits, (
        "WorkerSettings 에 health_check_interval 이 없다 — arq 기본 3600 이면 "
        "죽은 워커도 1시간 동안 헬스체크를 통과한다"
    )
    # 후행 주석·공백을 견딘다(첫 판은 주석 한 줄에 ValueError 로 크래시했다).
    raw = hits[0].split("=", 1)[1].split("#", 1)[0].strip()
    assert raw.isdigit(), (
        f"health_check_interval 이 리터럴 정수가 아니다: {hits[0].strip()!r} — "
        "값이 계산식이면 이 계약을 정적으로 잠글 수 없다"
    )
    value = int(raw)
    assert value <= 600, (
        f"health_check_interval={value}s 는 너무 길다 — 죽은 워커가 "
        f"{value + 1}초 동안 healthy 로 보인다"
    )
    assert value >= 120, (
        f"health_check_interval={value}s 는 너무 짧다 — 이 워커의 태스크는 "
        "이벤트 루프를 막는 동기 작업(model.fit·ifcopenshell.open·doc.build)을 포함하므로, "
        "정상 작업 중에 키가 만료돼 **일하는 워커가 unhealthy** 가 된다"
    )
