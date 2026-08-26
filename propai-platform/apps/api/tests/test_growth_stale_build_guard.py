"""낡은 스택의 성장루프 쓰기 차단 — **3축을 각각** 잠근다.

★왜 3축인가(2026-08-24 교훈): **탐지만 잠그면 "항상 거부"가 만점을 받는다.**
  전부 빨간 가드는 곧 꺼지므로, 정상 케이스를 통과시키는 **특이도**를 따로 잠근다.
  그리고 가드가 있어도 **아무도 안 부르면** 무의미하므로 **배선**을 또 따로 잠근다.

★특이도 초록은 공짜다 — 아무것도 안 하는 가드도 특이도는 만족한다. 그래서 각 특이도
  케이스에서 **실제로 판정이 일어났는지**(사유 문자열이 그 근거를 말하는지)를 함께 단언한다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.growth import analyzer as az
from app.services.growth import stale_build_guard as g

# apps/api/tests/<this> → parents[1] = apps/api (기존 계약 테스트와 같은 규약).
_API = Path(__file__).resolve().parents[1]
_MAIN = _API / "main.py"
_ANALYZER = _API / "app" / "services" / "growth" / "analyzer.py"


# ─────────────────────────────────────────────────────────────────────
# 축① 탐지 — 낡은 스택을 실제로 잡는가
# ─────────────────────────────────────────────────────────────────────
def test_detect_missing_build_id_is_refused(monkeypatch):
    """실측 재현: 158 의 옛 컨테이너는 APP_BUILD_ID 가 **미설정**이었다."""
    monkeypatch.delenv(g.BUILD_ID_ENV, raising=False)
    monkeypatch.delenv(g.DISABLE_ENV, raising=False)
    allowed, why = g.growth_writes_allowed()
    assert allowed is False
    # ★무언 거부 금지 — 사유가 **어느 환경변수 때문인지** 말해야 한다.
    assert g.BUILD_ID_ENV in why, why
    assert g.DISABLE_ENV in why, "해제 방법을 알려주지 않으면 운영자가 막힌다"


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_detect_blank_build_id_is_refused(monkeypatch, blank):
    """공백 문자열도 '없음'이다 — 빈 ENV 주입으로 게이트를 통과시킬 수 없다."""
    monkeypatch.setenv(g.BUILD_ID_ENV, blank)
    monkeypatch.delenv(g.DISABLE_ENV, raising=False)
    assert g.growth_writes_allowed()[0] is False


# ─────────────────────────────────────────────────────────────────────
# 축② 특이도 — 정상 스택을 막지 않는가 (★"항상 거부"가 만점 받지 못하게)
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bid", [
    "propai-v002765-08ca697e",   # 실측: 158 web
    "propai-v002760-907a3513",   # 실측: 168 api
    "dev-local",
])
def test_specificity_current_build_is_allowed(monkeypatch, bid):
    monkeypatch.setenv(g.BUILD_ID_ENV, bid)
    monkeypatch.delenv(g.DISABLE_ENV, raising=False)
    allowed, why = g.growth_writes_allowed()
    assert allowed is True
    # ★이 단언이 핵심이다: 그냥 통과한 게 아니라 **그 빌드를 보고** 통과했음을 확인한다.
    #   (사유를 안 보면 "게이트가 아예 안 돌았다"와 구별되지 않는다 — skip 통과는 통과가 아니다.)
    assert bid in why, f"판정 근거에 빌드 식별자가 없다: {why!r}"


def test_escape_hatch_says_it_is_an_escape_hatch(monkeypatch):
    monkeypatch.delenv(g.BUILD_ID_ENV, raising=False)
    monkeypatch.setenv(g.DISABLE_ENV, "1")
    allowed, why = g.growth_writes_allowed()
    assert allowed is True
    assert g.DISABLE_ENV in why, "해제로 통과했음을 사유가 말해야 한다(조용한 우회 금지)"


def test_escape_hatch_only_accepts_exact_1(monkeypatch):
    """'true'·'yes' 같은 오타로 게이트가 꺼지지 않는다(양방향 경계)."""
    monkeypatch.delenv(g.BUILD_ID_ENV, raising=False)
    for v in ("0", "true", "yes", "on", ""):
        monkeypatch.setenv(g.DISABLE_ENV, v)
        assert g.growth_writes_allowed()[0] is False, f"{v!r} 로 게이트가 꺼졌다"


# ─────────────────────────────────────────────────────────────────────
# 축③ 배선 — 스케줄러가 **실제로** 이 게이트를 지나는가
# ─────────────────────────────────────────────────────────────────────
def test_wired_into_the_single_choke_point():
    """모든 성장 잡(analyze/heal/correct/learn/improve)은 `_growth_run_locked` 를 지난다.

    ★소스 검사지만 **주석·문자열을 걷어낸 실행 라인만** 본다 —
      "주석처리 + 임포트 유지" 변이에 이 저장소가 두 번 뚫린 적이 있다.
    """
    from tests._scan_guard import code_lines, read, scan

    src = read(_MAIN, must_exist_reason="성장 인프로세스 스케줄러가 사는 파일")
    code = code_lines(src)

    # 게이트 호출이 실행 라인에 있는가.
    r = scan(
        code,
        pattern=r"growth_writes_allowed\s*\(",
        positive_control=r"_growth_run_locked",   # ★이 함수가 없으면 파일을 잘못 읽은 것
        where=str(_MAIN),
    )
    assert r.hits, "게이트 호출이 실행 라인에 없다(주석 처리되었거나 배선이 빠졌다)"

    # ★게이트가 lock **앞**에 있어야 한다 — 뒤에 있으면 낡은 스택이 이미 워터마크를 옮긴다.
    gate = code.index("growth_writes_allowed")
    lock = code.index("_GROWTH_LOCK_KEYS[job_name]")
    assert gate < lock, "게이트가 advisory lock 획득 뒤에 있다(순서가 무의미해진다)"


def test_all_growth_jobs_go_through_the_locked_runner():
    """길목이 하나임을 잠근다 — 잡이 늘어도 자동으로 게이트를 지나야 한다.

    ★목록형이 아니라 **파생형**: `_GROWTH_LOCK_KEYS` 에서 잡 이름을 뽑아, 그 각각이
      `_growth_run_locked(` 로 호출되는지 본다. 새 잡을 키에만 추가하고 우회 호출하면 잡힌다.
    """
    from tests._scan_guard import code_lines, read

    code = code_lines(read(_MAIN, must_exist_reason="성장 스케줄러"))
    keys = re.findall(r'"(\w+)":\s*911_000_\d+', code)
    assert len(keys) >= 5, f"잡 이름 추출 실패(추출={keys}) — 파서가 죽었다"
    missing = [k for k in keys
               if not re.search(rf'_growth_run_locked\(\s*"{re.escape(k)}"', code)]
    assert not missing, f"게이트를 안 지나는 잡: {missing}"


# ─────────────────────────────────────────────────────────────────────
# 불변식 — 구조적 불가능 행이 만들어질 수 없다
# ─────────────────────────────────────────────────────────────────────
def test_latency_regression_never_pairs_with_info_severity():
    """실측(2026-08-25): 24h 에 `type=latency_regression` + `severity=info` 가 **129건**.

    현행 코드로는 만들 수 없는 조합이다(`severity = sev or "info"` 이고
    `insight_type = latency_regression iff sev`). 129건은 **낡은 스택**이 쓴 것이었다.
    이 테스트는 **현행 생산자**가 그 조합을 못 만든다는 것을 잠근다.
    """
    seen = set()
    for sev in (None, "", "warn", "critical"):
        t = az.insight_type_for_latency(sev)
        stored_sev = sev or "info"
        seen.add((t, stored_sev))
        assert not (t == "latency_regression" and stored_sev == "info"), (
            f"구조적 불가능 행이 생성 가능하다: sev={sev!r} → ({t}, {stored_sev})"
        )
    # ★공허 진리 방지: 두 타입이 **실제로 둘 다** 나왔는지 확인한다.
    #   한쪽만 나오면 위 단언은 자동으로 참이 되어 아무것도 잠그지 않는다.
    types = {t for t, _ in seen}
    assert types == {"latency_regression", "latency_baseline"}, (
        f"두 모집단이 갈리지 않았다: {types} — 이 픽스처는 잠금이 아니다"
    )


def test_producer_stamp_is_type_agnostic(monkeypatch):
    """생산자 표식은 **모든 인사이트 타입**에 붙는다(타입별 손수 분기 금지).

    ★왜: 낡은 스택이 쓴 행을 특정하는 데 `created_at` 초 단위 지문을 써야 했다.
      그 우회는 다음 사람이 못 한다.
    """
    monkeypatch.setenv(g.BUILD_ID_ENV, "propai-vTEST-abc1234")
    from tests._scan_guard import code_lines, read

    src = read(_ANALYZER, must_exist_reason="인사이트 INSERT 가 사는 파일")
    code = code_lines(src)
    assert "producer_build_id" in code, "생산자 표식이 실행 라인에 없다"
    # ★타입별 분기 안이 아니라 **공통 INSERT 경로**에 있어야 한다.
    stamp = code.index("producer_build_id")
    insert = code.index("INSERT INTO platform_insights")
    assert abs(stamp - insert) < 1200, (
        "생산자 표식이 공통 INSERT 경로에서 멀다 — 타입별 분기에 박혔을 수 있다"
    )
    assert g.running_build_id() == "propai-vTEST-abc1234"
