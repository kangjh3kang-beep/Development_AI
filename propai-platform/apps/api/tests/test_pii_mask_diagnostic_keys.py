"""**적재 마스킹이 진단 필드를 지우지 않는가** — 그리고 **기각한 처방을 다시 시도하지 못하게** 한다.

## 왜 (2026-08-27 실측 · 원본 함수를 그대로 실행해 확인)

`capture_service.mask_pii` 는 `_PII_KEYS` 를 **부분일치**로 본다(`p in key_l`). `_PII_KEYS` 에
`"name"` 이 있어 **`"name" in "filename"` 이 참**이고, 그래서 조기 오류 포착이 애써 싣는
`filename` 이 **적재 시점에 `[redacted]`** 되어 왔다. 프론트가 보내는 payload 키를 파생형으로
전수(23개) 태운 결과 위양성은 그 하나였다.

## ★기각한 처방을 이 파일이 잠근다

*"부분일치를 토큰경계 일치로 바꾼다"* 가 가장 먼저 떠오르는 처방인데 **엄격히 더 나쁘다**:
위양성은 12/16 → 8/16 로만 줄고 **PII 누출 5건을 새로 만든다** —
`username`·`firstname`·`lastname`·`nickname`·`realname` 은 **단일 토큰**이라 `"name"` 과
토큰 일치하지 않아 전부 통과가 된다. 그래서 아래 `test_rejected_token_boundary_*` 가 그 다섯 개의
redact 를 **못 박는다**. 누가 나중에 매처를 "개선"하면 즉시 빨개진다.

★**하지 않기로 한 것을 테스트로 잠근다** — 산문으로만 적으면 재발 저수지에 들어간다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.growth.capture_service import (
    _DIAGNOSTIC_SAFE_KEYS,
    _PII_KEYS,
    mask_pii,
)

WEB = Path(__file__).resolve().parents[2] / "web"

# ── 프론트가 실제로 보내는 payload 키를 **소스에서 파생**한다 ──────────────────
# ★손으로 파일을 나열하면 그 목록이 곧 상한이 된다 — 실제로 그랬다: 초판은 두 파일을 이름으로
#   적었는데 그중 하나가 아직 머지 전이라 `FileNotFoundError` 로 죽었고, 더 중요하게는 **다른
#   곳의 `payload:` 블록을 통째로 못 봤다.** 그래서 **디렉토리에서 파생**한다.
_JS_LITERALS = frozenset({"null", "true", "false", "undefined"})
_EXCLUDE = re.compile(r"(^|/)(node_modules|\\.next|__tests__)(/|$)|\\.(test|spec)\\.tsx?$")


def _balanced(src: str, open_at: int, opener: str, closer: str) -> str:
    """`open_at` 의 여는 괄호부터 **균형이 맞는 지점**까지를 돌려준다.

    ★고정 길이 창을 쓰면 옆 블록을 침범한다(이 저장소에 실제 사고 기록이 있다).
    """
    depth = 0
    for j in range(open_at, len(src)):
        if src[j] == opener:
            depth += 1
        elif src[j] == closer:
            depth -= 1
            if depth == 0:
                return src[open_at + 1 : j]
    raise AssertionError("괄호 균형 실패 — 파서가 죽었다(조용히 넘어가지 않는다)")


def _payload_keys(path: Path) -> set[str]:
    """**`trackEvent(...)` 호출 인자 안의** `payload: { … }` 키만 뽑는다.

    ★초판은 파일 전체의 `payload:` 를 훑어 **경매 화면의 TypeScript 타입 선언**
    (`payload: { name: string; geojson: … }`)까지 집었다 — `name` 이 위양성으로 잡혀
    *"안전 키로 면제하라"* 는 **정반대 처방**을 유도할 뻔했다(그건 PII 누출이다).
    **위양성도 결함이다.** 파생의 축은 「파일 안의 `payload:`」가 아니라
    **「성장루프 이벤트를 만드는 호출」**이다.
    """
    src = path.read_text(encoding="utf-8")
    keys: set[str] = set()
    for call in re.finditer(r"\btrackEvent\s*\(", src):
        args = _balanced(src, call.end() - 1, "(", ")")
        for m in re.finditer(r"payload:\s*\{", args):
            block = _balanced(args, m.end() - 1, "{", "}")
            keys |= set(re.findall(r"(?:^|[\s{,])([A-Za-z_][A-Za-z0-9_]*)\s*:", block))
            # 축약 속성(`scope,`)도 키다. ★단 `digest: null` 의 **값**까지 집히므로 리터럴은 뺀다
            #   (위양성도 결함이다 — 잡음이 섞이면 진짜 위반을 가린다).
            keys |= set(re.findall(r"(?:^|[\s{,])([A-Za-z_][A-Za-z0-9_]*)\s*(?=[,}])", block))
    return keys - _JS_LITERALS


def _payload_sources() -> list[Path]:
    """`apps/web` 전수에서 **`trackEvent(` 를 부르는** 소스를 파생한다(테스트·번들 제외)."""
    out: list[Path] = []
    for p in WEB.rglob("*.ts*"):
        rel = p.relative_to(WEB).as_posix()
        if _EXCLUDE.search(rel):
            continue
        try:
            if re.search(r"\btrackEvent\s*\(", p.read_text(encoding="utf-8")):
                out.append(p)
        except (OSError, UnicodeDecodeError):  # pragma: no cover
            continue
    return out


PAYLOAD_SOURCES = _payload_sources()
FRONTEND_PAYLOAD_KEYS: set[str] = set().union(
    set(), *(_payload_keys(p) for p in PAYLOAD_SOURCES)
)


def test_deriver_is_alive() -> None:
    """전제: 파서가 실제로 키를 뽑았다(공허한 초록 방지 · 조회기 생존 증명)."""
    assert len(PAYLOAD_SOURCES) >= 3, (
        f"`payload:` 를 가진 소스를 거의 못 찾았다 — 수집기가 죽었다: {PAYLOAD_SOURCES}"
    )
    assert len(FRONTEND_PAYLOAD_KEYS) >= 5, (
        f"payload 키를 거의 못 뽑았다 — 파서가 죽었다: {sorted(FRONTEND_PAYLOAD_KEYS)}"
    )
    # ★양성 대조군: 결함이 살던 그 키가 실제로 파생 집합에 있어야 한다.
    assert "filename" in FRONTEND_PAYLOAD_KEYS, (
        "`filename` 이 파생 집합에 없다 — 파서가 그 블록을 놓쳤다면 아래 단언은 공허하다"
    )


def test_frontend_diagnostic_keys_survive_masking() -> None:
    """★(정) 프론트가 보내는 payload 키는 **하나도 지워지지 않는다**."""
    wiped = sorted(
        k for k in FRONTEND_PAYLOAD_KEYS if mask_pii({k: "SENTINEL"})[k] == "[redacted]"
    )
    assert wiped == [], (
        "적재 마스킹이 진단 필드를 지운다 — 그 필드는 화면·analyzer 어디에도 도착하지 않는다.\n"
        f"지워지는 키: {wiped}\n"
        "처방: `_DIAGNOSTIC_SAFE_KEYS` 에 **정확일치**로 추가하라. 매처를 약화시키지 마라(아래 참조)."
    )


@pytest.mark.parametrize(
    "key",
    ["username", "firstname", "lastname", "nickname", "realname"],
)
def test_rejected_token_boundary_refactor_stays_rejected(key: str) -> None:
    """★기각한 처방을 기계로 잠근다 — 이 다섯 개는 **토큰경계 매처에서 전부 누출된다**.

    부분일치를 토큰경계로 바꾸면 `username` 은 토큰이 `{"username"}` 하나뿐이라 `"name"` 과
    일치하지 않는다. 위양성 4건을 줄이려다 **PII 5건을 누출**하는 교환이다 — 하지 않는다.
    """
    assert mask_pii({key: "홍길동"})[key] == "[redacted]", (
        f"`{key}` 가 마스킹되지 않는다 — 매처가 토큰경계로 약화됐을 가능성이 높다.\n"
        "부분일치를 유지하고, 진단 키만 `_DIAGNOSTIC_SAFE_KEYS` 로 면제하라."
    )


@pytest.mark.parametrize(
    "key",
    ["owner_name", "user_email", "contact_phone", "jumin", "resident_id", "addr", "address"],
)
def test_genuine_pii_keys_still_redacted(key: str) -> None:
    """★(역) 정당한 PII 키는 여전히 지워진다 — 면제를 넓히다 보호를 뚫지 않았는가."""
    assert mask_pii({key: "X"})[key] == "[redacted]", f"`{key}` 가 더 이상 마스킹되지 않는다"


def test_safe_list_does_not_cover_a_genuine_pii_key() -> None:
    """★면제 목록이 **진짜 PII 키 자체**를 덮으면 안 된다(예: `"name"` 을 통째로 면제).

    한 방향만 걸면 반대 방향이 원리적으로 탐지 불가다 — 위 (정) 단언은 면제를 넓힐수록 쉬워진다.
    """
    overlap = sorted(k for k in _DIAGNOSTIC_SAFE_KEYS if k in _PII_KEYS)
    assert overlap == [], f"면제 목록이 민감 키 자체를 덮는다: {overlap}"
    # 면제는 **정확일치**여야 한다 — 접두/접미가 다른 키까지 새어 나가면 안 된다.
    assert mask_pii({"owner_filename": "X"})["owner_filename"] == "[redacted]", (
        "`owner_filename` 이 통과했다 — 면제가 부분일치로 새고 있다"
    )


def test_masking_still_scrubs_value_patterns() -> None:
    """면제된 키의 **값**도 내부 패턴(이메일·전화·주민번호)은 계속 치환된다."""
    out = mask_pii({"filename": "leak@example.com 010-1234-5678"})["filename"]
    assert "example.com" not in out and "1234-5678" not in out, out


@pytest.mark.xfail(
    reason=(
        "★부채(초록 안에 보이게 남김) — 백엔드 `_mask_str` 에 **주소 정규식이 없다**. "
        "프론트 `maskString` 은 `ADDRESS_RE` 로 지우지만 `growth.py` 피드백 payload 와 "
        "`learning_loop._summarize_payload` 는 프론트를 거치지 않는다. "
        "★처방 방향은 **결정 필요**: 이 경로가 태우는 것은 `analysis_ledger` 부동산 분석 payload 이고 "
        "**주소가 곧 분석 대상**이라, 지우면 학습 신호를 파괴할 수 있다(단독 판단하지 않았다). "
        "고쳐지면 XPASS 로 시끄럽게 알린다."
    ),
    strict=True,
)
def test_address_in_value_is_masked_debt() -> None:
    out = mask_pii({"note": "서울특별시 강남구 테헤란로 152 3동 401호"})["note"]
    assert "테헤란로 152" not in out
