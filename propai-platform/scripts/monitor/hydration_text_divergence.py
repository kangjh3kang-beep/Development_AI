"""**하이드레이션 표시 괴리 프로브** — SSR 텍스트와 하이드레이션 후 텍스트가 어디서 갈리는가.

이 저장소의 반복 결함 하나는 *"값은 나가는데 **그 값이 무엇인지**가 안 나간다"* 이고,
그 계열은 거의 항상 **서버·클라 표시 괴리**로 드러난다(`#812`·`#822` 가 같은 얼굴이었다).
React 하이드레이션 오류(#418, `args[]=text&args[]=` — 텍스트 노드 불일치·한쪽이 빈 문자열)
진단이 계기였지만, **그 건이 닫혀도 이 프로브는 남는다.**

## 방법

  ① `java_script_enabled=False` 컨텍스트로 같은 URL 을 연다 → **하이드레이션 없는 서버 마크업**
     (`curl` 로 받아 심는 것보다 정확하다 — 브라우저 파서를 그대로 쓴다)
  ② 같은 URL 을 정상 로드 → 하이드레이션 후
  ③ 두 텍스트 노드 **순서열을 정렬 diff**(`difflib`) → 치환·삽입·삭제

★**절대 인덱스 경로를 키로 쓰지 마라.** JS 끈 렌더는 `body` 자식 수가 달라 **전부 밀린다**
  (실측: 같은 요소가 `/body[2]/…` vs `/body[14]/…`). 그래서 순서 정렬을 쓴다.

## ★★결론에 쓰면 안 되는 것 — **치환 개수**

실측(2026-08-25):

    /ko/precheck      치환 520건  →  #418 **0**
    /ko/regulations   치환 410건  →  #418 **1**

**개수는 신호가 아니다.** 대부분의 괴리를 React 는 조용히 넘긴다(클라 전용 서브트리이거나
통째로 교체되는 경우). 판정은 **유무**와 **어느 자리인가**로만 하라.
★같은 이유로 *"괴리가 있으니 그것이 원인"* 도 성립하지 않는다 — 실제로 유력해 보이던
`대상 미선택 ↔ 분석 대상` 괴리가 **#418 이 안 나는 라우트에도 똑같이** 있었다.

## 측정 유효성 — 무효면 **출력하지 않는다**

경고만 찍고 표를 함께 내면 **사람은 표를 읽는다**(실제로 105건의 쓰레기를 출력했다).
그래서 무효 조건이면 결과 없이 `exit 3`:

  · 최종 URL 이 `/login` (토큰 만료·미인증)
  · 응답이 `{"detail": …}` 형태 — ★**토큰 만료는 401 이 아니라 이 모양으로 온다**
  · 한쪽 텍스트 노드가 0개(스캐너 사망) · 공통 텍스트가 0(정렬 실패)

★인증 프로브는 **토큰 수명이 측정보다 짧을 수 있다** — 한 세션에서 3회 만료됐다.

## 사용

    python3 propai-platform/scripts/monitor/hydration_text_divergence.py <URL> [state.json]

종료코드: 0 = 측정 성공 · 3 = **측정 무효**(결과를 믿지 마라)
"""
import sys, json
from playwright.sync_api import sync_playwright

EXTRACT = """() => {
  const out = [];
  const walk = (node, path) => {
    if (node.nodeType === 3) {
      const t = (node.textContent || '').trim();
      if (t) out.push([path, t.slice(0, 120)]);
      return;
    }
    if (node.nodeType !== 1) return;
    const tag = node.tagName.toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'noscript') return;
    let i = 0;
    for (const c of node.childNodes) walk(c, path + '/' + tag + '[' + (i++) + ']');
  };
  walk(document.body, '');
  return out;
}"""

def run(url, state=None):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=state, locale="ko-KR",
                            viewport={"width": 1400, "height": 900})
        # ① SSR: 자바스크립트를 끈 컨텍스트로 같은 URL 을 연다 → 하이드레이션 없음
        ssr_ctx = b.new_context(storage_state=state, locale="ko-KR",
                                java_script_enabled=False,
                                viewport={"width": 1400, "height": 900})
        sp = ssr_ctx.new_page()
        sp.goto(url, wait_until="domcontentloaded", timeout=60000)
        ssr = sp.evaluate(EXTRACT); ssr_url = sp.url
        # ② 하이드레이션 후
        cp = ctx.new_page()
        errs = []
        cp.on("pageerror", lambda e: errs.append(str(e)[:110]))
        cp.goto(url, wait_until="domcontentloaded", timeout=60000)
        cp.wait_for_timeout(6000)
        cli = cp.evaluate(EXTRACT); cli_url = cp.url
        b.close()
    return ssr, cli, ssr_url, cli_url, errs

def main():
    url = sys.argv[1]
    state = sys.argv[2] if len(sys.argv) > 2 else None
    ssr, cli, su, cu, errs = run(url, state)
    print("  URL        : %s" % url)
    print("  SSR 최종URL : %s%s" % (su, "   ★/login — 이 측정은 무효" if "/login" in su else ""))
    print("  CLI 최종URL : %s%s" % (cu, "   ★/login — 이 측정은 무효" if "/login" in cu else ""))
    print("  텍스트 노드 : SSR %d개 · 하이드레이션 후 %d개" % (len(ssr), len(cli)))
    print("  #418        : %d건" % sum(1 for e in errs if "418" in e))
    # ★무효한 측정은 **결과를 내지 않는다**. 종전엔 경고만 찍고 105건의 쓰레기를 출력했는데,
    #   그건 "로그인 페이지 vs 원래 페이지" 비교라 아무 의미가 없다.
    #   경고 아래에 그럴듯한 표가 있으면 사람은 표를 읽는다.
    # ★토큰 만료가 401 이 아니라 {"detail": …} 로 오는 경로가 있다(동료 세션 실측).
    #   그 경우 페이지는 200 이고 URL 도 안 바뀌므로 /login 검사만으로는 못 잡는다.
    for label, nodes in (("SSR", ssr), ("CLI", cli)):
        joined = " ".join(t for _, t in nodes)[:400]
        if joined.strip().startswith('{"detail"') or '"detail":' in joined[:120]:
            print("  ★측정 무효 — %s 응답이 {\"detail\": …} 다(토큰 만료 등). **결과를 출력하지 않는다.**" % label)
            return 3
    if "/login" in su or "/login" in cu:
        print("  ★측정 무효 — 로그인으로 리다이렉트됐다(토큰 만료 등). **결과를 출력하지 않는다.**")
        print("     state.json 을 새로 만들고 다시 실행하라. (이 세션에서 토큰이 3회 만료됐다)")
        return 3
    if not ssr or not cli:
        print("  ★대조군 실패 — 한쪽 텍스트 노드가 0개다. 스캐너가 죽었으므로 아래 결과를 믿지 마라.")
        return 3
    # ★절대 인덱스 경로는 키로 못 쓴다 — JS 끈 렌더는 body 자식 수가 달라 **전부 밀린다**
    #   (실측: SSR `/body[2]/...` vs CLI `/body[14]/...` — 같은 요소인데 키가 다르다).
    #   그래서 **텍스트 순서열을 정렬 diff** 한다. 밀림·삽입을 자연스럽게 흡수한다.
    import difflib
    sa = [t for _, t in ssr]
    sb = [t for _, t in cli]
    sm = difflib.SequenceMatcher(a=sa, b=sb, autojunk=False)
    replaced, inserted, deleted = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                A = sa[i1 + k] if i1 + k < i2 else None
                B = sb[j1 + k] if j1 + k < j2 else None
                replaced.append((A, B, ssr[i1 + k][0] if i1 + k < i2 else cli[j1 + k][0]))
        elif tag == "insert":
            inserted += [(cli[x][0], sb[x]) for x in range(j1, j2)]
        elif tag == "delete":
            deleted += [(ssr[x][0], sa[x]) for x in range(i1, i2)]
    same = sum(bl.size for bl in sm.get_matching_blocks())
    print("\n  정렬 결과: 동일 %d · **치환 %d** · 삽입 %d · 삭제 %d" % (same, len(replaced), len(inserted), len(deleted)))
    if same == 0:
        print("  ★공통 텍스트가 0 — 두 렌더가 완전히 다르다(정렬 실패). 아래를 믿지 마라.")
        return 3
    print("\n  ★**치환**(같은 자리에 다른 텍스트) — #418 의 직접 후보 %d건" % len(replaced))
    for A, B, path in replaced[:15]:
        print("    %s\n       SSR=%r\n       CLI=%r" % (path[-95:], A, B))
    print("\n  삽입(서버엔 없고 클라에만) %d건 — 앞 8개" % len(inserted))
    for path, t in inserted[:8]:
        print("    %-95s %r" % (path[-95:], t[:60]))
    print("\n  삭제(서버엔 있고 클라엔 없음) %d건 — 앞 8개" % len(deleted))
    for path, t in deleted[:8]:
        print("    %-95s %r" % (path[-95:], t[:60]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
