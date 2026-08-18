#!/usr/bin/env python3
"""백엔드 라우트 중 **프론트 소비처가 0인 것**을 파생형으로 뽑는다.

【왜 이 도구가 생겼나 — 2026-08-18】
"기능은 있는데 화면에 안 붙어 동작하지 않는다"가 이 저장소에서 반복됐다:
  · P2 매입전략(`/registry/survey/strategy`) — 백엔드 배포됨, 프론트 소비처 0
  · 종합 부지분석(`/analysis`) — 라우트 live, 생성허브·랜딩 어디에도 카드 없음
  · AVM 항공영상 — Next 라우트가 백엔드에 가려져 404
사람이 세면 매번 다른 수가 나온다. 그래서 **기계가 센다.**

【★측정 함정 — 이 도구가 존재하는 두 번째 이유】
`apiClient` 가 `/api/v1` 을 **자동으로 붙인다**. 그래서 프론트는 접두사 **없이** 쓴다.
접두사를 붙인 채로 대조하면 **위양성이 대량 발생한다**(첫 측정에서 227 → 보정 후 123, 위양성 104).
→ 이 도구는 접두사 있는/없는 형태를 **둘 다** 본다.

【★★역방향 스윕은 이 도구로 하지 마라 (2026-08-18 실패 기록)】
"프론트가 부르는데 백엔드에 없는 경로"를 같은 정규식으로 뽑았더니 **121건**이 나왔고,
`include_router(prefix=...)` 를 반영해 **19건**으로 줄었는데 그 19건도 라이브 확인 결과
**전부 존재**했다(401/405 — 404 아님). 즉 **정규식 추출로는 역방향 판정이 불가능**하다:
서빙 경로를 하나라도 놓치면 그만큼 그대로 오보가 된다(순방향은 반대로 **과소** 보고라 안전).
→ 역방향이 필요하면 **실행 중인 앱의 라우트 테이블**(`app.routes`)을 정답으로 써라. 정규식이 아니라.

【한계 — 이 수치를 "결함 수"로 읽지 마라】
소비처 0 ≠ 결함이다. 정당하게 백엔드 내부용인 라우트가 섞인다(운영·정리·알림 발송 등).
이 도구는 **후보를 좁힐 뿐**이고, 진짜 결함인지는 사람이 라우트별로 판단해야 한다.
분류(`--kind`)는 **거친 휴리스틱**이며 그 자체가 검증된 적 없다.

사용:  python3 scripts/orphan_routes.py            # 요약
       python3 scripts/orphan_routes.py --list     # 전체 목록
"""
from __future__ import annotations

import os
import re
import sys

API_DIR = os.path.join(os.path.dirname(__file__), "..", "apps", "api")
WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "apps", "web")


def _mount_prefixes() -> dict[str, str]:
    """`main.py` 의 `include_router(<mod>.router, prefix="...")` 에서 **마운트 접두사**를 읽는다.

    ★이것이 없으면 라우터 파일에 `APIRouter(prefix=...)` 가 없는 모듈이 통째로 누락된다.
      실측(2026-08-18): 이 누락으로 `/auction/*` 전체가 "백엔드에 없음"으로 잘못 잡혔다
      (라이브 확인 결과 405 = 존재함). **대조군 하나가 121건 오보를 막았다.**
    """
    out: dict[str, str] = {}
    main = os.path.join(API_DIR, "main.py")
    try:
        src = open(main, encoding="utf-8", errors="ignore").read()
    except OSError:
        return out
    for m in re.finditer(r'include_router\(\s*([A-Za-z_][\w.]*)\.router\s*,\s*prefix\s*=\s*["\']([^"\']+)', src):
        out[m.group(1).split(".")[-1]] = m.group(2)
    return out


def backend_routes() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    mounts = _mount_prefixes()
    for root, _, files in os.walk(API_DIR):
        if "/tests" in root or "node_modules" in root:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            try:
                src = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            pref = re.search(r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)', src, re.S)
            # 라우터 자체 prefix 가 없으면 main.py 의 마운트 접두사를 쓴다(모듈명으로 매칭).
            pfx = pref.group(1) if pref else mounts.get(os.path.splitext(f)[0], "")
            for m in re.finditer(r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']', src):
                full = (pfx + m.group(2)).replace("//", "/")
                if full and full != "/":
                    out.setdefault(full, (m.group(1), os.path.relpath(p, API_DIR)))
    return out


def frontend_blob() -> str:
    parts: list[str] = []
    for root, _, files in os.walk(WEB_DIR):
        if "node_modules" in root or "/.next" in root:
            continue
        for f in files:
            if f.endswith((".ts", ".tsx")) and not f.endswith((".test.ts", ".test.tsx", ".spec.ts")):
                try:
                    parts.append(open(os.path.join(root, f), encoding="utf-8", errors="ignore").read())
                except OSError:
                    pass
    return "\n".join(parts)


def is_consumed(full: str, blob: str) -> bool:
    """★접두사 있는/없는 형태를 둘 다 본다(apiClient 가 /api/v1 을 자동 부착)."""
    cands = {full, re.sub(r"^/api/v[12]", "", full)}
    for c in list(cands):
        cands.add(c.split("{")[0].rstrip("/"))
    return any(c and len(c) > 5 and c in blob for c in cands)


def orphans() -> list[tuple[str, str, str]]:
    routes = backend_routes()
    blob = frontend_blob()
    # ★대조군 — 조회기가 죽으면 전부 "소비처 0"으로 보인다. 그 경우 시끄럽게 실패한다.
    if "apiClient" not in blob:
        raise SystemExit("★프론트 스캔이 비었다(조회기 사망) — apiClient 가 한 번도 안 보인다")
    return [(f, m, p) for f, (m, p) in sorted(routes.items()) if not is_consumed(f, blob)]


if __name__ == "__main__":
    items = orphans()
    total = len(backend_routes())
    print(f"백엔드 라우트 {total} · 프론트 소비처 0 = {len(items)}")
    if "--list" in sys.argv:
        for f, m, p in items:
            print(f"  {m.upper():6s} {f:52s} {p}")
