"""**적재 마스킹이 진단 필드를 지우지 않는가** — 그리고 **면제가 PII 를 새게 하지 않는가**.

## 왜 (2026-08-27 실측 · 원본 함수를 그대로 실행해 확인)

`capture_service.mask_pii` 는 `_PII_KEYS` 를 **부분일치**로 본다(`p in key_l`). `_PII_KEYS` 에
`"name"` 이 있어 **`"name" in "filename"` 이 참**이고, 그래서 조기 오류 포착이 애써 싣는
`filename` 이 **적재 시점에 `[redacted]`** 되어 왔다.

## ★독립 적대 리뷰가 초판 락 3개를 뚫었다 — 그 자리가 이 파일의 설계다

1. **기각한 처방을 「손으로 고른 5개 키」로 잠갔었다** → 그 5개만 비켜 가는 토큰경계 리팩토링이
   **SURVIVED**(새로 누출되는 정당 PII 키 14건). **목록은 곧 상한이 된다.**
   → 이제 `_PII_KEYS` **전수 × 변형**으로 **부분일치라는 성질 자체**를 잠근다.
2. **(정)방향은 파생형인데 (역)방향이 목록형**이었다 → `_DIAGNOSTIC_SAFE_KEYS` 에
   `contact_name`·`home_addr1` 을 넣어도 **락 17개 전부 초록**이었다.
   → 이제 면제 집합이 **프론트 실제 payload 키에서 파생된 것의 부분집합**임을 강제한다.
3. **수집기가 간접 전달을 못 봤다** — `payload` 를 변수로 넘기는 호출
   (`buildSelectionContaminationProps`)의 4키가 파생 집합에 없었는데 **분모는 채워** 생존 단언이
   공허했다. → 축을 `TrackEventProps` 반환 함수까지 넓히고 **그 키를 양성 대조군으로** 못 박는다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.services.growth.capture_service import (
    _DIAGNOSTIC_SAFE_KEYS,
    _PII_KEYS,
    mask_pii,
)

WEB = Path(__file__).resolve().parents[2] / "web"

_JS_LITERALS = frozenset({"null", "true", "false", "undefined"})
# ★초판 정규식은 `r"\\."` 로 써서 **리터럴 역슬래시**를 요구했다 — POSIX 경로엔 없으므로
#   `.next/`·`*.test.ts` 를 **하나도 배제하지 못했다**(독립 리뷰 실측). 위양성도 결함이다.
_EXCLUDE = re.compile(r"(^|/)(node_modules|\.next|__tests__)(/|$)|\.(test|spec)\.tsx?$")


def _balanced(src: str, open_at: int, opener: str, closer: str) -> str:
    """`open_at` 의 여는 괄호부터 **균형이 맞는 지점**까지. 고정 창은 옆 블록을 침범한다."""
    depth = 0
    for j in range(open_at, len(src)):
        if src[j] == opener:
            depth += 1
        elif src[j] == closer:
            depth -= 1
            if depth == 0:
                return src[open_at + 1 : j]
    raise AssertionError("괄호 균형 실패 — 파서가 죽었다(조용히 넘어가지 않는다)")


def _keys_in_payload_blocks(text: str) -> set[str]:
    keys: set[str] = set()
    for m in re.finditer(r"payload:\s*\{", text):
        block = _balanced(text, m.end() - 1, "{", "}")
        keys |= set(re.findall(r"(?:^|[\s{,])([A-Za-z_][A-Za-z0-9_]*)\s*:", block))
        # 축약 속성(`scope,`)도 키다. `digest: null` 의 **값**은 리터럴 집합으로 걷어낸다.
        keys |= set(re.findall(r"(?:^|[\s{,])([A-Za-z_][A-Za-z0-9_]*)\s*(?=[,}])", block))
    return keys - _JS_LITERALS


def _extract(path: Path) -> tuple[set[str], int, int]:
    """성장루프 이벤트의 payload 키를 뽑고, **해석 못 한 호출 수**를 함께 돌려준다.

    반환: (키, **간접 호출 수**, **축② 생산자 수**). ★셋을 그대로 돌려주고 판정은 테스트가 한다.

    ★파일 전체의 `payload:` 를 훑으면 **경매 화면의 TypeScript 타입 선언**까지 집는다(실측 —
    그대로 갔으면 `name` 을 안전키로 면제하라는 **정반대 처방**을 유도했을 것이다).
    그래서 축은 ①`trackEvent(` 호출 인자 ②`TrackEventProps` 를 반환하는 함수 **둘뿐**이다.
    """
    src = path.read_text(encoding="utf-8")
    keys: set[str] = set()
    indirect = 0
    for call in re.finditer(r"\btrackEvent\s*\(", src):
        args = _balanced(src, call.end() - 1, "(", ")")
        if "payload:" in args:
            keys |= _keys_in_payload_blocks(args)
        elif not re.search(r"\{", args):
            indirect += 1  # payload 를 **변수로** 넘긴 호출 — 축 ②가 덮어야 한다
    axis2 = 0
    for fn in re.finditer(r":\s*TrackEventProps(?:\s*\|\s*null)?\s*\{", src):
        keys |= _keys_in_payload_blocks(_balanced(src, fn.end() - 1, "{", "}"))
        axis2 += 1
    # ★**판정을 여기서 하지 않는다.** 초판은 `if axis2: unresolved = 0` 으로 여기서 뭉갰는데,
    #   그 한 줄을 `if True:` 로 바꾸면 미해석 가드가 **통째로 공허**해졌다(변이 SURVIVED 실측).
    #   경고·보정은 산문이고 **판정은 테스트가 한다** — 두 수를 **그대로** 돌려준다.
    return keys, indirect, axis2


def _sources() -> list[Path]:
    out: list[Path] = []
    for p in WEB.rglob("*.ts*"):
        if _EXCLUDE.search(p.relative_to(WEB).as_posix()):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover
            continue
        if re.search(r"\btrackEvent\s*\(|:\s*TrackEventProps", text):
            out.append(p)
    return out


SOURCES = _sources()
_EXTRACTED = {p: _extract(p) for p in SOURCES}
FRONTEND_PAYLOAD_KEYS: set[str] = set().union(set(), *(k for k, _, _ in _EXTRACTED.values()))


# ── 백엔드 `record_event(...)` payload 키도 **소스에서 파생**한다 ────────────────
# ★`#906` 은 모집단을 **프론트 전용**으로 두고 그 한계를 계획서 §3 에 「미측정」으로 적었다 — 여기서 닫는다.
#   실측(2026-08-27 · 원본 `mask_pii` 를 AST 로 추출해 **그대로 실행**): 백엔드 키 **57종 중 위양성 0** ·
#   `_PII_KEYS` 와 부분일치하는 **위험 근접 키도 0**. **그래서 런타임은 안 고쳤다** —
#   이 파생은 *앞으로* 추가될 백엔드 키가 부분일치에 걸리면 **즉시 빨개지게** 한다.
#
# ★수집기가 **양방향으로** 틀렸던 것을 여기 남긴다(그래서 이 함수가 이 모양이다):
#   ①**이름만**으로 매칭 → 25건(**과다**). `api/endpoints/sales/referral.py` 가 **동명의 다른 함수**를
#     정의하고 `mh.py`·`referral.py` 가 그것을 부른다. `capture_service` 의 정의 자신도 섞인다.
#   ②**모듈 별칭만**으로 매칭 → 15건(**과소**). `design_ingest/orchestrator.py`·`ingest_service.py` 는
#     **함수 안 지역 import**(`from … import record_event`)라 모듈레벨 스캔에 안 잡힌다.
#   ③둘 다 처리 → **17건**. `ast.walk` 로 지역 import 까지 보고, **자기 정의가 있는 파일은 뺀다**.
#   ★한쪽만 고쳤으면 반대 방향이 조용히 남았다 — 위양성도 위음성도 결함이다.
API_ROOT = Path(__file__).resolve().parents[1]
_CS_MODULE = "growth.capture_service"


def _record_event_payload_keys() -> tuple[set[str], list[str], int]:
    """`capture_service.record_event(...)` 의 payload 키를 판다.

    반환: (키, **해석 못 한 호출 위치**, 진짜 호출 수). ★판정은 테스트가 한다 — 여기서 뭉개지 않는다
    (`#906` 에서 수집기 안 보정 한 줄이 가드를 통째로 공허하게 만든 전례가 있다).
    """
    keys: set[str] = set()
    unresolved: list[str] = []
    calls = 0
    for path in API_ROOT.rglob("*.py"):
        rel = path.relative_to(API_ROOT).as_posix()
        if rel.startswith("tests/") or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):  # pragma: no cover
            continue

        aliases: set[str] = set()
        direct = False
        defines_own = False
        for n in ast.walk(tree):  # ★walk — 함수 **안**의 지연 import 도 본다
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.endswith(_CS_MODULE):
                        aliases.add(a.asname or a.name.rsplit(".", 1)[-1])
            elif isinstance(n, ast.ImportFrom):
                mod = n.module or ""
                if mod.endswith(_CS_MODULE) and any(a.name == "record_event" for a in n.names):
                    direct = True
                if mod.endswith("services.growth"):
                    for a in n.names:
                        if a.name == "capture_service":
                            aliases.add(a.asname or "capture_service")
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "record_event":
                # ★**설명되는 생존**(변이 점수 부풀리기 방지 · 실측 기록): 이 줄을 `False` 로 바꿔도
                #   변이가 **생존한다**. 오늘 자기 정의를 가진 파일
                #   (`growth/capture_service.py` · `sales/referral.py`)은 **둘 다 `direct=False`** 라
                #   bare-name 분기가 애초에 안 탄다(실측). 즉 **도달 불가 이중 가드**다.
                #   그래도 남긴다 — 두 조건이 동시에 참인 파일(자기도 정의하고 우리 것도 들여옴)이
                #   생기면 그때는 **이 줄만이** 오배정을 막는다. 점수용 단언은 붙이지 않는다.
                defines_own = True

        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            is_ours = (
                isinstance(fn, ast.Attribute)
                and fn.attr == "record_event"
                and isinstance(fn.value, ast.Name)
                and fn.value.id in aliases
            ) or (
                isinstance(fn, ast.Name) and fn.id == "record_event" and direct and not defines_own
            )
            if not is_ours:
                continue
            calls += 1
            props = n.args[1] if len(n.args) >= 2 else next(
                (k.value for k in n.keywords if k.arg == "props"), None
            )
            if props is None:
                continue
            if not isinstance(props, ast.Dict):
                unresolved.append(f"{rel}:{n.lineno}")
                continue
            # `strict=True` — 길이가 어긋나면 **조용히 잘리지 않고** 터진다(파서 사망을 드러낸다).
            if any(k is None for k in props.keys):
                # props 자체가 `{**base}` 면 `"payload"` 상수 키가 안 보여 **키 0·미해석 0** 으로 통과한다.
                unresolved.append(f"{rel}:{n.lineno}(props ** 언패킹)")
            for k, v in zip(props.keys, props.values, strict=True):
                if not (isinstance(k, ast.Constant) and k.value == "payload"):
                    continue
                if isinstance(v, ast.Dict):
                    # ★**조용히 버리지 않는다**: `{**base, "x": y}` 의 `**base` 는 `keys` 에 `None` 으로
                    #   들어오고, 비상수 키(`{SOME_CONST: v}`)도 마찬가지다. 초판은 그것을 **필터링만**
                    #   했다 — 같은 파일이 `strict=True` 로 "조용히 잘리지 않고 터진다"고 적어 놓고
                    #   **이 줄이 조용히 잘랐다**(독립 리뷰 실측: `**{"owner_name": …}` 주입이 SURVIVED).
                    if any(pk is None for pk in v.keys):
                        unresolved.append(f"{rel}:{n.lineno}(payload ** 언패킹)")
                    if any(
                        pk is not None
                        and not (isinstance(pk, ast.Constant) and isinstance(pk.value, str))
                        for pk in v.keys
                    ):
                        unresolved.append(f"{rel}:{n.lineno}(payload 비상수 키)")
                    keys |= {
                        pk.value
                        for pk in v.keys
                        if isinstance(pk, ast.Constant) and isinstance(pk.value, str)
                    }
                else:
                    unresolved.append(f"{rel}:{n.lineno}(payload 비리터럴)")
        # ★**래퍼 경유**도 축이다 — `capture_service.record_fallback(service, kind, *, severity, **meta)` 은
        #   `record_event("fallback", {... "payload": {"kind": kind, **meta}})` 로 **임의 키를 그대로** 싣는다.
        #   그 호출은 `capture_service.py` **안**에 있어 `direct=False` 로 걸러지므로, 초판에서는
        #   모집단에도 `unresolved` 에도 **안 들어갔다 — 경고 없이 감시 밖**이었다.
        #   (독립 리뷰 실측: 생산자에 `owner_name="X"` 를 주입해도 SURVIVED.)
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            nm = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else None)
            if nm != "record_fallback" or rel.endswith("growth/capture_service.py"):
                continue
            calls += 1
            keys.add("kind")  # 래퍼가 항상 싣는 상수 키
            for kw in n.keywords:
                if kw.arg is None:
                    # `**meta` 전달 — 정적으로 못 푼다(2단 래퍼 `_record_engine_fallback` 이 그 예다).
                    unresolved.append(f"{rel}:{n.lineno}(record_fallback ** 전달)")
                elif kw.arg != "severity":  # `severity` 는 payload 가 아니라 형제 필드다
                    keys.add(kw.arg)
    return keys, unresolved, calls


BACKEND_KEYS, BACKEND_UNRESOLVED, BACKEND_CALLS = _record_event_payload_keys()

# `base_interpreter.py:399-408` 이 **같은 함수 안에서 조건부로 조립**하는 키.
# ★정정: 초판 계획서는 *"AST 로 파생되지 않는다"* 고 적었는데 그것은 **틀린 라벨**이다 —
#   리터럴 대입·`update()`·subscript 뿐이라 **정적 파생은 가능**하고, **이 파생기의 현재 형태**
#   (인라인 dict 리터럴만 본다)로는 안 잡힐 뿐이다. 두 문장은 다음 사람에게 다른 결정을 유도한다.
DYNAMIC_BACKEND_KEYS = frozenset(
    {"ok", "input_tokens", "output_tokens", "error", "reason", "error_type"}
)

# ★면제의 정당성을 판정하는 **역방향 모집단** — 프론트만 보면 백엔드 전용 위양성을 고치는
#   정당한 처방이 "발명"으로 신고된다(독립 리뷰가 잡은 교착: 이 파일의 실패 메시지가 지시한
#   처방을 이 파일의 다른 락이 막았다). `#906` 리뷰가 잡은 *"(정)은 파생형인데 (역)이 목록형"*
#   의 **거울상 재발**이었다.
DERIVED_PAYLOAD_KEYS: set[str] = set(BACKEND_KEYS) | set(DYNAMIC_BACKEND_KEYS)


# ── 수집기·파서 생존 ────────────────────────────────────────────────────────
def test_deriver_is_alive() -> None:
    """전제: 수집기와 파서가 살아 있다(공허한 초록 방지)."""
    assert len(SOURCES) >= 3, f"소스를 거의 못 찾았다 — 수집기가 죽었다: {SOURCES}"
    assert len(FRONTEND_PAYLOAD_KEYS) >= 5, f"키를 거의 못 뽑았다: {sorted(FRONTEND_PAYLOAD_KEYS)}"
    # ★양성 대조군 ①: 결함이 살던 그 키(직접 전달 축)
    assert "filename" in FRONTEND_PAYLOAD_KEYS, "직접 전달 축이 죽었다"
    # ★양성 대조군 ②: **간접 전달**(payload 를 변수로 넘기는 경로 — 초판이 통째로 놓친 축)
    assert "verdict" in FRONTEND_PAYLOAD_KEYS, (
        "간접 전달 축이 죽었다 — `buildSelectionContaminationProps` 의 키가 안 보인다.\n"
        "이 단언이 없으면 그 4키가 빠진 채로도 위 개수 단언이 **공허하게** 만족된다."
    )


def test_every_indirect_call_has_a_resolver() -> None:
    """★payload 를 **변수로** 넘기는 호출이 있으면, 같은 파일에 축② 생산자가 **있어야** 한다.

    없으면 그 키들은 이 락의 감시 밖이다 — **조용한 위음성**이다.
    ★판정을 수집기 안에서 하지 않는다: 초판은 `if axis2: unresolved = 0` 으로 뭉갰고, 그 한 줄을
    `if True:` 로 바꾸면 가드가 통째로 공허해졌다(변이 SURVIVED 실측).
    """
    orphan = sorted(
        str(p.relative_to(WEB))
        for p, (_, indirect, axis2) in _EXTRACTED.items()
        if indirect > 0 and axis2 == 0
    )
    assert orphan == [], (
        f"payload 를 해석할 수 없는 `trackEvent` 호출이 있는 파일: {orphan}\n"
        "축(`trackEvent(` 인자 · `TrackEventProps` 반환 함수)을 넓혀라."
    )
    # ★**설명되는 생존**(변이 점수 부풀리기 방지 · 실측 기록): 위 조건절을 `if False` 로 바꾸면
    #   이 단언은 생존한다. 그러나 그것은 **단언 자신의 술어를 죽인 것**이고, 그렇게 하면 어떤
    #   테스트든 죽는다 — 제품이 아니라 락을 지운 것이다. 앞선 `if axis2: unresolved = 0` 생존과
    #   **다른 층**이다: 그건 **수집기 안**의 보정이라 "정리"처럼 보였고 그래서 진짜 구멍이었다.
    # ★공허 진리 가드 — 간접 호출이 **실재**해야 위 단언이 무엇이라도 잰다.
    total_indirect = sum(i for _, i, _ in _EXTRACTED.values())
    assert total_indirect > 0, (
        "간접 호출을 한 건도 못 찾았다 — 수집기가 죽었으면 위 단언은 공허하게 참이다"
    )


# ── 백엔드 모집단 ────────────────────────────────────────────────────────────
def test_backend_deriver_is_alive() -> None:
    """전제: 백엔드 수집기가 살아 있다(공허 진리 방지)."""
    # 하한을 **실측값에 붙인다** — 여유를 크게 두면 절반이 사라져도 통과한다.
    # ★**양방향**으로 건다 — 하한만 걸면 **과대수집**(이름충돌 재유입)이 조용히 통과한다.
    #   초판은 하한만 있었고, 그 방어를 `test_backend_unresolved_calls_are_documented` 가
    #   **오늘의 우연**(동명 함수가 payload dict 를 안 넘긴다)에 기대 대신하고 있었다.
    assert 19 <= BACKEND_CALLS <= 26, (
        f"record_event/record_fallback 호출 수가 예상 범위를 벗어났다: {BACKEND_CALLS}\n"
        "  ↓ 하한 미달 = 수집기 사망 **또는** 정당한 삭제(둘 다 가능하다 — 확인 후 갱신하라)\n"
        "  ↑ 상한 초과 = 동명의 다른 함수 재유입(과대수집) 의심"
    )
    assert len(BACKEND_KEYS) >= 56, f"백엔드 payload 키 파생 실패: {sorted(BACKEND_KEYS)}"
    # ★양성 대조군 — 반드시 있어야 하는 키가 같은 방법으로 조회된다.
    # ★대조군의 **두께가 다르다**(정직하게): `ok` 는 다수 · `zone_code` 는 5곳 ·
    #   `cache_hit` 은 `base_interpreter.py:938` **한 곳뿐**이다. 그 관측이 정당하게 제거되면
    #   이 대조군이 빨개진다 — 그때는 대조군을 갈아 끼우는 것이 옳다(결함이 아니다).
    for probe in ("zone_code", "ok", "cache_hit"):
        assert probe in BACKEND_KEYS, f"`{probe}` 가 파생 집합에 없다 — 파서가 그 블록을 놓쳤다"


def test_backend_unresolved_calls_are_documented() -> None:
    """★해석 못 한 호출은 **사유와 함께 열거**된 것뿐이어야 한다.

    이 단언은 **이름충돌 대조군을 겸한다**: `api/endpoints/sales/referral.py` 가 정의하는
    **동명의 다른 함수**(`record_event(db, code, event, …)`)를 잘못 포함하면 그 호출들은
    payload dict 가 없어 **미해석이 2건에서 5건으로 늘어난다**. 즉 여기가 빨개진다.
    """
    known = {
        # 프론트가 보낸 것을 그대로 적재하는 경로. ★**우리 앱 `trackEvent` 가 유일한 생산자라는
        # 전제 하에** 프론트 파생(`FRONTEND_PAYLOAD_KEYS`)이 덮는다 — 그 엔드포인트는
        # `payload: dict | None` 이라 임의 HTTP 클라이언트의 임의 키도 받는다(전제를 명시한다).
        "app/routers/growth.py:98(payload 비리터럴)",
        # LLM 호출 계측 — payload 를 **같은 함수 안에서 조건부로 조립**한다. 그 6키는
        # `DYNAMIC_BACKEND_KEYS` 로 올려 마스킹 단언에 **직접 실어** 태운다.
        "app/services/ai/base_interpreter.py:410(payload 비리터럴)",
        # 같은 호출의 **props 층** `**({"latency_ms": …} if … else {})` — payload 키가 아니라
        # 형제 필드다(analyzer 의 latency 지표 계약). 파서가 "못 본다"고 정직하게 신고한 것.
        "app/services/ai/base_interpreter.py:410(props ** 언패킹)",
        # ★**2단 래퍼** `_record_engine_fallback(kind, **meta)` → `record_fallback(..., **meta)`.
        # 정적으로 못 따라간다. 오늘 실제로 싣는 키는 `reason`·`path`(`registry.py:313,325`)이나
        # **시그니처가 `**meta` 라 모집단이 열려 있다** — 그래서 값이 아니라 사실을 기록한다.
        "app/services/agents/registry.py:299(record_fallback ** 전달)",
    }
    surprise = sorted(set(BACKEND_UNRESOLVED) - known)
    assert surprise == [], (
        f"새로 해석 못 한 `record_event` 호출 — 그 키들은 이 락의 감시 밖이다:\n{surprise}"
    )
    # ★죽은 면제도 실패시킨다 — 사라진 예외를 남겨 두면 다음 사람이 유효한 것으로 읽는다.
    stale = sorted(known - set(BACKEND_UNRESOLVED))
    assert stale == [], f"이미 해소된 예외가 목록에 남아 있다(정리할 것): {stale}"


def test_backend_payload_keys_survive_masking() -> None:
    """★백엔드 `record_event` payload 키도 **하나도 지워지지 않는다**.

    실측(2026-08-27): 57종(정적 54 + `base_interpreter` 동적 6, 중복 제외) 중 **위양성 0**.
    `_PII_KEYS` 와 부분일치하는 **위험 근접 키도 0** 이었다 — 그래서 런타임은 안 고쳤다.
    """
    wiped = sorted(
        k for k in (BACKEND_KEYS | DYNAMIC_BACKEND_KEYS) if mask_pii({k: "S"})[k] == "[redacted]"
    )
    assert wiped == [], (
        "적재 마스킹이 백엔드 진단 필드를 지운다 — 그 필드는 analyzer 어디에도 도착하지 않는다.\n"
        f"지워지는 키: {wiped}\n"
        "처방: `_DIAGNOSTIC_SAFE_KEYS` 에 **정확일치**로 추가하라. 매처를 약화시키지 마라."
    )


# ── (정) 진단 필드는 살아남는다 ──────────────────────────────────────────────
def test_frontend_diagnostic_keys_survive_masking() -> None:
    wiped = sorted(k for k in FRONTEND_PAYLOAD_KEYS if mask_pii({k: "SENTINEL"})[k] == "[redacted]")
    assert wiped == [], (
        f"적재 마스킹이 진단 필드를 지운다 — 어디에도 도착하지 않는다.\n지워지는 키: {wiped}\n"
        "처방: `_DIAGNOSTIC_SAFE_KEYS` 에 **정확일치**로 추가하라. 매처를 약화시키지 마라."
    )


# ── ★기각한 처방을 **성질**로 잠근다(목록이 아니라) ──────────────────────────
@pytest.mark.parametrize("pii", _PII_KEYS)
def test_matcher_stays_substring_not_token(pii: str) -> None:
    """★부분일치 **성질 자체**를 `_PII_KEYS` 전수 × 변형으로 잠근다.

    초판은 `username` 등 **손으로 고른 5개**만 잠갔다 → 그 5개를 특례로 비켜 가는 토큰경계
    리팩토링이 SURVIVED 했고, 새로 누출되는 정당 PII 키가 **14건**이었다(독립 리뷰 실측).
    ★목록을 잠그면 그 목록이 곧 상한이 된다 — **성질**을 잠근다.
    """
    for key in (f"x{pii}", f"{pii}x", f"a{pii}b", f"user_{pii}", f"{pii}_id", f"{pii}s"):
        if key in _DIAGNOSTIC_SAFE_KEYS:
            continue  # 명시적으로 면제된 것만 예외(면제 자체는 아래에서 따로 잠근다)
        assert mask_pii({key: "PII"})[key] == "[redacted]", (
            f"`{key}` 가 마스킹되지 않는다 — 매처가 **토큰경계로 약화**됐을 가능성이 높다.\n"
            "부분일치를 유지하고, 진단 키만 `_DIAGNOSTIC_SAFE_KEYS` 로 면제하라."
        )


# ── (역) 면제가 발명되지 않았는가 ────────────────────────────────────────────
def test_exemptions_are_derived_not_invented() -> None:
    """★면제는 **프론트가 실제로 보내는 키** 중에서만 나와야 한다.

    초판의 역방향 락은 `k in _PII_KEYS`(튜플 정확일치)와 **손으로 쓴 7개 목록**이라,
    `contact_name`·`home_addr1` 을 면제에 넣어도 **락 17개가 전부 초록**이었다(독립 리뷰 실측).
    """
    invented = sorted(_DIAGNOSTIC_SAFE_KEYS - (FRONTEND_PAYLOAD_KEYS | DERIVED_PAYLOAD_KEYS))
    assert invented == [], (
        f"어느 생산자도 보내지 않는 키가 면제돼 있다(프론트·백엔드 전수): {invented}\n"
        "면제는 **실측된 위양성**만이다 — 발명하지 마라(PII 키를 슬쩍 넣는 경로가 된다)."
    )
    # 죽은 면제도 결함이다 — 실제로 부분일치에 걸리지 않는 키를 면제하는 것은 무의미하고,
    # 그 자리가 나중에 **의미 있는 면제로 오해**된다.
    dead = sorted(k for k in _DIAGNOSTIC_SAFE_KEYS if not any(p in k for p in _PII_KEYS))
    assert dead == [], f"부분일치에 걸리지도 않는 면제(죽은 면제): {dead}"


def test_exemption_is_exact_match_not_substring() -> None:
    """면제가 부분일치로 새면 `owner_filename` 같은 변형이 통째로 통과한다."""
    for key in ("owner_filename", "filename_owner", "user_filename"):
        assert mask_pii({key: "X"})[key] == "[redacted]", f"`{key}` 가 통과했다 — 면제가 샌다"


@pytest.mark.parametrize(
    "key", ["owner_name", "user_email", "contact_phone", "jumin", "resident_id", "addr", "address"]
)
def test_genuine_pii_keys_still_redacted(key: str) -> None:
    assert mask_pii({key: "X"})[key] == "[redacted]", f"`{key}` 가 더 이상 마스킹되지 않는다"


# ── ★C1: 면제된 값 자체가 PII 운반체다 ──────────────────────────────────────
def test_exempted_url_value_drops_query_and_fragment() -> None:
    """★`filename` 은 **인라인 스크립트 오류에서 문서 URL 전체**가 된다(실브라우저 실측).

    이 앱은 **지번을 쿼리에** 싣는다(`registry-analysis?addr=…`). 면제를 그냥 통과시키면
    지번이 평문 적재된다. 진단에는 **경로만으로 충분**하므로 쿼리·프래그먼트를 버린다.
    """
    out = mask_pii({"filename": "https://4t8t.net/ko/registry-analysis?addr=서울 강남구 테헤란로 152#f"})
    # 두 모집단이 같은 실행에서 갈린다: 경로는 **남고** 쿼리는 **사라진다**.
    assert "registry-analysis" in out["filename"], f"경로까지 지웠다 — 진단 불가: {out['filename']}"
    assert "테헤란로" not in out["filename"], f"쿼리의 지번이 살아남았다: {out['filename']}"
    assert "#f" not in out["filename"], out["filename"]


def test_exempted_percent_encoded_pii_is_redacted() -> None:
    """★퍼센트 인코딩은 `_mask_str` 의 정규식을 **전부 비켜 간다**(독립 리뷰 실측).

    `hong%40corp.co.kr` 는 이메일 정규식에 안 걸린다 → 디코드해서 검사하고, 걸리면 통째로 버린다.
    """
    enc = mask_pii({"filename": "app.js#u=hong%40corp.co.kr"})["filename"]
    assert "corp.co.kr" not in enc, f"인코딩된 이메일이 살아남았다: {enc}"
    # 음성 대조군 — PII 가 없는 평범한 경로는 **그대로 남아야** 한다(위양성도 결함이다).
    plain = mask_pii({"filename": "/_next/static/chunks/main-abc123.js"})["filename"]
    assert plain == "/_next/static/chunks/main-abc123.js", plain


def test_masking_still_scrubs_value_patterns_in_exempted_key() -> None:
    out = mask_pii({"filename": "leak@example.com 010-1234-5678"})["filename"]
    assert "example.com" not in out and "1234-5678" not in out, out


def test_exemption_applies_at_any_depth_but_pii_parent_still_wins() -> None:
    """면제는 깊이와 무관하되, **PII 부모 아래**에서는 부모가 이긴다(양방향 명시)."""
    assert mask_pii({"a": {"filename": "x.js"}})["a"]["filename"] == "x.js"
    assert mask_pii({"owner_name": {"filename": "x.js"}})["owner_name"] == "[redacted]"


@pytest.mark.xfail(
    reason=(
        "★부채(초록 안에 보이게 남김) — 백엔드 `_mask_str` 에 **주소 정규식이 없다**. "
        "프론트 `maskString` 은 `ADDRESS_RE` 로 지우지만 `growth.py` 피드백 payload 와 "
        "`learning_loop._summarize_payload` 는 프론트를 거치지 않는다. "
        "★처방 방향은 **결정 필요**: 그 경로가 태우는 것은 `analysis_ledger` 부동산 분석 payload 이고 "
        "**주소가 곧 분석 대상**이라, 지우면 학습 신호를 파괴할 수 있다(단독 판단하지 않았다). "
        "고쳐지면 XPASS 로 시끄럽게 알린다."
    ),
    strict=True,
)
def test_address_in_value_is_masked_debt() -> None:
    out = mask_pii({"note": "서울특별시 강남구 테헤란로 152 3동 401호"})["note"]
    assert "테헤란로 152" not in out
