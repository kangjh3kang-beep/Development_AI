"""★「자동 머지 절대 금지」라고 **적혀 있는데 막는 것이 없다** — 부채를 초록 안에 세운다.

## 왜 (2026-09-12 실측 · 전부 대조군 포함)

`improvement_agent` 는 산출물에 **게이트처럼 보이는 라벨 둘**을 붙인다:

    "requires_approval": True   (+ "auto_merge": False / "auto_adopt": False)
    "active": False             (prompt_candidates.<service> · 주석: «자동 채택 금지»)

**둘 다 읽히지 않는다.**

| 라벨 | 읽는 곳 | 그것이 게이트인가 |
|---|---|---|
| `requires_approval` | `ledger_adapters.py:69` | ✗ 원장으로 **중계**만 |
| 〃 | `growth_pr_task.py:176` | ✗ PR 본문 **문자열** |
| 〃 | `services/domain_agents_service.py:73,95` | ✗ **phase_f** — 다른 하위체계의 **자기 변수** |
| `active` | — | ✗ `dynamic_config.get_prompt_candidates` 가 **0회 언급** |

★`improvement_agent.py:196` 이 *「phase_f 승인게이팅 패턴을 **차용**」* 이라 적는다 —
  **차용한 것은 라벨이고, 게이트는 차용하지 않았다.**

실제 채택 조건은 **후보 레이블 멤버십 + `samples >= PROMPT_AB_MIN_SAMPLES`** 뿐이고,
그 경로는 **과금 LLM 호출**(`record_llm_response_billing_sync`)을 거쳐
`feature_flags.apply_prompt_ab` 의 `{"version": …, "auto": True}` 로 끝난다.

★★**지금 발화하지 않는 이유는 게이트가 아니라 표본 부족**이다(동료 세션 라이브 실측:
  `prompt_ab` 채택 기록 **0건** · `prompt.<service>` 활성 플래그 **없음**).
  ***「발화한 적 없는 경로」를 「막혀 있다」로 적지 않는다*** — 트래픽이 늘면 그대로 발화한다.

## 이 파일이 하는 것

행위를 **바꾸지 않는다**. 「막혀 있다」는 **거짓 주장**을 코드에서 걷어내고,
**진짜 게이트가 없다는 사실**을 초록 안에 세운다. 게이트를 어디에 둘지는 설계 판단이다
(`active` 를 존중할지 · 승인 상태를 어디에 저장할지 · 돈이 걸린 경로라 더 그렇다).
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from app.services.growth import dynamic_config as DC
from app.services.growth import feature_flags as FF
from app.services.growth import improvement_agent as IA

_API = pathlib.Path(__file__).resolve().parents[1]


def _idents(fn) -> set[str]:
    """함수 안의 **식별자·문자열 상수**(주석·독스트링 배제 — ast 가 애초에 안 본다)."""
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.add(n.value)
    return out


def test_candidate_reader_ignores_the_active_flag() -> None:
    """★`active: False` 는 **읽히지 않는다** — 「자동 채택 금지」를 그것이 보장하지 않는다."""
    idents = _idents(DC.get_prompt_candidates)
    # ★공허 방지 — 이 파서가 정말 그 함수를 읽었는가.
    assert "candidates" in idents, f"파서가 죽었다(후보 키를 못 봤다): {sorted(idents)[:8]}"
    assert "active" not in idents, (
        "후보 조회가 active 를 보기 시작했다 — 그렇다면 이 파일의 부채 표식을 갱신하라"
    )


def test_adoption_path_never_reads_the_approval_label() -> None:
    """★채택 경로가 `requires_approval` 을 **0회** 언급한다(대조군: 다른 메타는 읽는다)."""
    src = pathlib.Path(inspect.getfile(FF)).read_text(encoding="utf-8")
    lits = "".join(
        n.value for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )
    # ★대조군 — 이 모듈이 후보 메타를 **실제로** 읽는다(조회기 생존).
    assert "trigger_key" in lits, "대조군 실패 — 파서가 이 모듈의 메타 키를 못 본다"
    assert "requires_approval" not in lits, (
        "채택 경로가 승인 라벨을 읽기 시작했다 — 아래 xfail 을 갱신하라"
    )


def test_nothing_activates_a_prompt_candidate() -> None:
    """★`active` 를 True 로 되돌리는 생산자가 **없다** — 그 플래그는 죽어 있다."""
    hits: list[str] = []
    for p in (_API / "app").rglob("*.py"):
        if "/tests/" in str(p):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values, strict=False):
                    if (isinstance(k, ast.Constant) and k.value == "active"
                            and isinstance(v, ast.Constant) and v.value is True):
                        hits.append(f"{p}:{n.lineno}")
    # ★공허 방지 — 이 수집기가 `active` 키 자체는 찾는가(False 쪽으로).
    found_false = "active" in _idents(IA._register_candidate)
    assert found_false, "수집기가 active 키를 못 찾는다(파서 사망)"
    assert not hits, f"누군가 후보를 활성화한다 — 부채 표식을 갱신하라: {hits}"


def test_adoption_cannot_bootstrap_because_only_one_version_is_served() -> None:
    """★자동 채택의 **콜드 스타트가 구조적으로 불가능**하다 — 그 사실을 잠근다.

    측정(2026-09-12):
      · `_pick_better_version` 은 `len(scored) < 2` 면 `insufficient_versions` 로 거부한다
        (`samples >= PROMPT_AB_MIN_SAMPLES == 20` 을 넘는 버전이 **둘** 필요)
      · `base_interpreter._resolve_prompt_version_async` 는 서비스당 **한 버전**을 해석한다 —
        **트래픽 분할이 없다**(random·해시 버킷·rollout 0건 · 대조군: 그 파일에 버전 코드 32줄)
      · `prompt.<service>` 를 **쓰는 곳은 `feature_flags.apply_prompt_ab` 하나뿐**
    ⇒ 채택하려면 두 버전이 필요하고, 두 번째 버전이 생기려면 채택이 필요하다 — **순환**이다.

    ★그러므로 「표본 부족이라 안 돈다」는 **부정확**하다. 트래픽이 아무리 늘어도 콜드 스타트는
      안 돈다. **사람이 `POST /growth/settings` 로 한 번 심으면** 그 순환이 끊긴다.
    ★이 락은 **그 구조가 바뀌면 빨개진다** — 누가 트래픽 분할을 넣거나 두 번째 writer 를
      만들면, 위 xfail 의 위험 서술도 같이 고쳐야 한다.
    """
    from app.services.growth import feature_flags as _FF

    assert _FF.PROMPT_AB_MIN_SAMPLES == 20, f"하한이 바뀌었다: {_FF.PROMPT_AB_MIN_SAMPLES}"

    pick = inspect.getsource(_FF._pick_better_version)
    assert "len(scored) < 2" in pick, "두 버전 요구가 사라졌다 — 위험 서술을 갱신하라"

    bi = (_API / "app" / "services" / "ai" / "base_interpreter.py").read_text(encoding="utf-8")
    # ★공허 방지 — 이 파일이 정말 버전 해석기인가.
    assert bi.count("prompt_version") >= 5, "대조군 실패: 버전 코드를 못 찾았다"
    import re as _re
    split = _re.findall(r"\b(random|rollout|bucket)\b", bi)
    assert not split, f"트래픽 분할이 생겼다 — 순환이 끊긴다: {set(split)}"

    writers = [
        str(p) for p in (_API / "app").rglob("*.py")
        if "/tests/" not in str(p) and _re.search(r'setting_key\s*=\s*f"prompt\.', p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert len(writers) == 1, f"prompt.<service> writer 가 늘었다(순환이 끊긴다): {writers}"


@pytest.mark.xfail(
    strict=True,
    reason="★부채: 자동 프롬프트 A/B 채택 경로에 **사람 게이트가 없다**. 산출물에 "
           "`requires_approval: True` · `auto_adopt: False` · `active: False` 라는 라벨이 셋이나 "
           "붙는데 **강제하는 소비처가 0**이고, 실제 조건은 «후보 멤버십 + 표본 하한» 뿐이다. "
           "그 경로는 과금 LLM 호출을 거쳐 `apply_prompt_ab({'auto': True})` 로 끝난다. "
           "★★지금 발화하지 않는 **정확한** 이유는 「표본 부족」이 아니라 **순환**이다: "
           "채택은 `len(scored) >= 2`(하한 20 을 넘는 버전이 **둘**)를 요구하는데, 해석기는 "
           "서비스당 **한 버전**만 제공하고(트래픽 분할 0건) `prompt.<service>` 를 쓰는 곳은 "
           "`apply_prompt_ab` **하나뿐**이다 — 채택하려면 이미 채택돼 있어야 한다. "
           "★그러나 **사람이 `POST /growth/settings` 로 한 번 심으면 그 순환이 끊기고** "
           "그 뒤부터는 자동으로 돈다. 「도달 불가」는 **콜드 스타트에 한정**된다. "
           "★게이트를 어디에 둘지는 설계 판단이라 이 PR 은 **행위를 바꾸지 않는다**.",
)
def test_prompt_adoption_has_a_human_gate() -> None:
    """자동 채택 전에 사람 승인이 강제된다(미해결 — strict xfail).

    ★상환 방법(택1, 설계 판단): ①`get_prompt_candidates` 가 `active` 를 존중한다
      ②`apply_prompt_ab` 가 후보 메타의 `requires_approval` 을 본다 ③승인 상태를 둘 자리를
      새로 정한다. **어느 쪽이든 이 xfail 이 XPASS 로 빨개져** 라벨과 게이트가 다시 갈리지 않는다.
    """
    idents = _idents(DC.get_prompt_candidates) | _idents(FF.apply_prompt_ab)
    assert "active" in idents or "requires_approval" in idents, (
        "채택 경로가 승인/활성 라벨을 전혀 보지 않는다 — 라벨만 있고 게이트가 없다"
    )
