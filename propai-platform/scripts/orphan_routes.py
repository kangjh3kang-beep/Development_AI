#!/usr/bin/env python3
"""백엔드 라우트를 **확정 고아 / 판정 불가 / 확정 소비** 셋으로 가른다.

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
서빙 경로를 하나라도 놓치면 그만큼 그대로 오보가 된다.
→ 역방향이 필요하면 **실행 중인 앱의 라우트 테이블**(`app.routes`)을 정답으로 써라. 정규식이 아니라.

【★★★2026-08-20 정정 — "순방향은 과소 보고라 안전"은 **거짓이었다**】
종전 이 독스트링은 위 문단에 "(순방향은 반대로 **과소** 보고라 안전)"이라고 적었다.
그 문장이 다음 세션들에게 "여기 뜬 건 전부 진짜 후보"라고 읽혔고, 실제로 그 수치로
**약 40건이 결함 후보로 보드에 공표**됐다. 실측 결과 순방향은 **양방향으로 틀렸다**:

  ① **과대 보고(위양성 고아)** — 프론트가 마지막 세그먼트를 **동적으로** 넣으면
     그 리터럴이 소스에 없어 고아로 잡힌다. 실증:
     `MarketInsightsWorkspaceClient.tsx:777` 이
     ``fetch(`${marketApiBase()}/market/report/${fmt}`)`` 로
     `/market/report/{pdf,docx,pptx}` 를 **실제로 부르는데** 셋 다 고아로 올라 있었다.
     → 이 형태는 **정규식으로 소비 여부를 확정할 수 없다**. 조용히 "소비"로 넘기면
       진짜 고아가 숨고, 고아로 세면 없는 결함을 만든다. 그래서 **제3의 분류**를 둔다.

  ② **과소 보고(위음성 = 놓친 고아)** — 소스를 통째로 이어 붙여 대조하므로
     **주석 안의 경로도 "소비"로 셌다**. 실증(주석 배제 후 새로 드러난 6건):
       · `/api/v1/avm/estimate` — "탁상감정으로 **교체**"라고 적힌 줄 주석에만 있었다
       · `/api/v1/finance/monte-carlo` — "거짓 heroHint 정정"이라는 **JSX 주석**에만 있었다
       · `/api/v1/zoning/special-parcels` · `/basis/{run_id}` · `/basis/{run_id}/approve`
       · `/api/v1/design-audit/run` — 실행줄엔 `/design-audit/run-upload/…` 뿐인데
         **경계 없는 부분문자열**이라 소비로 셌다
     이 저장소는 소스 검사가 주석에 뚫리는 결함으로 반복해 데었다(회귀망 규율 A-3).

【한계 — 이 수치를 "결함 수"로 읽지 마라】
소비처 0 ≠ 결함이다. 정당하게 백엔드 내부용인 라우트가 섞인다(운영·정리·알림 발송 등).
이 도구는 **후보를 좁힐 뿐**이고, 진짜 결함인지는 사람이 라우트별로 판단해야 한다.

【아직 못 고친 것 — 다음 사람이 속지 않게 적어 둔다】
  · **문자열 리터럴은 배제하지 않는다.** 이 도구의 신호가 **전부 문자열 리터럴 안에**
    살기 때문이다(`apiClient.get("/market/report")`). 배제하면 도구가 통째로 죽는다.
    따라서 "죽은 상수에 남은 경로"는 여전히 소비로 세어진다.
  · **마운트 접두사 미해결 라우트가 85건 있다**(2026-08-20 실측). `main.py` 가
    `include_router(<별칭>, prefix=...)` 처럼 **별칭**으로 부르면 이 도구의 정규식이 못 읽어
    라우트가 접두사 없는 **꼬리 경로**로 남는다(예: `comprehensive_analysis.py` 의
    `/comprehensive` 는 실제로 `/api/v2/analysis/comprehensive`). 그래서 대조는
    **오른쪽 경계만** 본다 — 왼쪽까지 고정하면 그 85건이 통째로 위양성이 된다(실측).

사용:  python3 scripts/orphan_routes.py            # 요약(3분류)
       python3 scripts/orphan_routes.py --list     # 전체 목록(3분류 구분 출력)
"""
from __future__ import annotations

import os
import re
import sys

API_DIR = os.path.join(os.path.dirname(__file__), "..", "apps", "api")
WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "apps", "web")

# 경로 세그먼트를 이루는 문자. 대조 결과 **바로 뒤**가 이 문자면 다른 경로의 앞토막을
# 집은 것이다(`/api/v1/avm` 이 `/api/v1/avm-vision/analyze` 에 걸리던 실측 위양성).
_SEG_CHAR = re.compile(r"[A-Za-z0-9_-]")

# 템플릿 표현식 `${...}` — 중괄호 1단계 중첩까지 허용(`${a[b] ?? `${c}`}` 같은 깊은 중첩은 포기).
_DYN_EXPR = r"\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"

# 동적 세그먼트가 **경로의 끝**임을 뜻하는 문자(템플릿 종료 · 쿼리 시작 · 문자열 종료).
_URL_END = ("`", "?", '"', "'")

# 후보 경로의 최소 길이. `/avm`(4자) 같은 짧은 실경로를 살리려고 3 으로 낮췄다.
# ★이 완화는 **오른쪽 경계 검사와 한 쌍**이다 — 경계 없이 낮추면 짧은 경로가
#   다른 경로의 앞토막에 무차별로 걸린다.
_MIN_PATH_LEN = 3


def _strip_js_comments(src: str) -> str:
    """JS/TS 주석을 **길이·줄 수를 보존한 채**(공백으로) 지운다.

    ★왜 필요한가: 주석에만 남은 경로가 "소비"로 세어져 **진짜 고아를 숨겼다**(위 ② 참조).

    ★왜 손수 스캐너인가: 프론트에는 이미 `apps/web/lib/source-invariant.ts` 의
      `__stripCommentsForScan`(TS 파서 기반)이 있지만 **파이썬에서는 못 쓴다**.
      그래서 같은 일을 하는 스캐너를 여기 둔다 — 다만 파서가 아니므로 **동등하지 않다**.
      그 파일이 기록한 함정 두 가지는 그대로 방어한다:
        · 문자열 안의 `//`(URL) 를 주석으로 오인하지 않는다 → 문자열 상태를 추적한다
        · 줄 주석 안의 `/*` 를 블록 시작으로 오인하지 않는다 → 줄 주석을 먼저 끊는다

    ★남는 한계(정직하게 적는다 — 규율 C.11 "면역을 거짓 주장하지 마라"):
      · **정규식 리터럴을 토큰으로 인식하지 않는다.** `/…\\/\\/…/` 처럼 이스케이프된
        슬래시는 백슬래시 건너뛰기로 넘어가지만, 이스케이프 없는 `[//]` 류는 오인할 수 있다.
      · **JSX 텍스트**를 코드로 본다. `<p>a // b</p>` 의 `//` 를 주석으로 지운다.
      두 오인은 모두 "실제보다 **더 많이** 지우는" 방향이라 결과는 **고아 과대** 쪽으로 튄다.
      → 그래서 이 배제로 늘어난 항목은 **손수 표본 확인했다**(2026-08-20: 6건 전수 확인,
        전부 진짜 고아. 위양성 1건(`/api/v1/avm`)은 오른쪽 경계 검사로 잡아냈다).
    """
    out = list(src)
    i, n = 0, len(src)
    stack: list[str] = []  # 문자열/템플릿 중첩 상태
    while i < n:
        ch = src[i]
        cur = stack[-1] if stack else None
        if cur in ('"', "'", "`"):
            if ch == "\\":  # 문자열 이스케이프
                i += 2
                continue
            if ch == cur:
                stack.pop()
                i += 1
                continue
            if cur == "`" and ch == "$" and src[i + 1 : i + 2] == "{":
                stack.append("${")  # 템플릿 표현식 = 다시 코드 문맥
                i += 2
                continue
            i += 1
            continue
        # 여기부터는 코드(또는 템플릿 표현식) 문맥.
        if ch == "\\":  # 정규식 리터럴의 `\/` 를 슬래시로 오인하지 않게 건너뛴다.
            i += 2
            continue
        if ch in ('"', "'", "`"):
            stack.append(ch)
            i += 1
            continue
        if cur == "${" and ch == "}":
            stack.pop()
            i += 1
            continue
        if ch == "/" and src[i + 1 : i + 2] == "/":
            end = src.find("\n", i)
            end = n if end == -1 else end
            for k in range(i, end):
                out[k] = " "
            i = end
            continue
        if ch == "/" and src[i + 1 : i + 2] == "*":
            close = src.find("*/", i + 2)
            end = n if close == -1 else close + 2
            for k in range(i, end):
                if out[k] != "\n":  # 줄 수를 보존한다.
                    out[k] = " "
            i = end
            continue
        i += 1
    return "".join(out)


def _mount_prefixes() -> dict[str, str]:
    """`main.py` 의 `include_router(<mod>.router, prefix="...")` 에서 **마운트 접두사**를 읽는다.

    ★이것이 없으면 라우터 파일에 `APIRouter(prefix=...)` 가 없는 모듈이 통째로 누락된다.
      실측(2026-08-18): 이 누락으로 `/auction/*` 전체가 "백엔드에 없음"으로 잘못 잡혔다
      (라이브 확인 결과 405 = 존재함). **대조군 하나가 121건 오보를 막았다.**

    ★한계(2026-08-20 실측): `include_router(<별칭>, prefix=...)` 형태는 못 읽는다.
      그래서 접두사 미해결 라우트가 **85건** 남는다 — 위 독스트링의 "아직 못 고친 것" 참조.
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
    """프론트 소스를 이어 붙인다 — **주석은 지우고**(위 ② 결함)."""
    parts: list[str] = []
    for root, _, files in os.walk(WEB_DIR):
        if "node_modules" in root or "/.next" in root:
            continue
        for f in files:
            if f.endswith((".ts", ".tsx")) and not f.endswith((".test.ts", ".test.tsx", ".spec.ts")):
                try:
                    parts.append(_strip_js_comments(open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()))
                except OSError:
                    pass
    return "\n".join(parts)


def _candidates(full: str) -> set[str]:
    """접두사 있는/없는 형태를 둘 다 본다(apiClient 가 /api/v1 을 자동 부착)."""
    cands = {full, re.sub(r"^/api/v[12]", "", full)}
    for c in list(cands):
        cands.add(c.split("{")[0].rstrip("/"))
    return {c for c in cands if c and len(c) > _MIN_PATH_LEN}


def is_consumed(full: str, blob: str) -> bool:
    """리터럴 경로가 프론트 **실행 소스**에 있는가.

    ★오른쪽 경계를 본다 — 없으면 `/api/v1/avm` 이 `/api/v1/avm-vision/analyze` 에 걸려
      "소비"로 세어졌다(실측 위양성). 왼쪽은 **일부러 안 본다**: 마운트 접두사 미해결
      라우트 85건은 꼬리 경로라 왼쪽을 고정하면 통째로 위양성이 된다(실측).
    """
    for c in _candidates(full):
        for m in re.finditer(re.escape(c), blob):
            nxt = blob[m.end() : m.end() + 1] or "\n"
            if not _SEG_CHAR.match(nxt):
                return True
    return False


def is_dynamically_reachable(full: str, blob: str) -> bool:
    """마지막 세그먼트를 **동적으로** 넣는 호출이 프론트에 있는가(→ 판정 불가).

    ★"소비"가 아니다. `` `/blockchain/escrow/${id}` `` 는 **escrow ID** 를 넣는 호출이지
      리터럴 `/blockchain/escrow/fund` 를 부른다는 뜻이 아니다(실측 — 그 부모에는
      `{on_chain_escrow_id}` 라우트가 따로 있다). 반대로 `` `/market/report/${fmt}` `` 는
      `fmt: "pdf"|"pptx"|"docx"` 라 실제로 그 셋을 부른다.
      **정규식으로는 이 둘을 가를 수 없다** — 그래서 고아로도 소비로도 세지 않고 따로 낸다.

    동적 세그먼트가 **경로의 마지막**일 것을 요구한다. 안 그러면
    `` `/permits/${projectId}/latest` `` 가 `/permits/compliance-check` 를 설명해 버린다(실측).
    """
    for cand in {full, re.sub(r"^/api/v[12]", "", full)}:
        parent, _, last = cand.rpartition("/")
        if len(parent) <= _MIN_PATH_LEN or "{" in last:
            continue
        for m in re.finditer(re.escape(parent) + "/" + _DYN_EXPR, blob):
            if (blob[m.end() : m.end() + 1] or "`") in _URL_END:
                return True
    return False


def classify() -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """(확정 고아, 판정 불가) 를 돌려준다. 나머지는 확정 소비다."""
    routes = backend_routes()
    blob = frontend_blob()
    # ★대조군 — 조회기가 죽으면 전부 "소비처 0"으로 보인다. 그 경우 시끄럽게 실패한다.
    if "apiClient" not in blob:
        raise SystemExit("★프론트 스캔이 비었다(조회기 사망) — apiClient 가 한 번도 안 보인다")
    confirmed: list[tuple[str, str, str]] = []
    undecided: list[tuple[str, str, str]] = []
    for f, (m, p) in sorted(routes.items()):
        if is_consumed(f, blob):
            continue
        (undecided if is_dynamically_reachable(f, blob) else confirmed).append((f, m, p))
    return confirmed, undecided


def orphans() -> list[tuple[str, str, str]]:
    """**확정 고아만**. 판정 불가는 `undecided_routes()` 로 따로 본다.

    ★2026-08-20 이전에는 판정 불가 13건이 여기 섞여 있었다 — 그것이 보드에 올라간
      결함 후보 목록의 위양성이 됐다.
    """
    return classify()[0]


def undecided_routes() -> list[tuple[str, str, str]]:
    """**판정 불가(동적 세그먼트)**. 고아로도 소비로도 세지 않고 눈에 보이게 남긴다."""
    return classify()[1]


if __name__ == "__main__":
    confirmed, undecided = classify()
    total = len(backend_routes())
    print(
        f"백엔드 라우트 {total} · 확정 고아 {len(confirmed)} · 판정 불가(동적 세그먼트) {len(undecided)}"
        f" · 확정 소비 {total - len(confirmed) - len(undecided)}"
    )
    print("※ 판정 불가 = 프론트가 마지막 세그먼트를 동적으로 넣는 자리. 정규식으로는 확정 불가 —")
    print("   고아로도 소비로도 세지 않는다. 라우트별로 사람이 호출부를 열어 판단하라.")
    if "--list" in sys.argv:
        print("\n[확정 고아]")
        for f, m, p in confirmed:
            print(f"  {m.upper():6s} {f:52s} {p}")
        print("\n[판정 불가 — 동적 세그먼트]")
        for f, m, p in undecided:
            print(f"  {m.upper():6s} {f:52s} {p}")
