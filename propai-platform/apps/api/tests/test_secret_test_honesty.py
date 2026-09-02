"""키 「테스트」가 **거짓 초록을 내지 않는다** + 두 손목록이 **한 원천**에서 나온다.

## 왜 (2026-09-02 실측 · origin/main)

`POST /admin/secrets/{name}/test` 가 **전용 테스트 미지원 키**에 대해 이렇게 답했다:

    {"ok": True, "message": "값이 설정되어 있습니다(전용 테스트 미지원 키)."}

★**바로 위 분기의 주석이 그것을 금지하고 있었다**:
  *"'테스트'는 실제 호출 가능 여부를 물어야 한다 — 키가 저장돼 있다는 이유로 초록을 띄우면,
    벤더가 권한 없다고 거절하는 상태를 사용자가 알 수 없다."*
**같은 파일이 자기 원칙을 두 줄 뒤에서 어겼다.** `#932` 가 **화면**의 존재 배지에서 성공색을
걷어냈는데 **API 응답에는 그대로** 남아 있던 **형제 미러**다.

## 모집단 (파생형 · ast)

    secret_store.CATALOG        41키
    전용 테스트 지원              4키
    ★나머지                     37키  ← 버튼 미렌더 + 백엔드는 ok:True

## ★그리고 손목록이 **두 언어에 각각** 있었다

백엔드 인라인 집합 리터럴 ↔ 프론트 컴포넌트 안 인라인 배열. **대조 락 0건.**
갈리면: 백엔드만 추가 → 버튼이 안 뜬다 / 프론트만 추가 → 「미지원」이 **초록으로** 나갔다.

★**축을 「존재」가 아니라 「소비」까지 내린다** — 상수를 만들어 놓고 분기가 인라인 리터럴을
  그대로 쓰면 상수는 장식이다(#938 에서 «축이 한 층 위면 그 아래는 무잠금» 을 배웠다).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.routers import admin_secrets as AS
from app.services.secrets import secret_store as SS
from app.utils.withheld import NOT_APPLICABLE, is_withheld

_API = Path(__file__).resolve().parents[1]
_ROUTER_SRC = _API / "app" / "routers" / "admin_secrets.py"
_PANEL = _API.parent / "web" / "components" / "settings" / "ApiKeyManagementPanel.tsx"

#: `.tsx` 배열 원소 — **세 표기를 모두** 받는다(`"k"` · `'k'` · `` `k` ``).
#: ★한 표기만 받으면 나머지가 조용히 누락돼 **전수 일치가 거짓으로 참**이 된다(#938 실측).
_TS_ITEM = re.compile(r"""["'`]([A-Z][A-Z0-9_]*)["'`]""")


def frontend_testable() -> list[str]:
    src = _PANEL.read_text(encoding="utf-8")
    m = re.search(r"const TESTABLE_SECRETS:[^=]*=\s*\[(.*?)\];", src, re.S)
    assert m, "★프론트 TESTABLE_SECRETS 를 못 찾았다 — 조회기 사망(이름이 바뀌었나?)"
    return _TS_ITEM.findall(m.group(1))


def catalog_names() -> list[str]:
    return [c["name"] for c in SS.CATALOG]


def test_extractors_are_alive_before_any_comparison():
    """★생존 단언을 **비교 앞에** — 추출이 비면 «전수 일치» 가 공허하게 참이 된다."""
    assert _PANEL.is_file(), "패널 파일이 없다(경로가 바뀌었나?)"
    assert len(AS._TESTABLE_SECRETS) >= 3
    assert len(frontend_testable()) >= 3
    # ★원천과 결속 — 디스크에서 **독립 재계수**한 수와 같아야 한다(자기지시적 기대값 회피).
    raw = len(re.findall(r'"[A-Z][A-Z0-9_]*",', _PANEL.read_text(encoding="utf-8")
                         .split("const TESTABLE_SECRETS")[1].split("];")[0]))
    assert raw == len(frontend_testable()), f"정규식 파생 {len(frontend_testable())} vs 재계수 {raw}"
    assert len(catalog_names()) >= 30, "카탈로그가 비었다 — 조회기 사망"


def test_front_and_back_testable_lists_match_exactly():
    """두 언어의 손목록이 **전수 일치**. 갈리면 버튼이 없거나 거짓 초록이 나간다."""
    assert sorted(frontend_testable()) == sorted(AS._TESTABLE_SECRETS)


def test_the_branch_actually_dispatches_on_the_constant():
    """★상수를 **분기가 실제로 쓰는가** — 만들어 놓고 인라인 리터럴을 쓰면 상수는 장식이다.

    #938 에서 배운 것: 축을 「존재」가 아니라 **「소비」**까지 내린다.
    """
    src = _ROUTER_SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    used = any(
        isinstance(n, ast.Compare) and isinstance(n.comparators[0], ast.Name)
        and n.comparators[0].id == "_TESTABLE_SECRETS"
        for n in ast.walk(tree)
    )
    assert used, "분기가 `name in _TESTABLE_SECRETS` 를 쓰지 않는다 — 상수가 장식이다"
    # 음성 대조군 — 옛 인라인 리터럴이 **남아 있지 않다**(두 벌이면 한쪽만 고쳐진다).
    assert '{"HYPHEN_HKEY", "HYPHEN_USER_ID"' not in src, "인라인 손목록이 아직 남아 있다"


def test_every_testable_key_is_in_the_catalog():
    """테스트 버튼이 있는 키는 **관리 화면에서 조회 가능**해야 한다(카탈로그 등재)."""
    missing = [k for k in AS._TESTABLE_SECRETS if k not in catalog_names()]
    assert not missing, f"테스트 대상인데 카탈로그에 없다(운영자가 볼 수 없다): {missing}"


def test_moleg_key_is_managed_because_production_depends_on_it():
    """★`MOLEG_API_KEY` 가 카탈로그에 있다 — 프로덕션이 그 키로 실제 동작한다.

    실측(2026-09-02, 실행 중 컨테이너): 설정됨 · 법제처 호출 **HTTP 200 `<OrdinSearch>`
    `resultCode 00`**. 그런데 카탈로그에 없어 **운영자가 조회·교체할 수 없었다** —
    「키가 없다」가 아니라 **「화면이 그것을 모른다」** 였다.
    ★키가 만료·교체되면 조례 조회가 실패하고, 그 실패는 `#938` 이 봉합한 그 경로다.
    """
    assert "MOLEG_API_KEY" in catalog_names()


# ---------------------------------------------------------------------------
# ★행위 — **두 모집단**으로 가른다
# ---------------------------------------------------------------------------


async def _call_route(monkeypatch, name: str) -> dict:
    """★**실제 라우트 핸들러를 태운다** — 응답을 테스트에서 다시 만들지 않는다.

    ★첫 판은 `_unsupported_response()` 로 **응답 구성을 복제**했다. 그 결과
      «`ok: True` 복원» 과 «`None` → `False`» 변이가 **둘 다 SURVIVED** 했다 —
      **원래 결함 그 자체가 무잠금**이었다. 락이 태운 것이 프로덕션 코드가 아니라
      **내 복제본**이었기 때문이다.
      자문: ***"내 락이 태우는 것이 프로덕션 코드인가, 복제본인가?"***

    네트워크·인증만 가로채고 **분기·응답 구성은 진짜가 돈다.**
    """
    async def _noop(current, db):  # noqa: ANN001 — 권한 검사만 우회
        return None

    monkeypatch.setattr(AS, "_require_admin", _noop)
    monkeypatch.setenv(name, "dummy-value-for-test")
    return await AS.test_secret(name, current=object(), db=object())


def test_unsupported_key_is_not_reported_as_success(monkeypatch):
    """★미지원 키가 **성공으로 위장되지 않는다** — 종전엔 `ok: True` 였다."""
    import asyncio

    r = asyncio.run(_call_route(monkeypatch, "VWORLD_API_KEY"))
    assert not r["ok"], f"미지원인데 truthy 다(거짓 초록): {r['ok']!r}"
    assert r["ok"] is None, "「모름」은 False 가 아니라 None 이어야 한다(실패와 구별)"
    assert r["ok_absent"] == NOT_APPLICABLE, "사유 코드가 닫힌 어휘가 아니다"
    assert is_withheld(r, "ok"), "보류 3종 세트를 만족하지 않는다"
    assert "테스트가 없습니다" in r["message"], "사람이 읽을 사유가 없다(무언 보류)"


def test_missing_value_is_a_failure_not_a_withheld(monkeypatch):
    """★**세 번째 모집단** — 값이 없으면 그건 「미지원」이 아니라 **실패**다.

    둘을 뭉개면 *"키를 안 넣었다"* 와 *"테스트가 없다"* 가 화면에서 같아 보인다.
    """
    import asyncio

    async def _noop(current, db):  # noqa: ANN001
        return None

    monkeypatch.setattr(AS, "_require_admin", _noop)
    monkeypatch.delenv("VWORLD_API_KEY", raising=False)
    r = asyncio.run(AS.test_secret("VWORLD_API_KEY", current=object(), db=object()))
    assert r["ok"] is False, f"값 없음이 False 가 아니다: {r['ok']!r}"
    assert "ok_absent" not in r, "값 없음은 보류가 아니라 실패다(어휘를 섞지 마라)"


def test_supported_key_does_not_take_the_unsupported_path(monkeypatch):
    """★**두 번째 모집단** — 지원 키는 미지원 분기로 가지 않는다.

    이것이 없으면 *"항상 미지원을 돌려주는 구현"* 이 위 락을 통과한다.
    실제 벤더 호출은 나가지 않게 `RegistryService.live_status` 를 대역으로 바꾼다
    (★네트워크만 가로채고 **분기 판정은 진짜가 돈다**).
    """
    import asyncio

    from app.services.registry import registry_service as RS

    async def _fake_status(self):  # noqa: ANN001
        return {"configured": True, "provider": "hyphen", "message": "대역"}

    monkeypatch.setattr(RS.RegistryService, "live_status", _fake_status)
    r = asyncio.run(_call_route(monkeypatch, "TILKO_API_KEY"))
    assert "ok_absent" not in r, f"지원 키가 미지원 분기로 갔다: {r}"
    assert r["ok"] is True, f"지원 키가 실제 상태를 반영하지 않는다: {r}"
