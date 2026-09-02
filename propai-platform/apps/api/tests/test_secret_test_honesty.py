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

from app.core.config import settings as _settings  # ★수집 시점에 인스턴스화 고정(위 락 참조)
from app.routers import admin_secrets as AS
from app.services.legal.moleg_drf_envelope import moleg_oc_key
from app.services.secrets import secret_store as SS
from app.utils.withheld import NOT_APPLICABLE, is_withheld, validate_withheld_pair

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
    # ★주석을 걷어내고 본다 — 주석 속 대문자 토큰이 목록으로 세어지면 **정상 코드가 위반**이 된다.
    body = re.sub(r"//[^\n]*", "", m.group(1))
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    return _TS_ITEM.findall(body)


def catalog_names() -> list[str]:
    return [c["name"] for c in SS.CATALOG]


def test_extractors_are_alive_before_any_comparison():
    """★생존 단언을 **비교 앞에** — 추출이 비면 «전수 일치» 가 공허하게 참이 된다."""
    assert _PANEL.is_file(), "패널 파일이 없다(경로가 바뀌었나?)"
    assert len(AS._TESTABLE_SECRETS) >= 3
    assert len(frontend_testable()) >= 3
    # ★원천과 결속 — 디스크에서 **독립 재계수**한 수와 같아야 한다(자기지시적 기대값 회피).
    # ★재계수는 **다른 매체**로 한다. 첫 판은 같은 정규식을 상위집합에 적용해
    #   **구조적으로 실패 불가능**했다(독립 제3 렌즈 지적) — 「자기지시적 기대값 회피」를
    #   적어 놓고 회피가 안 됐다. 여기서는 **줄 단위로 세어** 정규식과 다른 축을 쓴다.
    body = _PANEL.read_text(encoding="utf-8").split("const TESTABLE_SECRETS")[1].split("];")[0]
    body_nc = re.sub(r"//[^\n]*", "", body)
    body_nc = re.sub(r"/\*.*?\*/", "", body_nc, flags=re.S)
    by_line = [ln for ln in body_nc.splitlines() if re.search(r"[A-Z][A-Z0-9_]{2,}", ln)]
    assert len(by_line) == len(frontend_testable()), (
        f"정규식 파생 {len(frontend_testable())} vs 줄 단위 재계수 {len(by_line)} — 추출기가 일부를 놓친다")
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
    # ★저장소 **표준 검증기**로도 통과해야 한다. `is_withheld` 는 문구를 **아예 안 보므로**
    #   그것만 쓰면 「무언 보류 금지」가 이 자리에서 무잠금이다(독립 리뷰 MEDIUM-1).
    #   문구를 `message` 에 실었으니(기존 스키마 유지) 검증도 그 키로 한다.
    assert validate_withheld_pair(r, "ok", text_field="message") == [], (
        "표준 검증기가 계약 위반을 신고한다")
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


# ---------------------------------------------------------------------------
# ★HIGH-2 — 카탈로그 등재가 **작동하는 조작 수단**인가
# ---------------------------------------------------------------------------


def test_no_consumer_reads_the_moleg_key_from_settings_directly():
    """★MOLEG 키를 **`settings` 계열에서 직접** 읽는 소비처가 없다.

    시크릿 저장은 `os.environ` **만** 바꾸는데 `settings` 는 모듈 싱글턴(`@lru_cache`)이라
    **재동기화 경로가 0건**이다. 직접 읽으면 운영자가 화면에서 키를 바꿔도 **「저장됨」
    초록만 뜨고 아무것도 안 바뀐다** — **작동하지 않는 조작 수단**이다.

    ## ★독립 제3 렌즈가 이 락의 두 구멍을 찾았다

    · **범위가 좁았다** — `app/` 만 봤는데 `apps/api/` 에 **나란히 살아 있는 트리**가 있고
      (`main.py` 가 `apps.api.routers` 를 **10건** 등록한다) 그 176 파일이 감시 밖이었다.
      → `_API` 전체로 올린다(`tests/` 는 제외 — 픽스처가 일부러 옛 경로를 쓸 수 있다).
    · **문자열 검사라 별칭 한 줄로 우회**됐다 — `get_settings()` 를 `cfg` 에 담아 읽으면
      같은 결함인데 락은 초록이었다. → **`ast` 로 판정**한다(이 파일의 다른 락과 매체를 맞춘다).

    ★**포지티브 판정**으로 뒤집는다 — *"`settings` 라는 이름을 쓰는가"* 가 아니라
      *"`MOLEG_API_KEY` 를 읽으면서 `moleg_oc_key` 를 안 쓰는가"* 를 본다. 별칭에 강하다.
    """
    import ast as _ast

    offenders: list[str] = []
    scanned = 0
    for f in _API.rglob("*.py"):
        rel = f.relative_to(_API)
        if rel.parts[0] in {"tests", "__pycache__"} or f.name in {
            "config.py", "moleg_drf_envelope.py", "secret_store.py"
        }:
            continue
        src = f.read_text(encoding="utf-8")
        if "MOLEG_API_KEY" not in src:
            continue
        scanned += 1
        tree = _ast.parse(src)
        # 문자열/속성 어디로 읽든 잡되, 같은 파일이 `moleg_oc_key` 를 쓰면 정상으로 본다.
        # ★**설정 객체에서 읽는 것만** 위반이다. 키 **이름 문자열**(예: 내보낼 시크릿
        #   목록의 원소)이나 `os.environ.get("MOLEG_API_KEY")` 는 정상이다 —
        #   첫 판이 바 문자열까지 잡아 `export_scoped_secrets.py`(이름 목록)를
        #   **위양성으로 신고**했다. **가드의 위양성도 결함이다**(§A-6).
        reads = any(
            (isinstance(n, _ast.Attribute) and n.attr == "MOLEG_API_KEY")
            or (
                isinstance(n, _ast.Call)
                and isinstance(n.func, _ast.Name)
                and n.func.id == "getattr"
                and len(n.args) >= 2
                and isinstance(n.args[1], _ast.Constant)
                and n.args[1].value == "MOLEG_API_KEY"
            )
            for n in _ast.walk(tree)
        )
        uses_helper = any(
            isinstance(n, _ast.Name) and n.id == "moleg_oc_key" for n in _ast.walk(tree)
        )
        if reads and not uses_helper:
            offenders.append(str(rel))
    assert not offenders, (
        f"MOLEG 키를 읽으면서 `moleg_oc_key()` 를 안 쓴다"
        f"(관리 화면 저장이 무효가 된다): {offenders}")
    # ★음성 대조군 — 조회기가 살아 있는가(대상이 0개면 위 단언이 공허하게 참이다).
    assert scanned >= 3, f"MOLEG 를 언급하는 파일이 {scanned}개 — 조회기 사망 의심"


def test_runtime_key_change_takes_effect_without_restart(monkeypatch):
    """★**두 경로를 서로 다른 값으로 가른다** — 같은 값이면 두 구현이 구별되지 않는다.

    ## 첫 판이 왜 공허했나 (독립 제3 렌즈가 실행으로 확증)

    종전 락은 `setenv` 만 하고 `settings` 는 안 건드렸다. 그런데 `moleg_oc_key()` 가
    `app.core.config` 를 **함수 안에서** 임포트하고, 이 PR 이 소비처들의 **모듈 최상단
    임포트를 지웠기 때문에**, 락 파일만 돌리면 `app.core.config` 가 **`setenv` 이후에
    최초 임포트**된다 → `BaseSettings` 가 그 env 값을 읽어 **`settings` 도 같은 값**이 된다.
    → *"`settings` 만 읽는 구현"* 으로 되돌려도 **SURVIVED**(원 결함이 무잠금이었다).

    ★그래서 **`settings` 를 모듈 최상단에서 먼저 임포트**해 인스턴스화 시점을 고정하고,
      **env 와 settings 에 다른 값**을 넣어 어느 쪽을 읽는지가 **답으로 드러나게** 한다.
    """
    monkeypatch.setattr(_settings, "MOLEG_API_KEY", "boot-value", raising=False)
    monkeypatch.setenv("MOLEG_API_KEY", "runtime-value")
    assert moleg_oc_key() == "runtime-value", (
        "런타임 갱신이 반영되지 않는다 — `settings` 만 읽는 구현이다"
        "(관리자 화면 저장이 무효가 된다)")

    # ★없으면 부팅 설정으로 떨어진다(반대 방향).
    monkeypatch.delenv("MOLEG_API_KEY", raising=False)
    assert moleg_oc_key() == "boot-value", "환경변수가 없을 때 부팅 설정으로 안 떨어진다"

    # ★빈 문자열이 부팅 설정을 **가리지 않는다**(경계를 양방향으로).
    monkeypatch.setenv("MOLEG_API_KEY", "   ")
    assert moleg_oc_key() == "boot-value", "빈 환경변수가 부팅 설정을 가린다"


def test_moleg_is_marked_secret_so_it_is_not_shown_in_plaintext():
    """★OC 값이 **평문으로 응답·화면에 뜨지 않는다**.

    `secret: False` 면 `/admin/secrets` 와 `/backups` 가 **원문**을 그대로 싣는다.
    `apps/api/scripts/export_scoped_secrets.py` 는 이 키를 이미 **스코프 시크릿으로 분류**하므로
    두 층을 맞춘다(독립 리뷰 MEDIUM-3).
    """
    entry = next(c for c in SS.CATALOG if c["name"] == "MOLEG_API_KEY")
    assert entry["secret"] is True
