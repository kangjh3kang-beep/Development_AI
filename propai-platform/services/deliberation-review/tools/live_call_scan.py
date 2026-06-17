"""INC-15 — INV-13 라이브 호출 정적검사(AST).

소비경로(adapters/regulation·adapters/legal·services/land·services/cross_validate)의 **캐시 우회 직접
네트워크 호출**(httpx/requests의 get/post/Client 등)을 위반으로 탐지한다. 허용 경로는 AdapterCache
(`cached_get`, adapters/cache — 스캔 대상 외)뿐. INV-13(소비측 라이브 미호출·무음0)을 코드로 강제 —
누군가 캐시를 우회하는 직접 httpx.get을 소비경로에 추가하면 AT가 차단한다(결정론·재현성 강화).

tools/static_scan.py(수치 하드코딩 스캐너)와 동일 위치·동일 AT 패턴.
"""
from __future__ import annotations

import ast

# 직접 라이브 호출로 간주하는 HTTP 모듈(공급측 LiveNetwork·캐시 내부 cached_get은 스캔 대상 외).
_HTTP_MODULES = ("httpx", "requests")
_LIVE_ATTRS = (
    "get", "post", "put", "delete", "patch", "head", "options",
    "request", "stream", "Client", "AsyncClient", "Session",
)


def scan_for_uncached_live_calls(source: str, allowlist: tuple[str, ...] = ()) -> list[str]:
    """source에서 캐시 우회 직접 호출 목록("httpx.get@L<line>") 반환. 없으면 []. 파싱 실패 시 [].

    탐지: `httpx.<net>(...)` / `requests.<net>(...)` (module 이름에 직접 attribute 호출). allowlist로 면제.
    한계(정직): 이름기반 — `import httpx as hx; hx.get()`처럼 별칭 import는 미탐(코드베이스 관례=`import httpx`).
    """
    hits: list[str] = []
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr in _LIVE_ATTRS
                and isinstance(func.value, ast.Name) and func.value.id in _HTTP_MODULES):
            token = f"{func.value.id}.{func.attr}"
            if token not in allowlist:
                hits.append(f"{token}@L{node.lineno}")
    return hits
