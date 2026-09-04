"""`insight_type` 카탈로그가 **실제 산출과 갈라지면 잡는다** (2026-08-24).

## 배경 — 목록 7 vs 실제 11

인사이트는 여러 모듈이 각자 INSERT 하는데(`analyzer` · `heal_actions` · `healing_rules` ·
`improvement_agent`), 화면은 **손으로 쓴 라벨 표**로 그것을 한글로 옮긴다.
실측 결과 백엔드 **11종** vs 화면 표 **7종**이었고, 그 7종 중 **3종은 백엔드가 한 번도
내보내지 않는 유령**(`funnel`·`usage_pattern`·`churn_risk`)이었다.

즉 **7종이 라벨 없이 raw 문자열로** 떴다 — 그중 `heal_escalation` 은
*"자동치유 무효 · 사람 점검 필요"* 라는 **critical** 이다.

★규율 §A-4: *"목록형이 아니라 전수/파생형으로 쓴다 — 사람이 센 목록이 곧 상한이 된다."*

## 이 파일이 잠그는 것

소스를 **스윕해서** 실제 리터럴을 뽑고 카탈로그와 대조한다. 새 타입을 추가하면서
카탈로그에 안 넣으면 여기서 빨개진다(그러면 화면 락도 함께 걸린다).
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.services.growth.insight_types import INSIGHT_TYPES  # noqa: E402

_GROWTH_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "services", "growth")

# ── 방향 ① 소스 → 카탈로그 (엄격 패턴) ─────────────────────────────────────
# ★첫 작성에서 이 패턴이 **불완전해 '없는 유령' 4건을 만들었다**(도구 출력이 원문과 달랐다).
#   실제 표기는 넷이다:
#     ① "insight_type": "error_cluster"          (dict 리터럴 — analyzer)
#     ② insight_type='improvement_proposal'      (키워드 인자 / SQL where)
#     ③ VALUES (:tid, 'stale_reanalysis', ...)   (인라인 SQL — 리터럴이 **첫 값이 아니다**)
#     ④ INSIGHT_PROMPT_CANDIDATE = "prompt_candidate"  ·  return "latency_baseline"
_PATTERNS = (
    re.compile(r'"insight_type"\s*:\s*"([a-z_]+)"'),
    re.compile(r"insight_type\s*=\s*['\"]([a-z_]+)['\"]"),
    re.compile(r"^\s*INSIGHT_[A-Z_]*\s*=\s*['\"]([a-z_]+)['\"]", re.M),
    # `LATENCY_BASELINE_SOURCE_TYPES = ("latency_regression", "latency_baseline")`
    re.compile(r"^[A-Z_]+_TYPES\s*=\s*\(([^)]*)\)", re.M),
)
# INSERT INTO platform_insights ... VALUES( ... ) 안의 **모든** 따옴표 리터럴.
_VALUES_BLOCK = re.compile(r"INSERT INTO platform_insights[\s\S]{0,800}?VALUES\s*\(([\s\S]{0,400}?)\)")
_QUOTED = re.compile(r"'([a-z_]+)'")

# 스윕이 집어도 **타입 리터럴이 아닌** 것(컬럼명·상태값·recommended_action 등).
_NOT_A_TYPE = frozenset({
    "created_at", "insight_type", "open", "acknowledged", "dismissed", "acted",
    "heal", "none", "correct", "propose_pr", "critical", "warn", "info",
})


def _strip_comments(src: str) -> str:
    """줄 주석을 제거한다 — 주석에 적은 예시가 '실제 산출'로 세어지면 안 된다."""
    return "\n".join(re.sub(r"(^|\s)#.*$", r"\1", ln) for ln in src.splitlines())


def _sources() -> dict[str, str]:
    """growth 패키지 소스(카탈로그 자신은 제외 — 넣으면 모든 대조가 공허해진다)."""
    out: dict[str, str] = {}
    for name in sorted(os.listdir(_GROWTH_DIR)):
        if not name.endswith(".py") or name == "insight_types.py":
            continue
        with open(os.path.join(_GROWTH_DIR, name), encoding="utf-8") as fh:
            out[name] = _strip_comments(fh.read())
    return out


def _sweep() -> dict[str, set[str]]:
    """엄격 패턴으로 발견한 insight_type 리터럴 → 발견 파일 집합."""
    found: dict[str, set[str]] = {}
    for name, src in _sources().items():
        lits: set[str] = set()
        for pat in _PATTERNS:
            for m in pat.finditer(src):
                # 튜플 패턴은 그룹이 "a", "b" 형태의 목록이라 안에서 다시 뽑는다.
                g = m.group(1)
                lits.update(re.findall(r"['\"]([a-z_]+)['\"]", g) or ([g] if re.fullmatch(r"[a-z_]+", g) else []))
        for blk in _VALUES_BLOCK.finditer(src):
            lits.update(m.group(1) for m in _QUOTED.finditer(blk.group(1)))
        for lit in lits - _NOT_A_TYPE:
            found.setdefault(lit, set()).add(name)
    return found


# ── 방향 ② 카탈로그 → 소스 (느슨한 언급 검사) ──────────────────────────────
# ★엄격 패턴으로 역방향을 보면 **표기 하나 놓칠 때마다 없는 유령을 만든다**(실제로 겪었다).
#   역방향의 목적은 하나뿐이다 — **죽은 카탈로그 항목**(산출부가 없는 이름) 적발.
#   그래서 "growth 패키지 어딘가에 그 리터럴이 나타나는가"만 본다. 이것으로 충분히
#   `funnel`·`usage_pattern`·`churn_risk` 같은 유령이 걸린다.
def _mentioned(lit: str) -> bool:
    needle_d, needle_s = f'"{lit}"', f"'{lit}'"
    return any(needle_d in src or needle_s in src for src in _sources().values())


# ★★**잔여 한계(의도적 미잠금 — 적어 둔다)**
#   엄격 스윕은 위 다섯 표기만 본다. 새 타입을 **함수 안 bare `return "x"`** 로만 만들면
#   방향①이 놓친다(현재 `insight_type_for_latency` 가 그 형태인데, 그 둘은 같은 파일의
#   `LATENCY_BASELINE_SOURCE_TYPES` 튜플에 함께 적혀 있어 잡힌다).
#   그때도 **방향②(느슨한 언급 검사)와 화면 락**은 여전히 걸리므로 raw 노출까지 가지는 않는다.
#   이 한계를 모르면 "전수 감사했다"고 착각하게 된다.


def test_A_스윕이_비어있지_않다_공허한_초록_방지():
    """★이 가드가 단언 **앞에** 있어야 한다 — 정규식이 깨져 0건이면 아래가 공허하게 참이다."""
    found = _sweep()
    assert len(found) >= 8, f"스윕 결과가 너무 적다({len(found)}) — 정규식이 낡았다: {sorted(found)}"
    # 소스 자체가 비면 역방향도 공허하게 참이 된다.
    assert len(_sources()) >= 5, "growth 소스를 못 읽었다"


def test_B_소스에_있는_타입은_모두_카탈로그에_있다():
    """새 타입을 추가하면서 카탈로그에 안 넣으면 **화면이 raw 로 뜬다.**"""
    found = _sweep()
    missing = {k: sorted(v) for k, v in found.items() if k not in INSIGHT_TYPES}
    assert not missing, (
        f"소스가 내보내는데 카탈로그에 없는 insight_type: {missing}\n"
        f"→ app/services/growth/insight_types.py 에 추가하라(화면 라벨도 함께 걸린다)."
    )


def test_C_카탈로그에만_있고_소스에_없는_유령은_없다():
    """유령 항목은 화면에 **영원히 안 뜨는 라벨**을 만들고, 목록을 신뢰할 수 없게 한다.

    ★실제로 화면 표에 `funnel`·`usage_pattern`·`churn_risk` 3종이 그렇게 있었다.
    """
    ghosts = sorted(t for t in INSIGHT_TYPES if not _mentioned(t))
    assert not ghosts, (
        f"카탈로그에만 있고 소스가 내보내지 않는 유령 타입: {ghosts}\n"
        f"→ 산출부가 지워졌다면 카탈로그에서도 빼라."
    )


def test_D_이번에_추가한_타입이_실제로_들어있다():
    """전수 대조는 **'둘 다 없음'과 구별하지 못한다** — 존재를 따로 못 박는다."""
    assert "selection_contamination" in INSIGHT_TYPES
    assert "heal_escalation" in INSIGHT_TYPES      # 라벨 누락이던 critical
    assert "latency_baseline" in INSIGHT_TYPES
