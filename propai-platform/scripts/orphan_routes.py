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

  ②-미러 **백엔드 반쪽도 같은 결함이었다**(2026-08-20 R2, 적대리뷰 H-2). 프론트 주석은
     배제하면서 **백엔드 추출은 파이썬 주석·독스트링을 그대로 셌다**. 그래서 실재하지 않는
     라우트가 "확정 고아"로 기준선에 실렸다 — `/admin-only` 는 `app/core/rbac.py:114`
     **독스트링의 사용 예**다. `tokenize` 마스킹으로 봉합(575건 중 정확히 3건 배제,
     백엔드 총수 549 → 546 · 확정 고아 124 → 123).
     ★교훈: 처방을 적용한 범위 = 결함이 사는 범위인지 확인하라(규율 20).

【한계 — 이 수치를 "결함 수"로 읽지 마라】
소비처 0 ≠ 결함이다. 정당하게 백엔드 내부용인 라우트가 섞인다(운영·정리·알림 발송 등).
이 도구는 **후보를 좁힐 뿐**이고, 진짜 결함인지는 사람이 라우트별로 판단해야 한다.

【아직 못 고친 것 — 다음 사람이 속지 않게 적어 둔다】
  · **문자열 리터럴은 배제하지 않는다.** 이 도구의 신호가 **전부 문자열 리터럴 안에**
    살기 때문이다(`apiClient.get("/market/report")`). 배제하면 도구가 통째로 죽는다.
    따라서 "죽은 상수에 남은 경로"는 여전히 소비로 세어진다.
  · **`tokenize` 오프셋이 폼피드(`\x0c`)·`\x0b`·유니코드 줄바꿈에서 어긋난다.**
    `splitlines(keepends=True)` 는 그 문자에서 줄을 자르는데 `tokenize` 는 안 자르기 때문에
    줄 오프셋 표가 밀린다(실증: 주석이 15번지인데 (7,10)으로 보고). 그러면 마스킹이 엉뚱한
    구간에 걸린다. ★저장소 노출은 **0건**이다(백엔드 `.py` 전수 중 해당 문자 포함 0개).
    방향(유령이 새는 쪽인지 진짜가 지워지는 쪽인지)은 **확정하지 않았다** — 노출이 0이라 안 팠다.
  · **import 경로·Next 페이지 경로를 "API 소비"로 센다.** 짧은 경로일수록 심하다 —
    실측(2026-08-20, 전수 분류) `/cost` 는 경계를 통과한 매칭 **52건 중 25건이
    `@/components/cost/…` import·`/{locale}/analytics/cost` 링크**이고 27건만 진짜
    API 호출이다. 이 라우트는 실제로 소비되므로 오늘 결론은 안 바뀌지만, **같은 이름의
    컴포넌트 폴더만 있고 호출은 없는 라우트**는 import 경로만으로 "소비"가 되어 숨는다.
    ※적대리뷰는 이 비율을 "52건 중 50건"으로 적었으나 내 전수 분류로는 재현되지 않았다
      (25건). 구조적 위음성이 존재한다는 결론 자체는 같다.
  · **마운트 접두사 미해결 라우트가 85건 있다**(2026-08-20 실측). `main.py` 가
    `include_router(<별칭>, prefix=...)` 처럼 **별칭**으로 부르면 이 도구의 정규식이 못 읽어
    라우트가 접두사 없는 **꼬리 경로**로 남는다(예: `comprehensive_analysis.py` 의
    `/comprehensive` 는 실제로 `/api/v2/analysis/comprehensive`). 그래서 대조는
    **오른쪽 경계만** 본다 — 왼쪽까지 고정하면 **137 → 143(+6)** 이 되는데 그 6건이
    전부 위양성이다(실측 2026-08-20: `/comprehensive` · `/interpretation` ×2 ·
    `/llm-providers` · `/site-layout` 은 전부 `comprehensive_analysis.py` 의 접두사
    미해결 꼬리 경로다). ★종전에 "144(+7)"로 적었던 것은 중간 구성(최소길이 5) 수치였다 —
    현재 구성 기준 실측은 **143(+6)** 이다.

사용:  python3 scripts/orphan_routes.py            # 요약(3분류)
       python3 scripts/orphan_routes.py --list     # 전체 목록(3분류 구분 출력)
"""
from __future__ import annotations

import functools
import io
import os
import re
import sys
import tokenize

API_DIR = os.path.join(os.path.dirname(__file__), "..", "apps", "api")
WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "apps", "web")

# 경로 세그먼트를 이루는 문자. 대조 결과 **바로 뒤**가 이 문자면 다른 경로의 앞토막을
# 집은 것이다(`/api/v1/avm` 이 `/api/v1/avm-vision/analyze` 에 걸리던 실측 위양성).
_SEG_CHAR = re.compile(r"[A-Za-z0-9_-]")

# 템플릿 표현식 `${...}` — 중괄호 1단계 중첩까지 허용(`${a[b] ?? `${c}`}` 같은 깊은 중첩은 포기).
_DYN_EXPR = r"\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"

# 동적 세그먼트가 **경로의 끝**임을 뜻하는 문자(템플릿 종료 · 쿼리 시작 · 문자열 종료).
_URL_END = ("`", "?", '"', "'")

# ── 호출부 HTTP 메서드 판독 ────────────────────────────────────────────────
# 왜 필요한가(쉬운 설명): `` `/blockchain/escrow/${id}` `` 를 **GET** 으로 부르는 화면은
# **POST** 라우트인 `/blockchain/escrow/fund` 를 부를 수 없다. 메서드를 안 보면 이 둘이
# 구분되지 않아 진짜 고아 9건이 "판정 불가"에 숨었다(2026-08-21 실측).
# ★게이트는 **한 방향으로만** 쓴다 — 메서드를 **확실히 읽었고 다를 때만** 그 호출부가
#   이 라우트를 설명하지 않는다고 본다. 못 읽으면 종전대로 판정 불가로 남긴다
#   (모르는 것을 안다고 하지 않는다).
_CALL_METHOD_BEFORE = re.compile(
    r"\.(get|post|put|patch|delete)\s*(?:<[^;{}]*?>)?\s*\(\s*$", re.IGNORECASE
)
# fetch 는 URL 이 **먼저** 오고 메서드가 뒤 옵션에 온다 → 앞뒤를 따로 본다.
_FETCH_BEFORE = re.compile(r"\bfetch\s*\(")
_FETCH_METHOD_AFTER = re.compile(r"""method\s*:\s*["'](\w+)["']""")
# 호출부 판독 창(문자). 좁으면 못 읽고(→ 판정 불가 유지) 넓으면 남의 호출을 줍는다.
_METHOD_LOOKBEHIND = 200
_METHOD_LOOKAHEAD = 300

# 후보 경로의 최소 길이. `/avm`(4자) 같은 짧은 실경로를 살리려고 3 으로 낮췄다.
# ★이 완화는 **오른쪽 경계 검사와 한 쌍**이다 — 경계 없이 낮추면 짧은 경로가
#   다른 경로의 앞토막에 무차별로 걸린다.
_MIN_PATH_LEN = 3


def _forward(i: int, end: int) -> int:
    """커서를 **반드시 앞으로** 옮긴다.

    ★올바른 코드에서는 항상 `end > i` 라 이 함수는 `end` 를 그대로 돌려준다(=무동작).
      그런데도 두는 이유: 이 스캐너는 손수 만든 상태 기계라, `end` 계산이 한 줄만 어긋나도
      커서가 **뒤로** 가 무한루프가 된다. 실측(2026-08-20 변이 감사) — 폴백 한 줄을 지웠더니
      `end = -1` 이 되어 스캔이 영원히 돌았고, 저장소 변이 도구는 `subprocess.run` 에
      타임아웃이 없어 **감사 전체가 멎었다**. 행(hang)은 "아직 도는 중"과 구별되지 않는다.
      → 여기서 전진을 강제해 그런 버그가 **조용한 행이 아니라 시끄러운 오답**으로 드러나게 한다.
    """
    return end if end > i else i + 1


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
      · **JSX 텍스트**를 코드로 본다. `<p>a // b</p>` 의 `//` 를 주석으로 지운다
        (= **더 많이** 지우는 방향 → 고아 과대).
      · ★**정규식 리터럴·따옴표 짝이 어긋나면 반대로 `덜` 지운다.** 정규식 안의 `'`/`"`
        (예: `/[\'"]/`)나 JSX 아포스트로피(`It's`)를 문자열 시작으로 오인하면, 스캐너가
        문자열 상태에 갇혀 **그 뒤 구간의 주석을 통째로 못 지운다** = 결함② 재발 방향이다.
        **실측(2026-08-20, 663 프론트 파일)**: 배제 실패 **10개 파일** ·
        놓친 줄주석 **127줄** · 따옴표 desync 이후 파일 끝까지 **4,600줄 / 177,002줄 = 2.60%**
        (SatongMultiMap · MarketInsightsWorkspaceClient · vworld-xml-exception ·
         MarkdownLite · source-invariant · ProjectPresaleMap 등).
        → **이 배제는 완전하지 않다.** 단정하지 마라.
      ★그러나 **오늘 분류 영향은 0이다**(실측): 놓친 줄주석을 오라클로 강제 제거해
        문자 5,444자를 더 지워도 **124/13 불변 · 신규 고아 0 · 사라진 고아 0**.
        다음 사람이 정확히 판단하도록 둘 다 적는다 — "완전하다"도 "그래서 수치가 틀렸다"도
        모두 거짓이다.
      → 이 배제로 늘어난 항목은 **손수 표본 확인했다**(2026-08-20: 6건 전수 확인,
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
        # ★무잠금(2026-08-20 변이 감사): 아래 두 줄의 백슬래시 건너뛰기는 **테스트가 잠그지
        #   못한다**. 코드 문맥 쪽은 픽스처의 정규식이 `\/` 를 담고는 있으나 그 줄을 지워도
        #   결과가 같아 원리적으로 위반 불가였고(공허), 문자열 쪽은 위 독스트링이 말한
        #   desync 를 **직접 유발하는 층**이라 정직한 픽스처를 만들지 못했다.
        #   고쳤다고 적지 않는다 — 미검증이다.
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
            i = _forward(i, end)
            continue
        if ch == "/" and src[i + 1 : i + 2] == "*":
            close = src.find("*/", i + 2)
            end = n if close == -1 else close + 2
            for k in range(i, end):
                if out[k] != "\n":  # 줄 수를 보존한다.
                    out[k] = " "
            i = _forward(i, end)
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


def _py_comment_string_spans(src: str) -> list[tuple[int, int]] | None:
    """파이썬 소스의 **주석·문자열 리터럴** 절대 오프셋 범위. 실패하면 None.

    ★왜 필요한가(2026-08-20 — 프론트 반쪽만 고쳤던 것을 봉합): 이 도구는 프론트 주석을
      배제하면서 **백엔드 추출은 주석·독스트링을 그대로 셌다**. 그래서 실재하지 않는
      라우트가 "확정 고아"로 기준선에 실렸다:
        · `app/core/rbac.py:114`            `/admin-only`   ← 함수 **독스트링의 사용 예**
        · `app/services/auth/project_ownership.py:12`  `/from-project`
        · `auth/rbac.py:338`                `/projects`
      전수 실측: `@router.<메서드>(...)` 매칭 **575건 중 정확히 3건**이 주석/문자열 내부.
      `/admin-only` 는 기준선에 실려 **없는 결함이 후보로 공표**됐다.

    ★`@` 의 위치만 본다 — 라우트 경로 자체는 별개의 STRING 토큰이라 마스킹해도 안전하다.
      (문자열을 통째로 배제하면 경로 추출이 죽는다. 그래서 "매칭 시작점 포함 여부"만 본다.)
    """
    lines = src.splitlines(keepends=True)
    off = [0]
    for ln in lines:
        off.append(off[-1] + len(ln))
    out: list[tuple[int, int]] = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type in (tokenize.COMMENT, tokenize.STRING):
                out.append((off[t.start[0] - 1] + t.start[1], off[t.end[0] - 1] + t.end[1]))
    except (tokenize.TokenError, IndentationError, SyntaxError, IndexError):
        # ★조용히 넘기지 않는다 — 이 파일만 마스킹 없이(=종전 동작으로) 처리되므로
        #   그 사실을 호출자가 알아야 한다. 실측 2026-08-20 기준 실패 파일은 **0건**이다.
        return None
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
            spans = _py_comment_string_spans(src)
            # ★무잠금·도달 불가(2026-08-20 변이 감사에서 이 3줄이 생존): 저장소의 백엔드 .py
            #   **전부가 토큰화에 성공**하므로(실패 0건) 이 폴백은 실행되지 않는다. 그래서
            #   변이가 안 죽는다 — 진짜 구멍이 아니라 도달 불가다. 픽스처로 만들려면 저장소에
            #   깨진 .py 를 넣어야 해서 하지 않았다. 대신 `_py_comment_string_spans` 가
            #   None 을 돌려주는 층은 `test_토큰화_실패시_None_을_돌려준다` 로 직접 잠갔다.
            if spans is None:
                print(f"★{os.path.relpath(p, API_DIR)} 토큰화 실패 — 주석/독스트링 배제 없이 셌다",
                      file=sys.stderr)
                spans = []
            for m in re.finditer(r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']', src):
                # ★주석·독스트링 안의 "사용 예"는 라우트가 아니다(유령 라우트 차단).
                if any(a <= m.start() < b for a, b in spans):
                    continue
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


def call_method_at(blob: str, start: int, end: int) -> str | None:
    """그 동적 호출부가 쓰는 HTTP 메서드. **읽어내지 못하면 None**(모른다고 말한다).

    두 형태를 읽는다.
      · `apiClient.get<T>(` / `.post(` / `.put(` / `.delete(` — URL **앞**에 메서드가 있다.
      · `fetch(` — URL **뒤** 옵션의 `method: "POST"` 에 있다.
    ★fetch 에 method 가 없으면 브라우저 기본은 GET 이지만 **None 을 돌려준다** —
      옵션 객체를 다른 곳에서 조립할 수 있어, 추정으로 진짜 고아를 만들지 않는다.
    ★`endpoint={`/underwriting/${id}`}` 처럼 **프롭으로 넘기는** 호출은 메서드가 그 자리에
      없다 → None. 이 경우 라우트는 판정 불가로 **남는다**(정직한 미결).
    """
    pre = blob[max(0, start - _METHOD_LOOKBEHIND) : start]
    # 템플릿 시작 백틱·따옴표·공백을 걷어내야 `.get(` 이 끝에 닿는다.
    trimmed = pre.rstrip("`'\" \t\r\n")
    m = _CALL_METHOD_BEFORE.search(trimmed)
    if m:
        return m.group(1).lower()
    if _FETCH_BEFORE.search(pre):
        after = _FETCH_METHOD_AFTER.search(blob[end : end + _METHOD_LOOKAHEAD])
        if after:
            return after.group(1).lower()
    return None


def is_dynamically_reachable(full: str, blob: str, method: str | None = None) -> bool:
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
            if (blob[m.end() : m.end() + 1] or "`") not in _URL_END:
                continue
            # ★메서드 게이트 — 확실히 읽었고 다를 때만 "이 호출부는 이 라우트가 아니다".
            called = call_method_at(blob, m.start(), m.end())
            if method and called and called != method.lower():
                continue
            return True
    return False


@functools.lru_cache(maxsize=1)
def classify() -> tuple[tuple[tuple[str, str, str], ...], tuple[tuple[str, str, str], ...]]:
    """(확정 고아, 판정 불가) 를 돌려준다. 나머지는 확정 소비다.

    ★캐시하는 이유: 한 번 호출에 저장소를 **전수 스캔**한다(백엔드 .py + 프론트 .ts/.tsx).
      테스트 1회가 `orphans()`·`undecided_routes()`·파라미터화로 7회 호출해 ≈38초였다.
      한 프로세스 안에서 소스는 안 바뀌므로 안전하다 — 소스를 바꿔가며 재분류하고 싶으면
      `classify.cache_clear()` 를 부르라(변이 검증은 프로세스를 새로 띄우므로 무관하다).

    ★★**캐시가 살아 있는 동안 아래 `apiClient` 대조군은 발화하지 않는다.**
      `API_DIR`/`WEB_DIR` 를 바꿔 가며 두 트리를 비교하는 감사(리뷰 레인이 실제로 한다)에서
      **낡은 수치를 원본으로 보고**하게 된다 — 이 도구가 고치려는 "낡은 워크트리를 읽어 133"과
      **같은 형태**다. 경로·소스를 바꿨으면 **반드시 `classify.cache_clear()`** 를 부르라.
      (실증 2026-08-20: `WEB_DIR="/tmp/__nonexistent__"` 로 바꿔도 예외 없이 123 을 돌려주고,
       `cache_clear()` 후에야 SystemExit 이 난다.)

    ★반환은 **튜플**이다 — 종전에는 캐시가 쥔 리스트를 그대로 돌려줘서 호출자의
      `.append()`/`.sort()` 한 줄이 **전역 캐시를 조용히 오염**시켰다(실증: 123 → 124).
    """
    routes = backend_routes()
    blob = frontend_blob()
    # ★대조군 — 조회기가 죽으면 전부 "소비처 0"으로 보인다. 그 경우 시끄럽게 실패한다.
    #   (이 단언은 **조회기 사망 탐지용**이지 하한 목표가 아니다.)
    if "apiClient" not in blob:
        raise SystemExit("★프론트 스캔이 비었다(조회기 사망) — apiClient 가 한 번도 안 보인다")
    confirmed: list[tuple[str, str, str]] = []
    undecided: list[tuple[str, str, str]] = []
    for f, (m, p) in sorted(routes.items()):
        if is_consumed(f, blob):
            continue
        (undecided if is_dynamically_reachable(f, blob, m) else confirmed).append((f, m, p))
    return tuple(confirmed), tuple(undecided)


def orphans() -> list[tuple[str, str, str]]:
    """**확정 고아만**. 판정 불가는 `undecided_routes()` 로 따로 본다.

    ★2026-08-20 이전에는 판정 불가 13건이 여기 섞여 있었다 — 그것이 보드에 올라간
      결함 후보 목록의 위양성이 됐다.
    """
    return list(classify()[0])  # ★사본 — 호출자가 캐시를 훼손하지 못하게


def undecided_routes() -> list[tuple[str, str, str]]:
    """**판정 불가(동적 세그먼트)**. 고아로도 소비로도 세지 않고 눈에 보이게 남긴다."""
    return list(classify()[1])  # ★사본 — 호출자가 캐시를 훼손하지 못하게


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
