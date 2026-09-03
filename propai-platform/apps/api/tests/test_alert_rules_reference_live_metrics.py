"""경보 규칙이 **존재하지 않는 메트릭**을 조회한다 — 발화한 적 없는 안전망 3건.

## 관측 (라이브 2026-08-27)

`infra/monitoring/prometheus/alert_rules.yml` 의 11개 규칙 중 **3개**가
앱이 내보내지 않는 메트릭을 조회한다:

| 규칙 | 조회하는 메트릭 | 라이브 `/metrics` |
|---|---|---|
| `APIHighErrorRate` | `http_requests_total` | **0건** |
| `APIHighLatency` | `http_request_duration_seconds_bucket` | **0건** |
| `WorkerTaskBacklog` | `arq_pending_tasks` | **0건** |

★**양성 대조군**: 같은 응답에 패밀리 **23종**이 있고 `python_*`·`process_*`·`propai_*` 는
실재한다 — 조회기는 살아 있다.

PromQL 에서 **빈 벡터의 `rate`/`histogram_quantile` 은 빈 벡터**다.
`> 0.05` · `> 2` 비교는 빈 벡터에 대해 아무 시계열도 만들지 않으므로
**알림이 `pending` 에조차 도달하지 못한다.** 빨간 적이 없는 게 아니라 **빨개질 수 없다.**

★이건 이 저장소가 오늘 이미 한 번 만난 클래스다 — `heal_escalation` 이
"코드·카탈로그·라벨이 다 있는데 전 상태 0건"이었던 것과 같은 형태
(**존재 ≠ 발화**). 안전망의 **존재**를 다른 판단의 근거로 쓰기 전에
**그것이 발화할 수 있는지** 재야 한다.

## 이 파일이 하는 일 — 그리고 **하지 않는 일**

**한다**: 규칙이 참조하는 **앱 소유** 메트릭이 앱 레지스트리에 실제로 선언됐는지 대조한다.
**안 한다**: 규칙식을 고치지 않는다. 고치려면 **라우트 클래스별 예산**이 필요한데
(`/api/v1/analysis/comprehensive` 는 정상적으로 163초가 걸린다 — 2초 SLO 를 그대로 켜면
**상시 빨강**이 되고, 상시 빨간 검사는 곧 꺼진다), 그건 제품 결정이다.
**탐지와 교정은 다른 단계다** — 여기서는 탐지를 **기계가 잊지 못하게** 만든다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

_API = Path(__file__).resolve().parents[1]
_RULES = _API.parents[1] / "infra" / "monitoring" / "prometheus" / "alert_rules.yml"

#: 앱(`propai-api`/`propai-worker` 잡)이 스스로 내보내야 하는 메트릭의 접두.
#  ★나머지(`node_`·`pg_`·`redis_`·`nginx_`·`up`)는 **별도 exporter** 가 낸다
#  (`prometheus.yml` 의 `*-exporter:*` 타깃) — 앱 레지스트리로 판정하면 위양성이다.
#  위양성도 결함이므로 **앱 소유가 확실한 것만** 판정한다.
_APP_OWNED_PREFIXES = ("http_", "arq_", "propai_")

#: prometheus_client 가 자동으로 붙이는 접미 — 참조에서 걷어내야 선언명과 맞는다.
_SUFFIXES = ("_bucket", "_sum", "_count", "_total")


def _strip_noise(expr: str) -> str:
    """식별자 추출 **전에** 메트릭 이름일 수 없는 것을 걷어낸다.

    ★**위양성도 결함이다**(2026-08-28 · 리뷰 development-ai-8d 가 잡음을 관측했고,
      재 보니 그중 하나는 **실제 위양성 경로**였다).

    | 표기 | 걷어내지 않으면 | 왜 문제인가 |
    |---|---|---|
    | `rate(x[5m])` | `m` 이 식별자로 잡힌다 | 무해(앱 접두와 못 겹친다) |
    | `up{svc="propai_ghost"}` | **`propai_ghost` 가 잡힌다** | ★**앱 접두와 겹쳐 「죽은 규칙」을 날조한다** |

    실증: `up{service="propai_ghost_service"} == 0` → 걷어내기 전 `propai_ghost_service` 가
    참조 메트릭으로 잡혀 **존재하지 않는 결함을 신고**한다. 오늘 파일에는 그 표기가 **0건**
    (대조군: 따옴표가 있는 **줄** 19개 · 따옴표 **문자** 40개 = 조회기 생존)이라 **잠복**이었다.
    """
    expr = re.sub(r"'[^']*'|\"[^\"]*\"", " ", expr)      # ① 따옴표 안(라벨값) — 위양성 경로
    return re.sub(r"\[[^\]]*\]", " ", expr)                 # ② 범위벡터 `[5m]` — 잡음


def _referenced_metrics(text: str | None = None) -> dict[str, set[str]]:
    """`alert_rules.yml` 에서 **규칙별로** 참조 메트릭을 뽑는다(목록형 금지 — 파일에서 파생).

    ★**YAML 은 YAML 파서로 읽는다**(2026-08-28 · 독립 리뷰 development-ai-8d).
      첫 판은 `re.match(r"\\s*expr:\\s*(.+)", line)` 로 **한 줄만** 봤다. 그러면
      블록 스칼라(`expr: >` / `expr: |`)로 쓴 규칙은 캡처되는 것이 `>` 뿐이고
      **실제 PromQL 이 통째로 버려진다.** 그 규칙의 `names` 가 빈 집합이 되어
      `names - declared` 도 비고 → **죽은 규칙이 `dead` 에 영영 안 나타난다.**
      즉 **죽은 규칙이 숨는다** — 이 파일이 잡으려는 바로 그것이 숨는다.

    ★같은 세션에서 이 형태가 **세 번째**다(리뷰 지적):
        #914 타입 추출은 AST · 배선 락은 문자열
        #901 상태는 파티션형 · 라우터는 금지 목록형
        #905 파이썬은 AST  · YAML 은 정규식        ← 여기
      매번 **「좋은 도구」와 「급한 도구」를 한 파일 안에서 섞었고, 급한 쪽에서 뚫렸다.**
    """
    doc = yaml.safe_load(_RULES.read_text(encoding="utf-8") if text is None else text)
    assert isinstance(doc, dict) and doc.get("groups"), \
        f"alert_rules.yml 을 파싱하지 못했다 — 락이 무의미하다: {type(doc)}"
    out: dict[str, set[str]] = {}
    fns = {"rate", "histogram_quantile", "avg", "by", "instance", "sum",
           "irate", "increase", "max", "min", "count", "job", "status",
           "mode", "mountpoint", "idle", "quantile", "on", "without"}
    for group in doc["groups"]:
        for rule in group.get("rules") or []:
            alert = rule.get("alert")
            if not alert:
                continue
            expr = rule.get("expr")
            # ★빈 expr 을 **조용히 빈 집합으로 두지 않는다** — 그게 첫 판의 결함이었다.
            assert isinstance(expr, str) and expr.strip(), \
                f"규칙 {alert!r} 의 expr 을 못 읽었다(빈 값) — 파서가 죽으면 죽은 규칙이 숨는다"
            out[alert] = {i for i in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", _strip_noise(expr))
                          if i not in fns}
    return out


def _declared_metrics() -> set[str]:
    """앱이 **선언한** 메트릭 이름 — `ast` 로 정적 파싱한다(임포트하지 않는다).

    ★첫 판은 모듈을 임포트해 `REGISTRY.collect()` 를 읽었는데, **CI 에서 실패**했다:
      `sys.path` 를 두 개 넣는 바람에 `metrics` 가 `metrics` 와 `apps.api.metrics`
      **두 이름으로 두 번 실행**돼 `DuplicateTimeseries` 가 났다(로컬에서는 다른
      테스트가 그 경로로 먼저 임포트하지 않아 안 났다 — **순서·경로 의존**).
      → 임포트 부작용을 없앤다. 정적 파싱은 **결정적**이고 다른 테스트와 간섭하지 않는다.

    ★잃는 것: `python_*`·`process_*` 같은 prometheus_client 내장은 안 잡힌다.
      **문제 없다** — 판정 대상은 `_APP_OWNED_PREFIXES` 뿐이고 내장은 그 접두에 없다.
    """
    declared: set[str] = set()
    sites = [_API / "metrics.py", _API / "integrations" / "base_client.py"]
    for site in sites:
        assert site.is_file(), f"선언 사이트가 없다 — 락이 과소 수집한다: {site}"
        tree = ast.parse(site.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name not in {"Counter", "Histogram", "Gauge", "Summary"}:
                continue
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                declared.add(_strip(node.args[0].value))
    return declared


def _strip(name: str) -> str:
    for s in _SUFFIXES:
        if name.endswith(s):
            return name[: -len(s)]
    return name


def _app_owned_references() -> dict[str, set[str]]:
    """규칙별 **앱 소유** 참조만."""
    return {
        alert: {_strip(n) for n in names if n.startswith(_APP_OWNED_PREFIXES)}
        for alert, names in _referenced_metrics().items()
    }


# ══════════════════════════════════════════════════════════════════════
# 조회기 생존 — 이게 없으면 아래 결과가 "0건이라 통과"인지 구별 안 된다
# ══════════════════════════════════════════════════════════════════════

def test_rules_file_exists_and_parses():
    assert _RULES.is_file(), f"규칙 파일이 없다: {_RULES}"
    refs = _referenced_metrics()
    assert len(refs) >= 10, f"규칙을 {len(refs)}개만 파싱했다 — 파서가 죽었다"
    # ★위 한 줄만으로는 **다른 것을 센다**(2026-08-28 · 리뷰 development-ai-8d).
    #   첫 판은 `- alert:` 줄에서 키를 만들었으므로 **expr 파싱이 전부 실패해도
    #   개수는 그대로 11** 이었다 — 생존 가드가 「규칙이 몇 개인가」를 셌지
    #   「식을 읽었는가」를 세지 않았다. 파서를 바꾼 지금도 이 단언을 함께 둔다:
    #   **모든 규칙이 식별자를 하나 이상 내야 한다.** 빈 집합은 곧 숨은 죽은 규칙이다.
    empty = sorted(a for a, names in refs.items() if not names)
    assert not empty, f"식을 못 읽은 규칙이 있다(죽은 규칙이 숨는다): {empty}"
    assert "APIHighLatency" in refs


def test_registry_actually_declares_things():
    declared = _declared_metrics()
    assert len(declared) >= 8, f"선언 메트릭 {len(declared)}개 — 파서가 죽었다"
    assert any(n.startswith("propai_") for n in declared), "앱 메트릭이 하나도 없다"


def test_some_rules_do_reference_app_metrics():
    """★공허한 참 방지 — 앱 소유 참조가 0이면 아래 단언이 무의미해진다."""
    owned = {a: s for a, s in _app_owned_references().items() if s}
    assert owned, "앱 소유 메트릭을 참조하는 규칙이 하나도 없다 — 접두 판정이 죽었다"


# ══════════════════════════════════════════════════════════════════════
# ★본 계약 — 지금은 **깨져 있다**. 부채를 초록 안에 드러낸다.
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(
    strict=True,
    reason="★부채: APIHighErrorRate·APIHighLatency·WorkerTaskBacklog 가 앱이 "
           "내보내지 않는 메트릭을 조회해 **발화 불가**다(라이브 /metrics 23패밀리에 0건). "
           "교정은 라우트 클래스별 예산이 필요한 제품 결정이라 여기서 하지 않는다. "
           "메트릭을 노출하면 이 xfail 이 XPASS 로 **빨개져** 제거를 요구한다.",
)
def test_every_app_owned_alert_metric_is_declared():
    declared = _declared_metrics()
    missing = {
        alert: sorted(names - declared)
        for alert, names in _app_owned_references().items()
        if names - declared
    }
    assert not missing, f"선언되지 않은 메트릭을 조회하는 규칙: {missing}"


def test_the_three_dead_rules_are_exactly_the_known_ones():
    """부채의 **크기를 못 박는다** — 새 규칙이 같은 실수를 하면 여기서 늘어난다.

    ★이 단언은 위 `xfail` 과 **다른 일**을 한다: 저건 "언젠가 고쳐라",
    이건 **"그 사이에 더 늘지 마라"** 다. 늘면 빨개진다.
    """
    declared = _declared_metrics()
    dead = sorted(
        alert for alert, names in _app_owned_references().items() if names - declared
    )
    assert dead == ["APIHighErrorRate", "APIHighLatency", "WorkerTaskBacklog"], dead


# ══════════════════════════════════════════════════════════════════════
# ★블록 스칼라로 **죽은 규칙이 숨는** 것을 막는다 (2026-08-28 · 리뷰 development-ai-8d)
# ══════════════════════════════════════════════════════════════════════

_BLOCK_SCALAR_PROBE = """
  - name: _lock_probe
    rules:
      - alert: LockProbeBlockScalar
        expr: >
          rate(propai_totally_nonexistent_metric_zzz[5m]) > 0
        for: 1m
        labels: {severity: warning}
        annotations: {summary: "락 프로브"}
"""


def _names_for(text: str, alert: str) -> set[str]:
    """★**프로덕션 함수를 태운다** — 파싱 논리를 여기 복제하지 않는다.

    첫 판은 `yaml.safe_load` + 식별자 추출을 이 함수 안에 **다시 썼다.** 그러면
    `_referenced_metrics()` 를 옛 정규식으로 되돌려도 이 락이 **초록**이다
    (변이 실측 2026-08-28: M1 `SURVIVED`). **락이 사본을 태우면 아무것도 안 잠근다.**
    """
    refs = _referenced_metrics(text)
    assert alert in refs, f"규칙 {alert!r} 을 못 찾았다 — 프로브가 죽었다: {sorted(refs)}"
    return refs[alert]


def test_a_block_scalar_expr_cannot_hide_a_dead_rule() -> None:
    """★**두 모집단**이 다른 답을 내야 이 수정이 잠긴다.

    | 표기 | 옛 정규식(`re.match(r"expr:\\\\s*(.+)")`) | 현재(YAML 파서) |
    |---|---|---|
    | 한 줄 `expr: rate(...)`  | 읽는다 | 읽는다 |
    | 블록 `expr: >` + 다음 줄 | **`>` 만 → ∅ (숨는다)** | 읽는다 |

    ★실측(2026-08-28): 옛 구현에 이 프로브를 주입하면 **규칙 수는 12 로 늘어나
      생존 가드 `len(refs) >= 10` 을 통과하는데** 그 규칙의 names 는 **빈 집합**이었다.
      **가드가 「식을 읽었는가」가 아니라 「규칙이 몇 개인가」를 세고 있었다.**
    """
    injected = _RULES.read_text(encoding="utf-8") + _BLOCK_SCALAR_PROBE
    ghost = "propai_totally_nonexistent_metric_zzz"

    # ① 모집단 A — 블록 스칼라: 유령 메트릭이 **보여야** 한다
    names = _names_for(injected, "LockProbeBlockScalar")
    assert ghost in names, f"블록 스칼라 규칙의 식을 못 읽었다 — 죽은 규칙이 숨는다: {names}"

    # ② 모집단 B — 한 줄 표기: 같은 유령이 같은 방법으로 보여야 한다(★조회기 생존)
    one_line = _RULES.read_text(encoding="utf-8") + (
        "\n  - name: _lock_probe_inline\n    rules:\n"
        f"      - alert: LockProbeInline\n        expr: rate({ghost}[5m]) > 0\n"
        "        for: 1m\n        labels: {severity: warning}\n"
        '        annotations: {summary: "락 프로브"}\n'
    )
    assert ghost in _names_for(one_line, "LockProbeInline"), "한 줄 표기조차 못 읽는다 — 프로브가 죽었다"

    # ③ ★음성 대조군 — 원본에는 그 유령이 **없어야** 한다(위 ①②가 공허하지 않다)
    for alert, ref in _referenced_metrics().items():
        assert ghost not in ref, f"원본 규칙 {alert} 에 프로브 메트릭이 새어 들어갔다"


def test_the_liveness_guard_counts_exprs_not_alerts() -> None:
    """★생존 가드가 **다른 것을 세지 않는지** 직접 건다.

    `- alert:` 줄만 세는 가드는 **식을 하나도 못 읽어도 초록**이다(위 실측: 12개).
    그래서 「모든 규칙이 식별자를 하나 이상 낸다」를 함께 단언한다.
    """
    refs = _referenced_metrics()
    assert refs, "규칙을 하나도 못 읽었다"
    empty = sorted(a for a, names in refs.items() if not names)
    assert not empty, f"식을 못 읽은 규칙: {empty}"


def test_an_empty_expr_fails_loudly_instead_of_hiding() -> None:
    """★**빈 `expr` 은 시끄럽게 죽어야 한다** — 조용히 빈 집합이 되면 죽은 규칙이 숨는다.

    변이 실측(2026-08-28): 이 단언이 없으면 M2' 가 **SURVIVED** 였다 — 현재 파일에
    빈 `expr` 이 없어 **도달 불가 방어**였기 때문이다. 그래서 **도달하는 모집단**을 만든다.

    | 모집단 | 기대 |
    |---|---|
    | `expr:` 가 비어 있다 | **AssertionError** (파싱 실패를 정상으로 세지 않는다) |
    | `expr:` 가 정상이다  | 통과하고 식별자를 낸다 |
    """
    broken = _RULES.read_text(encoding="utf-8") + (
        "\n  - name: _empty_expr_probe\n    rules:\n"
        "      - alert: EmptyExprProbe\n        expr:\n        for: 1m\n"
        "        labels: {severity: warning}\n"
        '        annotations: {summary: "빈 식"}\n'
    )
    with pytest.raises(AssertionError, match="EmptyExprProbe"):
        _referenced_metrics(broken)

    # ★대조 모집단 — 같은 자리에 정상 식이면 통과해야 한다(과잉 억제가 아님을 증명)
    ok = broken.replace("        expr:\n", "        expr: propai_analysis_total > 0\n")
    assert "propai_analysis_total" in _referenced_metrics(ok)["EmptyExprProbe"]


def test_a_label_value_is_not_mistaken_for_a_metric() -> None:
    """★**위양성도 결함이다** — 라벨값이 앱 접두를 가지면 「없는 죽은 규칙」을 날조한다.

    | 모집단 | 기대 |
    |---|---|
    | `up{service="propai_ghost_service"} == 0` | 그 문자열이 참조 메트릭에 **없어야** 한다 |
    | `propai_ghost_service > 0` (진짜 참조)     | **있어야** 한다 ← 과잉 억제가 아님을 증명 |

    ★두 모집단이 **다른 답**을 내야 잠긴다. 하나만 걸면 *"전부 걸러내는"* 구현도 통과한다.
    실측 2026-08-28: 걷어내기 전에는 라벨값이 잡혀 **존재하지 않는 결함을 신고**했다.
    오늘 파일에 그 표기는 **0건**(대조군: 따옴표가 있는 줄 19개 · 따옴표 문자 40개 = 조회기 생존)이라 **잠복**이었다.
    """
    ghost = "propai_ghost_service"
    tail = ("        for: 1m\n        labels: {severity: warning}\n"
            '        annotations: {summary: "라벨 프로브"}\n')
    base = _RULES.read_text(encoding="utf-8")

    # ① 라벨값 — 참조로 세면 안 된다
    as_label = base + (
        "\n  - name: _label_probe\n    rules:\n"
        f'      - alert: LabelValueProbe\n        expr: up{{service="{ghost}"}} == 0\n' + tail
    )
    assert ghost not in _referenced_metrics(as_label)["LabelValueProbe"], \
        "라벨값을 메트릭으로 집었다 — 없는 죽은 규칙을 날조한다"

    # ② ★대조 모집단 — 진짜 참조는 세야 한다(전부 걸러내는 구현을 막는다)
    as_metric = base + (
        "\n  - name: _label_probe2\n    rules:\n"
        f"      - alert: RealRefProbe\n        expr: {ghost} > 0\n" + tail
    )
    assert ghost in _referenced_metrics(as_metric)["RealRefProbe"], \
        "진짜 참조까지 걸러냈다 — 과잉 억제(이러면 죽은 규칙을 못 잡는다)"
