"""탁상감정 채택가·신뢰도의 **결정성**과 **신뢰도 계약**을 잠근다.

★라이브 실측 결함(2026-08-25) — `desk_appraisal_service` 의 교차검증 모사 블록이

    seed = abs(hash((pnu or address or "") + str(int(op)))) % (2**31)

로 시드를 만들었다. CPython 은 `PYTHONHASHSEED` 가 **설정되지 않으면** str `hash()` 를
**프로세스마다 솔팅**한다. 프로덕션 168 컨테이너에서 `printenv PYTHONHASHSEED` 는 **빈 값**
이었다(실측). 따라서 같은 필지가 **재시작할 때마다 다른 감정가**를 받았다.

측정(원문 소스 410–424·448행을 그대로 exec · PYTHONHASHSEED 1..40 의 실제 hash()):
  · 거래사례 없음 경로 채택단가 진폭 **5.66%**
  · 라이브 논현동 1-1 1,000㎡ = 총액 6,255,771,000원 → **재시작마다 약 3.5억원 이동**
  · 그리고 `rough_feasibility_orchestrator:813` 이 이 값을 **수지 토지비**로 쓴다

★**왜 아무도 못 봤나**: 한 프로세스 안에서는 완벽히 결정적이다(라이브 8/8 동일).
값이 갈리는 순간은 **재시작 직후**뿐이라, 반복 호출하는 어떤 테스트도 초록이었다.
→ 그래서 이 파일은 **반드시 서로 다른 `PYTHONHASHSEED` 하위프로세스**에서 재야 한다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parents[1]
_SERVICE = _API_ROOT / "app" / "services" / "land_intelligence" / "desk_appraisal_service.py"

# 두 모집단을 가르는 입력 — 거래사례 **없음**(단일 경로) / **있음**(두 방법)
_COMMON = dict(pnu="1168010800100010001", address="", area_sqm=500.0,
               official_price_per_sqm=15_000_000)

_RUNNER = """
import asyncio, json, sys
from app.services.land_intelligence.desk_appraisal_service import desk_appraisal
kw = json.loads(sys.argv[1])
r = asyncio.run(desk_appraisal(**kw))
cc = r.get("cross_check") or {}
print(json.dumps({
    # ★대조군: 이 프로세스의 hash 솔트가 실제로 다른지 스스로 신고한다.
    #   이게 프로세스마다 같으면 아래 '동일하다' 단언은 **공허한 참**이다.
    "hash_probe": abs(hash("propai-determinism-probe")) % (2**31),
    "unit": r.get("appraised_price_per_sqm"),
    "total": r.get("appraised_total_won"),
    "confidence": r.get("confidence"),
    "range": r.get("range_per_sqm"),
    "cv_pct": cc.get("cv_pct"),
    "scenarios": cc.get("firms"),
    "note": cc.get("note"),
    "confidence_basis": r.get("confidence_basis") or r.get("confidence_reason"),
}, ensure_ascii=False))
"""


def _run(hash_seed: str, **overrides) -> dict:
    kw = {**_COMMON, **overrides}
    proc = subprocess.run(
        [sys.executable, "-c", _RUNNER, json.dumps(kw)],
        cwd=str(_API_ROOT), capture_output=True, text=True,
        # ★환경은 **상속**하고 PYTHONHASHSEED 만 덮는다. 손수 구성했더니 `apps.*` 임포트가
        #   깨져 테스트가 **엉뚱한 이유로 빨갛게** 됐다 — 그건 탐지가 아니다.
        env={**os.environ, "PYTHONHASHSEED": hash_seed,
             "PYTHONPATH": os.pathsep.join([str(_API_ROOT), str(_API_ROOT.parents[1])])},
        timeout=180,
    )
    if proc.returncode != 0:
        pytest.fail(f"하위프로세스 실패(PYTHONHASHSEED={hash_seed})\n{proc.stderr[-2000:]}")
    line = [ln for ln in proc.stdout.strip().splitlines() if ln.startswith("{")]
    assert line, f"산출 없음 — 조회기가 죽었다\nstdout={proc.stdout[-800:]}"
    return json.loads(line[-1])


@pytest.mark.parametrize("with_cmp", [False, True], ids=["거래사례없음", "거래사례있음"])
def test_appraisal_is_deterministic_across_process_hash_seeds(with_cmp: bool) -> None:
    """같은 입력이면 **프로세스가 달라도** 같은 채택가·신뢰도를 내야 한다."""
    extra = {"comparable_avg_per_sqm": 18_000_000} if with_cmp else {}
    runs = [_run(s, **extra) for s in ("1", "77", "31337")]

    # ── 공허진리 가드 ①: hash 솔트가 실제로 갈렸는가(안 갈리면 이 테스트는 무의미) ──
    probes = {r["hash_probe"] for r in runs}
    assert len(probes) == len(runs), (
        f"PYTHONHASHSEED 가 hash() 를 안 갈랐다 — 이 테스트는 **공허한 참**이다. probes={probes}"
    )
    # ── 공허진리 가드 ②: 잴 값이 실제로 있는가 ──
    assert all(r["unit"] for r in runs), f"채택단가가 비었다 — 잠글 대상이 없다: {runs}"

    for key in ("unit", "total", "range", "cv_pct", "scenarios"):
        vals = [r[key] for r in runs]
        assert all(v == vals[0] for v in vals), (
            f"**프로세스마다 {key} 가 다르다** — 같은 필지의 감정가가 재시작마다 바뀐다.\n"
            f"  근본: seed 를 str hash() 에서 뽑는데 PYTHONHASHSEED 가 프로덕션에서 미설정.\n"
            f"  값={vals}"
        )


def test_confidence_is_withheld_when_only_one_independent_method() -> None:
    """거래사례가 없으면 **독립 추정이 1개** — 교차검증이 아니므로 신뢰도를 말하면 안 된다.

    ★계획서 §P-3 의 방침: *정답이 '값'이 아니라 '보류'일 수 있다.*
    종전엔 `1 - cv*3` 로 **자기가 주입한 난수의 분산**에서 0.92 를 만들어 냈다.
    """
    single = _run("1")
    assert single["unit"], "채택단가가 비었다 — 아래 단언이 공허해진다"
    assert single["confidence"] is None, (
        "독립 추정이 1개(공시지가 기준법 단독)인데 신뢰도를 숫자로 단정한다 — "
        f"그 숫자는 주입한 난수의 변동계수다. confidence={single['confidence']}"
    )
    assert single["confidence_basis"], "신뢰도를 보류했으면 **사유**를 말해야 한다(무언 보류 금지)"


def test_confidence_contract_splits_two_populations() -> None:
    """★픽스처가 두 모집단을 갈라야 한다 — 둘이 같으면 배선을 끊어도 결과가 같다."""
    single = _run("1")
    dual = _run("1", comparable_avg_per_sqm=18_000_000)
    assert single["unit"] and dual["unit"], "두 경로 다 값이 있어야 대조가 성립한다"
    assert single["confidence"] is None and dual["confidence"] is not None, (
        "단일 경로와 두 방법 경로가 **같은 신뢰도 계약**을 낸다 — "
        f"단일={single['confidence']} 이중={dual['confidence']}"
    )


def test_appraisal_source_has_no_random_number_generator() -> None:
    """구조 락 — 감정 산출 경로에 난수가 **없어야** 한다(주석·문자열 제외)."""
    sys.path.insert(0, str(_API_ROOT.parents[1] / "tests"))
    from _scan_guard import assert_absent, code_lines, read  # noqa: PLC0415

    src = code_lines(read(_SERVICE, must_exist_reason="탁상감정 서비스가 사라졌다"))
    assert_absent(
        src,
        pattern=r"\brandom\b|\.uniform\(|Random\(",
        # 대조군: 이 파일에 반드시 있는 것 — 없으면 경로·정규식이 틀린 것이다
        positive_control=r"async def desk_appraisal",
        reason=("감정 산출에 난수가 남아 있다 — 채택가가 프로세스마다 달라지고 "
                "신뢰도가 '자기가 주입한 잡음'에서 나온다"),
        where=str(_SERVICE),
    )


def test_confidence_actually_tracks_the_two_methods_disagreement() -> None:
    """신뢰도가 **상수가 아니라** 두 독립 추정의 불일치를 실제로 따라가야 한다.

    ★위 `test_confidence_contract_splits_two_populations` 는 "이중 경로면 숫자가 있다"만
    본다 — 그래서 `confidence = 0.9` 같은 **상수로 바꿔도 통과**한다(변이 생존 지점).
    여기서는 **불일치가 큰 쪽이 더 낮은 신뢰도**를 내는지 본다.
    """
    near = _run("1", comparable_avg_per_sqm=15_500_000)   # 공시지가 경로와 가까움
    far = _run("1", comparable_avg_per_sqm=60_000_000)    # 크게 어긋남
    assert near["confidence"] is not None and far["confidence"] is not None, (
        "두 경로 다 신뢰도가 있어야 대조가 성립한다"
    )
    assert far["confidence"] < near["confidence"], (
        "두 방법이 크게 어긋나는데 신뢰도가 낮아지지 않는다 — 신뢰도가 증거를 안 따라간다.\n"
        f"  가까움={near['confidence']} 어긋남={far['confidence']}"
    )


def test_assumption_band_is_non_degenerate_and_contains_adopted_value() -> None:
    """가정 봉투가 **폭을 가져야** 하고 채택가를 품어야 한다.

    ★가정 폭을 0 으로 접어도(`_OF_STEPS` 를 전부 0.0 으로) 결정성 테스트는 **여전히 초록**
    이다(결정적이긴 하니까). 그러면 화면의 ± 범위가 한 점으로 붕괴한다 — 그건 "범위 없음"을
    "범위"라고 말하는 것이다. 상한·하한은 한 쌍이다(§19).
    """
    for label, extra in (("단일", {}), ("이중", {"comparable_avg_per_sqm": 18_000_000})):
        r = _run("1", **extra)
        lo, hi = r["range"]["low"], r["range"]["high"]
        assert lo < hi, f"[{label}] 가정 범위가 한 점으로 붕괴했다: low={lo} high={hi}"
        assert lo <= r["unit"] <= hi, (
            f"[{label}] 채택가가 자기 가정 범위 밖이다: unit={r['unit']} range=({lo},{hi})"
        )
        assert len(r["scenarios"]) >= 3, f"[{label}] 시나리오가 {len(r['scenarios'])}개뿐"
