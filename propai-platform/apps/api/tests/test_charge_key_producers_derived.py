"""파생형 락 — **백엔드가 가드한 과금 경로는 프론트가 키를 보내야 한다.**

## 왜 필요한가

백엔드에 `charge_once` 를 다 붙여도 **프론트가 `Idempotency-Key` 를 안 보내면 보호는 0** 이다
(가드는 키가 없으면 종전대로 실행한다 — 하위호환이 그렇게 설계돼 있다).
실측 시점에 가드된 경로는 10개인데 키를 보내는 호출부는 **1곳**이었다.
즉 "배선 완료"라고 쓰면 **거짓**이 되는 상태였다.

★이건 이 저장소의 단골 형태의 거울상이다 — 종전엔 "정의만 하고 소비처 0"이었고,
  여기서는 **"소비처(백엔드)는 준비됐는데 생산자(프론트)가 0"** 이다. 둘 다 조용하다.

## 무엇을 파생하는가

    ① 백엔드: `charge_once(... endpoint="X" ...)` 가 있는 핸들러 → 그 라우트의 **경로**를
       `@router.post("...")` 데코레이터 + 라우터 prefix 로 조립한다(경로를 손으로 적지 않는다).
    ② 프론트: 그 경로를 **실제로 POST 하는** 호출부를 찾는다(주석·타입은 제외 — 주석을
       호출로 세는 위양성이 이 세션에서 여러 번 났다).
    ③ 그 호출부가 `idempotencyHeaders(...)` 또는 `Idempotency-Key` 를 보내는지 본다.

## 면제

프론트 호출부가 **아직 없는** 경로는 면제가 아니라 **대상 없음**이다(보호할 트래픽이 없다).
그건 실패로 보지 않되, 호출부가 생기면 자동으로 걸린다 — 그게 파생형의 값이다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1]
_WEB = _API.parents[0] / "web"
_ROUTER_DIRS = (_API / "routers", _API / "app" / "routers", _API / "app" / "api" / "endpoints")

_JS_BLOCK = re.compile(r"/\*.*?\*/", re.S)
_JS_LINE = re.compile(r"(?<![:\w])//[^\n]*")
# 실제 POST 호출만 — `apiClient.post<T>("/path"` / `postV2<T>(`/path`” 형태.
_POST_CALL = re.compile(r"\.(?:post|postV2)\s*(?:<[^(]*?>)?\s*\(\s*[\"'`]([^\"'`]+)[\"'`]")


def _strip_js_comments(src: str) -> str:
    return _JS_LINE.sub("", _JS_BLOCK.sub("", src))



def _include_prefixes() -> dict[str, str]:
    """`main.py` 의 include_router 에서 **모듈명 → prefix** 를 파생한다."""
    main_py = _API / "main.py"
    if not main_py.exists():
        return {}
    out: dict[str, str] = {}
    for m in re.finditer(
        r"include_router\(\s*([A-Za-z_][\w.]*)\s*(?:,[^)]*?prefix\s*=\s*[\"']([^\"']+)[\"'])?",
        main_py.read_text(encoding="utf-8"),
    ):
        sym, pref = m.group(1), m.group(2) or ""
        mod = sym.split(".")[0]
        if pref:
            out.setdefault(mod, pref)
    return out


def _module_prefix(path: Path) -> str:
    """라우터 파일 → include_router prefix(없으면 빈 문자열)."""
    prefixes = _include_prefixes()
    stem = path.stem
    if stem in prefixes:
        return prefixes[stem]
    # sales/actions.py 처럼 심볼명이 파일명과 다른 경우 — 심볼 후보로도 찾는다.
    for sym, pref in prefixes.items():
        if sym and (sym in path.as_posix()):
            return pref
    return ""


def _guarded_paths() -> dict[str, str]:
    """가드된 핸들러 → HTTP 경로(prefix + 데코레이터 경로). 경로를 손으로 적지 않는다."""
    out: dict[str, str] = {}
    for d in _ROUTER_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.py")):
            if "__pycache__" in str(f):
                continue
            src = f.read_text(encoding="utf-8")
            if "charge_once" not in src:
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            # ★prefix 는 **라우터 파일이 아니라 `main.py` 의 include_router** 에서 붙는다.
            #   실측: auto_zoning·sales actions 둘 다 `APIRouter()` 에 prefix 가 없고
            #   `include_router(..., prefix="/api/v1/zoning")` 로 붙는다. 라우터 파일만 보면
            #   경로가 `/analyze` 처럼 **너무 일반적**이 되어 엉뚱한 프론트 호출과 매칭된다
            #   (실제로 `salesApi.ts` 가 오탐으로 잡혔다 — 위양성도 결함이다).
            # ★전체 경로 = include_router prefix **+** 라우터 파일 자체 prefix + 데코레이터 경로.
            #   **둘 중 하나만 보면 어느 쪽이든 틀린다** — 실측:
            #     registry.py    : APIRouter(prefix="/registry")   · main.py 에는 prefix 없음
            #     auto_zoning.py : APIRouter()(자체 없음)          · main.py 에 "/api/v1/zoning"
            #   한 출처만 읽었을 때 각각 "경로 못 찾음"과 "너무 일반적이라 오탐"이 났다.
            own = ""
            _m = re.search(r'APIRouter\(\s*prefix\s*=\s*["\']([^"\']+)["\']', src)
            if _m:
                own = _m.group(1)
            inc = _module_prefix(f)
            # ★중복 접두사 방어 — 라우터 자체 prefix 가 이미 include prefix 를 포함하면
            #   합치면 "/api/v1/design/api/v1/design/..." 처럼 두 번 붙는다(실측).
            prefix = own if (own and own.startswith(inc)) else (inc + own)
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
                    continue
                guarded = any(
                    isinstance(n, ast.AsyncWith)
                    and any(
                        isinstance(i.context_expr, ast.Call)
                        and (getattr(i.context_expr.func, "id", "")
                             or getattr(i.context_expr.func, "attr", "")) == "charge_once"
                        for i in n.items
                    )
                    for n in ast.walk(fn)
                )
                if not guarded:
                    continue
                for deco in fn.decorator_list:
                    if not isinstance(deco, ast.Call):
                        continue
                    attr = getattr(deco.func, "attr", "")
                    if attr not in {"post", "put", "patch"}:
                        continue
                    if deco.args and isinstance(deco.args[0], ast.Constant):
                        out[fn.name] = (prefix + str(deco.args[0].value)).replace("//", "/")
    return out


def _frontend_post_sites() -> list[tuple[str, str, bool]]:
    """(파일, POST 경로, 키전송여부) — 주석 제거 후 **실제 호출**만."""
    sites: list[tuple[str, str, bool]] = []
    for f in sorted(list(_WEB.rglob("*.ts")) + list(_WEB.rglob("*.tsx"))):
        rel = f.relative_to(_WEB).as_posix()
        if "node_modules" in rel or "/__tests__/" in rel or rel.startswith("app/api/"):
            continue
        src = _strip_js_comments(f.read_text(encoding="utf-8", errors="ignore"))
        for m in _POST_CALL.finditer(src):
            path = m.group(1)
            # 호출 옵션 블록(대략 800자) 안에서 키 전송을 본다.
            window = src[m.end(): m.end() + 800]
            sends = ("idempotencyHeaders" in window) or ("Idempotency-Key" in window)
            sites.append((rel, path, sends))
    return sites


def _matches(front_path: str, backend_path: str) -> bool:
    """프론트 경로가 백엔드 라우트에 대응하는가(경로 파라미터는 와일드카드로 본다)."""
    # ★버전 접두사(/api/v1·/api/v2)는 **양쪽에서 벗긴다.**
    #   프론트는 `apiClient` 가 내부에서 붙이므로 호출부에는 `/registry/bulk` 만 적힌다.
    #   이걸 안 벗기면 세그먼트 수가 달라 **전부 "호출부 없음"으로 skip** 된다 —
    #   실측으로 10경로 중 9개가 그렇게 조용히 비어 있었다(공허한 초록 직전이었다).
    _ver = re.compile(r"^/api/v\d+")
    fp = _ver.sub("", front_path.split("?")[0]).rstrip("/")
    bp = _ver.sub("", backend_path).rstrip("/")
    # 백엔드 `{param}` → 프론트는 `${...}` 보간이라 세그먼트 수 + 고정 세그먼트로 대조한다.
    b_seg = [s for s in bp.split("/") if s]
    f_seg = [s for s in fp.split("/") if s]
    if len(b_seg) != len(f_seg):
        return False
    for b, ff in zip(b_seg, f_seg, strict=True):
        if b.startswith("{"):
            continue
        if "${" in ff:
            # ★보간 세그먼트라도 **리터럴 접두사는 일치해야** 한다.
            #   무조건 와일드카드로 보면 제네릭 래퍼(`/sales${p}`)가 아무 경로에나 매칭돼
            #   위양성이 난다(실측: `salesApi.ts` 가 /provision·/analyze·/run 에 전부 걸렸다).
            lit = ff.split("${", 1)[0]
            if lit and not b.startswith(lit):
                return False
            continue
        if b != ff:
            return False
    return True


def test_추출기가_살아_있다():
    """★공허 진리 가드 — 한쪽이 0이면 아래 단언이 전부 무의미하다."""
    guarded = _guarded_paths()
    sites = _frontend_post_sites()
    assert len(guarded) >= 8, f"가드된 경로를 {len(guarded)}개밖에 못 찾았다: {guarded}"
    assert len(sites) >= 20, f"프론트 POST 호출부를 {len(sites)}개밖에 못 찾았다"
    # 양성 대조 — 확실히 있는 것이 실제로 잡히는가.
    assert any(p.endswith("/registry/bulk") for p in guarded.values()), "registry.bulk 를 못 찾았다"
    assert any(s for _f, p, s in sites if p.endswith("/registry/bulk")), (
        "registry/bulk 호출부가 키를 보내는 것으로 안 잡힌다 — 탐지기가 죽었다"
    )


@pytest.mark.parametrize("fn_path", sorted(_guarded_paths().items()))
def test_가드된_경로를_부르는_프론트는_키를_보낸다(fn_path: tuple[str, str]):
    """★가드가 있어도 키가 없으면 보호는 0이다 — 생산자 쪽을 잠근다."""
    fn, path = fn_path
    callers = [(f, p, s) for f, p, s in _frontend_post_sites() if _matches(p, path)]
    if not callers:
        pytest.skip(f"{fn}({path}) — 프론트 호출부 없음(보호할 트래픽 자체가 없다)")
    missing = [f for f, _p, s in callers if not s]
    assert not missing, (
        f"{fn}({path}) 를 부르면서 Idempotency-Key 를 안 보내는 호출부가 있다 — "
        f"백엔드 가드가 있어도 **보호는 0**이다: {missing}. "
        f"`idempotencyHeaders(\"<scope>\", body)` 를 headers 에 넣어라."
    )
