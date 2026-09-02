"""「테스트」 버튼이 **실호출로 판정하는가** — 값이 있다는 이유로 초록을 띄우지 않는다.

## 왜 필요한가 (실측 2026-08-27)

`POST /admin/secrets/{name}/test` 는 **등기 계열 4개 키만** 실제 점검하고,
나머지는 전부 이렇게 돌려줬다:

    return {"ok": True, "message": "값이 설정되어 있습니다(전용 테스트 미지원 키)."}

화면(`ApiKeyManagementPanel`)은 그것을 **초록 「연결 성공」** 으로 그린다.
→ **LLM 키가 401(무효)이거나 402/429(크레딧·레이트)여도 관리자는 「성공」으로 읽는다.**

★그리고 **바로 위 주석이 이미 그 원칙을 적어 뒀다**:

> ★'테스트'는 실제 호출 가능 여부를 물어야 한다 — 키가 저장돼 있다는 이유로 초록을
> 띄우면, 벤더가 권한 없다고 거절하는 상태를 사용자가 알 수 없다.

**그 원칙이 등기 키에만 적용돼 있었다.** 그리고 그것을 적용할 진단 도구
(`/admin/secrets/llm-health`·`image-health`)는 **이미 있었고 프론트 소비처가 0** 이었다
(라우트 도달률 실측: 둘 다 「확정 고아」).

★이건 이 저장소가 반복해 데인 형태다 — *"처방을 적용한 범위 = 결함이 사는 범위인지 확인하라"*.

## 무엇을 잠그나

1. **매핑이 파생인가** — `_LLM_KEY_PROVIDER` 는 `llm_health` 의 `env_map` 을 뒤집은 것이다.
   두 표가 갈리면 실패한다(손 목록이 상한이 되지 않게).
2. **실호출 경로를 태우는가** — LLM/이미지 키는 `*_health` 를 호출해야 한다.
3. ★**실패 사유를 버리지 않는가** — `error_type` 이 메시지에 실려야 관리자가 무엇을 고칠지 안다.
4. **두 모집단** — 전용 테스트가 없는 키는 종전 문구를 유지한다(전면 변경이 아니다).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1]
_MOD = _API / "app" / "routers" / "admin_secrets.py"


class ScannerDeadError(RuntimeError):
    """추출기가 죽었다 — **위반이 아니다**(`AssertionError` 와 다른 예외)."""


def _src() -> str:
    return _MOD.read_text(encoding="utf-8")


def _dict_literal(name: str) -> dict[str, str]:
    """모듈 최상위 dict 리터럴을 ast 로 읽는다."""
    tree = ast.parse(_src())
    for node in tree.body:
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        )
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name and isinstance(node.value, ast.Dict):
                out = {}
                for k, v in zip(node.value.keys, node.value.values, strict=False):
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                        out[k.value] = v.value
                return out
    raise ScannerDeadError(f"{name} 딕셔너리를 못 읽었다 — 표기가 바뀌었다(위반 아님).")


def _env_map_in(func_name: str) -> dict[str, str]:
    """`llm_health` 내부의 `env_map = {...}` 을 ast 로 읽는다(정규식으로 안 읽는다)."""
    tree = ast.parse(_src())
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef) or fn.name != func_name:
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name) and t.id == "env_map" and isinstance(n.value, ast.Dict):
                        return {
                            k.value: v.value
                            for k, v in zip(n.value.keys, n.value.values, strict=False)
                            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)
                        }
    raise ScannerDeadError(f"{func_name} 의 env_map 을 못 읽었다(위반 아님).")


def test_extractors_are_alive() -> None:
    """★공허한 초록 방지 + 양성 대조군."""
    env_map = _env_map_in("llm_health")
    mapping = _dict_literal("_LLM_KEY_PROVIDER")
    assert len(env_map) >= 3, f"env_map 이 {len(env_map)}개 — 추출기가 죽었다"
    assert len(mapping) >= 3, f"매핑이 {len(mapping)}개 — 추출기가 죽었다"
    assert "anthropic" in env_map and "ANTHROPIC_API_KEY" in mapping


def test_llm_key_mapping_is_derived_from_env_map() -> None:
    """★손 목록이 상한이 되지 않게 — 두 표가 갈리면 실패한다.

    `llm_health` 에 프로바이더를 추가하면 이 테스트가 **매핑도 추가하라고 강제**한다.
    """
    env_map = _env_map_in("llm_health")          # provider → ENV_NAME
    mapping = _dict_literal("_LLM_KEY_PROVIDER")  # ENV_NAME → provider
    expected = {env: prov for prov, env in env_map.items()}
    missing = sorted(set(expected) - set(mapping))
    extra = sorted(set(mapping) - set(expected))
    assert not missing, (
        f"llm_health 는 아는데 테스트 매핑에 없는 키: {missing}. "
        "그 키를 「테스트」하면 실호출 없이 초록이 뜬다."
    )
    assert not extra, f"매핑에만 있고 llm_health 가 모르는 키: {extra}"
    for env, prov in expected.items():
        assert mapping[env] == prov, f"{env} 의 프로바이더가 다르다: {mapping[env]} vs {prov}"


def _code() -> str:
    """주석을 걷은 실행 소스(소스 검사가 주석에 뚫리지 않게)."""
    return re.sub(r"^\s*#[^\n]*$", "", _src(), flags=re.M)


def test_test_endpoint_burns_the_live_health_path() -> None:
    """★배선 — 매핑이 **있는 것**과 테스트가 **태우는 것**은 다른 명제다."""
    code = _code()
    i = code.find('@router.post("/{name}/test")')
    assert i > 0, "테스트 엔드포인트를 못 찾았다(위반 아님 — 구조가 바뀌었다)"
    body = code[i:]
    assert "await llm_health(" in body, "LLM 키 경로가 llm_health 를 안 태운다"
    assert "await image_health(" in body, "이미지 키 경로가 image_health 를 안 태운다"


def test_failure_reason_is_not_swallowed() -> None:
    """★실패 사유를 버리지 않는다 — 401/402/429/모델거부가 구별돼야 고칠 수 있다.

    ★**소스에 `error_type` 이 있는지 보면 안 잠긴다.** 첫 판이 그랬고, 반환문만
    `{"ok": False, "message": "테스트 실패"}` 로 바꾸는 변이가 **생존**했다
    (변수 대입은 그대로라 소스 검사가 통과한다). **행위를 태운다** — 순수 함수를 직접 부른다.
    """
    from app.routers.admin_secrets import _health_to_test_result

    # 두 모집단: 사유가 다르면 메시지도 달라야 한다(같으면 구별 불가).
    a = _health_to_test_result(
        {"ok": False, "error_type": "AuthenticationError", "error": "invalid api key"}, "LLM(anthropic)"
    )
    b = _health_to_test_result(
        {"ok": False, "error_type": "RateLimitError", "error": "credit balance too low"}, "LLM(anthropic)"
    )
    assert a["ok"] is False and b["ok"] is False
    assert "AuthenticationError" in a["message"], f"사유가 메시지에 없다: {a['message']!r}"
    assert "RateLimitError" in b["message"], f"사유가 메시지에 없다: {b['message']!r}"
    assert a["message"] != b["message"], "서로 다른 실패가 같은 문구를 낸다 — 구별 불가"
    # 조사자가 근거를 잃지 않게 원본을 싣는다.
    assert a.get("detail", {}).get("error") == "invalid api key"

    ok = _health_to_test_result({"ok": True, "reply": "PONG"}, "LLM(anthropic)")
    assert ok["ok"] is True and "성공" in ok["message"]


def test_generic_keys_are_withheld_not_falsely_green() -> None:
    """★두 모집단 — 전용 테스트가 **없는** 키는 「보류」이지 성공이 아니다.

    ## 이 단언이 왜 바뀌었나 (2026-09-02)

    `#899` 시점의 원문은 *"종전 문구(`전용 테스트 미지원 키`)를 유지한다"* 였다.
    그때는 **변경 범위를 LLM/이미지로 한정**한다는 뜻이었고 옳았다.

    그런데 그 「종전 문구」는 `{"ok": True, "message": "값이 설정되어 있습니다(전용 테스트
    미지원 키)."}` 였다 — **`#899` 자신이 고치려던 「값만 있어도 초록」의 마지막 잔여**다.
    `#942` 가 그것을 `withheld(NOT_APPLICABLE)`(`ok=None` + 사유 코드)로 바꿨다.

    ★**원 의도(두 모집단)는 그대로 지킨다** — LLM/이미지는 **실호출**, 그 외는 **보류**.
      바뀐 것은 *"그 외"* 가 **초록이 아니게** 된 것뿐이다.
    """
    code = _code()
    assert "_unsupported(name)" in code, "미지원 키 분기가 사라졌다(두 모집단 중 하나가 없다)"
    assert "NOT_APPLICABLE" in code, "미지원이 닫힌 어휘 사유 코드를 쓰지 않는다"
    # ★음성 대조군 — **거짓 초록이 되살아나지 않았는지** 본다(이 파일의 존재 이유).
    assert '"ok": True, "message": "값이 설정되어 있습니다' not in code, (
        "미지원 키가 다시 `ok: True` 로 돌아갔다 — `#899`·`#942` 가 함께 지우던 그 결함이다"
    )


@pytest.mark.parametrize("env_name", ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"])
def test_regression_the_keys_that_were_falsely_green(env_name: str) -> None:
    """회귀 고정 — 종전에 **실호출 없이 초록**이던 바로 그 키들."""
    assert env_name in _dict_literal("_LLM_KEY_PROVIDER"), (
        f"{env_name} 가 매핑에서 빠졌다 — 다시 '값만 있어도 초록'이 된다."
    )
