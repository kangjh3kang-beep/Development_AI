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

    발각 계기는 PR #601(Celery 배치의 DB 연결 누수 봉합)을 배포하기 전에
    "이 수정이 실제로 누수하는 프로세스에 닿는가"를 확인한 것이다. 닿지 않았다.

    ★그래서 여기서 잠그는 것은 "정렬 스크립트가 존재한다"가 아니라
    **배포 → 정렬 → 개별 워커**의 호출 경로가 실제로 이어져 있다는 것이다.
    존재는 도달을 뜻하지 않는다 — 이 저장소가 반복해서 데인 그 지점이다.
"""

from __future__ import annotations

import re
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PLATFORM_DIR / "scripts"
DEPLOY_SCRIPT = PLATFORM_DIR / "infra" / "deploy-zero-downtime.sh"
ALIGN_SCRIPT = SCRIPTS_DIR / "a1-align-workers.sh"
ARQ_SCRIPT = SCRIPTS_DIR / "a1-arq-worker.sh"
WORKER_SETTINGS = PLATFORM_DIR / "apps" / "worker" / "main.py"


def _code(path: Path) -> str:
    """★주석을 걷어낸 **실행 줄**만 돌려준다.

    소스를 그냥 grep 하면 주석이 코드로 읽힌다. 이 저장소에서 배선 락이 실제로
    ``주석 처리 + 임포트 유지`` 변이에 뚫린 적이 있다. 반대 방향도 중요하다 —
    **주석 안에 적힌 호출은 호출이 아니다**. 이 파일들은 결함의 내력을 주석에
    길게 적어 두므로(예: "종전에는 arq 만 정렬했다"), 주석을 지우지 않으면
    지금은 하지 않는 일을 하고 있다고 오판한다.
    """
    assert path.is_file(), f"배포 자산이 저장소에 없다: {path}"
    raw = path.read_text(encoding="utf-8")
    # 공허진리 방지 — 빈/짧은 파일이면 아래 검사들이 통째로 무의미해진다.
    assert len(raw) > 500, f"내용이 너무 짧다({len(raw)}자) — 검사 대상이 비었을 수 있다: {path}"
    code = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    assert len(code) > 300, f"주석 제거 후 실행 코드가 거의 없다({len(code)}자): {path}"
    return code


def _invocations(code: str, script_name: str) -> list[str]:
    """스크립트를 **실제로 부르는** 줄만 돌려준다.

    ★이 함수는 변이 검증이 만들어 냈다. 처음에는 그냥 ``script_name in code`` 로
    검사했는데, 배포 스크립트에서 **호출을 통째로 지워도 테스트가 초록**이었다 —
    실패 시 안내 문구가 같은 경로를 담고 있었기 때문이다::

        echo "   bash ~/.../scripts/a1-align-workers.sh"   # 안내일 뿐 호출이 아니다

    "언급한다"와 "부른다"는 다르다. 주석을 걷어내는 것만으로는 부족하고,
    **메시지 줄도 배제**해야 이 계약이 도달을 잠근다.
    """
    hits = []
    for line in code.splitlines():
        stripped = line.strip()
        # echo/printf 는 사용자에게 보여 주는 문구다 — 실행 경로가 아니다.
        if re.match(r"^(echo|printf)\b", stripped):
            continue
        # 호출 표기는 여러 형태다: `bash scripts/x.sh` · `bash "$DIR/x.sh"` · `bash x.sh; then`.
        # 경계를 좁게 잡으면 정상 코드를 위반으로 신고한다(실제로 따옴표 형태를 놓쳐
        # 기준선이 빨개졌다 — 가드의 위양성도 결함이다).
        if re.search(rf"""bash\s+\S*{re.escape(script_name)}(\s|$|;|["'])""", stripped):
            hits.append(stripped)
    return hits


def _worker_alignment_scripts() -> list[Path]:
    """정렬 대상 워커 스크립트를 **파생**시킨다(사람이 센 목록을 쓰지 않는다).

    목록을 손으로 적으면 그 목록이 곧 상한이 된다 — 새 워커가 생겨도 목록에 없으면
    감시망 밖이고, 그게 정확히 celery 가 3주간 새어 나간 방식이다.
    ``scripts/`` 에서 워커를 기동/정렬하는 스크립트를 이름으로 걷어, **하나라도
    a1-align-workers.sh 가 부르지 않으면 실패**하게 만든다.
    """
    found = sorted(
        p
        for p in SCRIPTS_DIR.glob("a1-*.sh")
        if "worker" in p.name and p.name != ALIGN_SCRIPT.name
    )
    # 공허진리 가드 — 0개면 아래 "전부 배선됐다"가 자동으로 참이 된다.
    assert len(found) >= 2, (
        f"워커 정렬 스크립트를 {len(found)}개만 찾았다 — 파생 규칙이 낡았을 수 있다. "
        f"찾은 것: {[p.name for p in found]}"
    )
    return found


def test_배포가_워커_정렬을_부른다() -> None:
    """배포 스크립트가 정렬 진입점을 **실행 줄에서** 부른다."""
    code = _code(DEPLOY_SCRIPT)
    calls = _invocations(code, ALIGN_SCRIPT.name)
    assert calls, (
        f"{DEPLOY_SCRIPT.name} 이 {ALIGN_SCRIPT.name} 를 부르지 않는다 — "
        "배포한 이미지가 워커에 도달하지 않는다(2026-07-22~08-11 에 실제로 그랬다). "
        "★언급이 아니라 호출이어야 한다: 실패 안내 문구에 같은 경로가 적혀 있어도 "
        "그것은 호출이 아니다(변이로 실증됨)"
    )


def test_정렬_진입점이_모든_워커_스크립트를_부른다() -> None:
    """새 워커 스크립트가 생기면 배선될 때까지 여기서 실패한다."""
    align = _code(ALIGN_SCRIPT)
    미배선 = [p.name for p in _worker_alignment_scripts() if not _invocations(align, p.name)]
    assert not 미배선, (
        f"{ALIGN_SCRIPT.name} 가 부르지 않는 워커 정렬 스크립트: {미배선} — "
        "배포가 그 워커에는 닿지 않는다"
    )


def test_arq_헬스체크가_HTTP_상속을_덮는다() -> None:
    """워커는 HTTP 서버가 아니다 — 상속된 curl 헬스체크는 영원히 실패한다.

    실제로 3일 내내 ``unhealthy`` 였고 cron 은 정상 실행 중이었다.
    위양성이 상시화되면 **진짜 장애와 구분되지 않는다**(감시 마비).
    """
    code = _code(ARQ_SCRIPT)
    assert "--health-cmd" in code, (
        f"{ARQ_SCRIPT.name} 가 --health-cmd 로 헬스체크를 덮지 않는다 — "
        "API 이미지의 HTTP 헬스체크를 상속해 워커가 멀쩡해도 unhealthy 가 된다"
    )
    # 덮되 **같은 실수를 반복하지 않는지**까지 본다(HTTP 로 덮으면 고친 게 아니다).
    health_lines = [ln for ln in code.splitlines() if "ARQ_HEALTH_CMD" in ln and ":-" in ln]
    assert health_lines, "ARQ_HEALTH_CMD 기본값을 찾지 못했다 — 패턴이 낡았을 수 있다"
    default = health_lines[0]
    assert "curl" not in default and "http" not in default.lower(), (
        f"헬스체크를 다시 HTTP 로 걸었다: {default.strip()}"
    )
    assert "--check" in default, (
        f"arq 의 health 키를 읽지 않는다(실제 대상을 태우지 않는다): {default.strip()}"
    )


def test_health_키가_빨리_만료돼야_헬스체크가_공허하지_않다() -> None:
    """★이 단언이 없으면 앞의 헬스체크가 **위양성 초록**이 된다.

    arq 는 health 키 만료를 ``health_check_interval + 1`` 초로 건다
    (arq/worker.py: ``psetex(key, (health_check_interval + 1) * 1000, ...)``).
    기본값은 **3600** 이라, 워커가 죽어도 최대 1시간 동안 ``arq --check`` 가 성공한다.
    즉 주기를 낮추지 않으면 "빨강이 안 뜨는 헬스체크"를 만든 것이다 —
    종전의 "영원한 빨강"과 방향만 반대인 같은 결함이다.
    """
    src = WORKER_SETTINGS.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    hits = [ln for ln in code.splitlines() if "health_check_interval" in ln]
    assert hits, (
        "WorkerSettings 에 health_check_interval 이 없다 — arq 기본 3600 이면 "
        "죽은 워커도 1시간 동안 헬스체크를 통과한다"
    )
    value = int(hits[0].split("=")[1].strip())
    assert value <= 300, (
        f"health_check_interval={value}s 는 너무 길다 — 죽은 워커가 "
        f"{value + 1}초 동안 healthy 로 보인다"
    )
