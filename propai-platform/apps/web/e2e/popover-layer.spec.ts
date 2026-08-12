/**
 * 주소 후보 팝오버의 **층위 계약**을 실제 브라우저에서 판정한다.
 *
 * ★왜 e2e 여야 하나 — 단위 가드(`lib/stacking-context.ts`)는 **클래스 토큰만** 본다.
 *   이 저장소에서 실제로 층위를 무력화하는 것들 중 상당수는 그 층에 없다:
 *     · 수작업 CSS — `.cc-panel { overflow:hidden }`(32파일) · `.glass { backdrop-filter }` ·
 *       `.leaflet-container { isolation:isolate }`
 *     · framer-motion 이 넣는 **인라인 transform**
 *   jsdom 은 CSS 를 로드하지 않아 `getComputedStyle` 로도 구제되지 않는다.
 *   → 이 층은 **실제 렌더된 computed style 과 페인트 순서**로만 잡힌다(규율 D-18).
 *
 * ★판정 방법 두 가지를 나눠 쓴다:
 *   1) **가려짐** — 경쟁자가 같은 화면에 있을 때만 의미가 있다. `elementFromPoint` 로
 *      페인트 순서를 본다. 좌표 교차(rect)로는 판정하지 않는다.
 *   2) **갇힘** — 경쟁자가 없어도 계약은 깨질 수 있다. 조상의 computed style 로
 *      스태킹 컨텍스트 생성 여부를 직접 본다(z 값만 읽으면 갇힌 것을 못 본다 —
 *      갇혀도 `getComputedStyle(el).zIndex` 는 그대로 650 이다).
 *
 * ★공허한 통과 방지: 각 검사 **앞에** 전제를 단언한다(후보 목록이 실제로 열렸는가,
 *   경쟁자와 실제로 겹치는 영역이 있는가). 이 저장소는 "대상이 0이라 위반도 0"인
 *   초록을 여러 번 만들었다.
 */
import { expect, test, type Page } from "@playwright/test";

import { SATONG_CONTENT_Z } from "../lib/satong-map-z";

const CANDIDATES = Array.from({ length: 8 }, (_, i) => ({
  pnu: `11680101000${i}`,
  address: `서울특별시 강남구 역삼동 ${736 + i}`,
  jibun: `서울특별시 강남구 역삼동 ${736 + i}`,
  roadAddr: `서울특별시 강남구 테헤란로 ${i + 1}`,
  kind: "지번",
  lat: 37.5 + i * 0.001,
  lon: 127.03 + i * 0.001,
}));

/** 클라이언트 인증은 localStorage 토큰이다(기존 harness 와 같은 방식). */
async function seedSession(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("propai_access_token", "playwright-access-token");
    localStorage.setItem("propai_refresh_token", "playwright-refresh-token");
  });
  // ★★API 를 **전부** 고정한다 — 후보 조회만 막으면 이 스펙은 **환경에 의존**한다.
  //
  //   실제로 그랬다: 종전엔 `/zoning/search` 만 가로챘고, 백엔드가 **없는** 로컬에서는
  //   나머지 호출이 네트워크 오류로 끝나 아무 일도 없었다. 그런데 CI 에는 백엔드가 **있어서**
  //   시드한 가짜 토큰이 **401 로 거부**되고, `lib/api-client.ts:426` 의 `handleSessionExpired()`
  //   가 토큰을 지우고 **로그인으로 리다이렉트**한다 → 입력칸은 잠깐 보였다가 사라지고
  //   후보 목록은 영영 안 뜬다. 그래서 **로컬 초록 / CI 빨강**이었다.
  //   (401 만 돌려주는 더미 서버를 :8000 에 세워 로컬에서 CI 를 그대로 재현해 확인했다.)
  //
  //   층위 계약은 **인증과 무관**하다 — 인증 왕복에 의존하지 않게 만든다.
  //   미지정 엔드포인트는 200 `{}` 로 답해 401 경로 자체가 생기지 않게 한다.
  await page.route("**/api/v1/**", async (route) => {
    if (route.request().url().includes("/zoning/search")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ candidates: CANDIDATES }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

/**
 * 후보 목록을 실제로 띄운다.
 *
 * ★Enter 는 첫 후보를 **선택**해 버리므로 입력만 한다(디바운스 350ms 뒤 조회).
 * ★★입력을 **재시도**한다 — 이 입력칸은 의도적으로 SSR 로 먼저 그려지므로(주소창 HTML 즉시 노출),
 *   `toBeVisible` 이 통과해도 아직 하이드레이션 전일 수 있다. 그 상태에서 한 번만 타이핑하면
 *   React onChange 가 붙기 전이라 **조회가 아예 발화하지 않는다**(실제로 이 함정에 걸렸다).
 */
async function openCandidates(page: Page, inputSelector: string, listSelector: string) {
  const input = page.locator(inputSelector).first();
  await expect(input, "주소 검색 입력칸이 없다 — 이 화면의 렌더 경로가 바뀌었다").toBeVisible({
    timeout: 30_000,
  });
  const list = page.locator(listSelector).first();
  await expect(async () => {
    await input.fill("");
    await input.pressSequentially("역삼동", { delay: 30 });
    await expect(list).toBeVisible({ timeout: 3_000 });
  }, "후보 목록이 열리지 않았다 — 아래 검사가 공허해진다").toPass({ timeout: 60_000 });
  return list;
}

test.describe("주소 후보 팝오버 — 층위 계약(실제 브라우저)", () => {
  test("★갇히지 않는다 — 조상이 스태킹 컨텍스트를 만들지 않는다 (/ko/projects/new)", async ({
    page,
  }) => {
    await seedSession(page);
    await page.goto("/ko/projects/new");
    const list = await openCandidates(
      page,
      'input[placeholder^="지번·도로명 검색"]',
      'ul[class*="top-full"]',
    );

    // 조상의 **computed style** 로 판정한다 — 클래스 토큰이 아니라.
    //   이렇게 해야 `.cc-panel` 같은 수작업 CSS 와 framer-motion 인라인 transform 까지 보인다.
    const result = await list.evaluate((ul) => {
      const traps: Array<{ cls: string; why: string }> = [];
      let n = ul.parentElement;
      let depth = 0;
      while (n && n !== document.body) {
        const cs = getComputedStyle(n);
        const reasons: string[] = [];
        if (cs.position !== "static" && cs.zIndex !== "auto") reasons.push(`${cs.position}+z:${cs.zIndex}`);
        if (cs.position === "fixed" || cs.position === "sticky") reasons.push(cs.position);
        if (cs.isolation === "isolate") reasons.push("isolation");
        if (cs.transform !== "none") reasons.push("transform");
        if (cs.filter !== "none") reasons.push("filter");
        if (cs.backdropFilter && cs.backdropFilter !== "none") reasons.push("backdrop-filter");
        if (Number.parseFloat(cs.opacity) < 1) reasons.push(`opacity:${cs.opacity}`);
        if (cs.mixBlendMode !== "normal") reasons.push("mix-blend");
        if ((cs.contain || "").includes("paint")) reasons.push("contain:paint");
        if (reasons.length) traps.push({ cls: String(n.className).slice(0, 80), why: reasons.join(",") });
        n = n.parentElement;
        depth += 1;
      }
      return { depth, traps, z: getComputedStyle(ul).zIndex };
    });

    // 공허 진리 방지 — 조상을 실제로 훑었는가.
    expect(result.depth, "조상이 0개다 — 렌더 구조가 바뀌었다").toBeGreaterThan(1);
    expect(Number(result.z), "팝오버가 계약 상수를 쓰지 않는다").toBe(SATONG_CONTENT_Z.contentPopover);
    expect(
      result.traps,
      `조상이 층 상자를 만든다 — z-${SATONG_CONTENT_Z.contentPopover} 가 그 안에 갇힌다:\n` +
        result.traps.map((t) => `  · ${t.why} :: ${t.cls}`).join("\n"),
    ).toEqual([]);

    // ★위 트랩을 없애려고 본문 래퍼에서 `z-10` 을 걷어냈다. 그 **안전 근거 두 가지**를 잠근다.
    //   ※ `elementFromPoint` 로는 못 잡는다 — 장식은 `pointer-events:none` 이라 히트테스트에서
    //     아예 빠진다. 그 오라클로 쓰면 **원리적으로 실패할 수 없는 공허한 단언**이 된다
    //     (실제로 그렇게 썼다가 되돌렸다). 그래서 근거를 **구조로** 검사한다.
    const basis = await page.evaluate(() => {
      const deco = document.querySelector(".cc-grid-bg") as HTMLElement | null;
      const body = document.querySelector(".cc-panel__body") as HTMLElement | null;
      if (!deco || !body) return { found: false as const };
      const cs = getComputedStyle(deco);
      return {
        found: true as const,
        // ① 장식이 본문보다 DOM 에서 **앞**에 온다 → 같은 z(auto)면 본문이 뒤에 그려져 위로 온다.
        decoBeforeBody: !!(deco.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING),
        // ② 장식이 스스로 위로 올라오지 않는다(양수 z 를 갖지 않는다).
        decoZ: cs.zIndex,
        // ③ 클릭을 가로채지 않는다.
        decoPointerEvents: cs.pointerEvents,
      };
    });
    expect(basis.found, "장식(.cc-grid-bg) 또는 본문(.cc-panel__body)을 찾지 못했다 — 근거 검사가 공허해진다").toBe(true);
    expect(basis.decoBeforeBody, "장식이 본문보다 뒤로 갔다 — z 없이 본문이 위에 온다는 전제가 깨졌다").toBe(true);
    expect(["auto", "0"], `장식이 z(${basis.decoZ})를 가졌다 — 본문 위로 올라온다`).toContain(basis.decoZ);
    expect(basis.decoPointerEvents, "장식이 클릭을 가로챈다").toBe("none");
  });

  test("★가려지지 않는다 — sticky 본문 헤더(600)와 겹쳐도 팝오버가 이긴다 (/ko/precheck)", async ({
    page,
  }) => {
    // ★뷰포트를 고정한다 — 겹침이 **실제로 일어나는 조건**이어야 판정이 성립한다.
    //   기본 720px 높이에서는 스크롤을 다 내려도 목록이 헤더에 닿지 않아 판정 불가였다(실측).
    //   480px 에서 두 박스가 19px 겹친다.
    await page.setViewportSize({ width: 1280, height: 480 });
    await seedSession(page);
    // ★경쟁자가 실재하는 화면을 골라야 한다. `z-[600]`(stickyContextHeader)은 저장소 전체에서
    //   **`SatongMapShell` 안에만** 있고(실측), 그 셸이 자기 sticky ContextHeader 와 자기
    //   주소 드롭다운(z-[650])을 함께 그린다 — 즉 둘이 겹칠 수 있는 유일한 화면이 여기다.
    //   ★`?legacy=1`(PreCheckWorkspace)에는 z-600 이 없다. 거기서 재면 **경쟁자 없는 공허한 통과**다.
    await page.goto("/ko/precheck");
    await openCandidates(
      page,
      'input[placeholder^="예: 의정부동 224"]',
      'ul[role="listbox"][aria-label="주소 후보"]',
    );

    const header = page.locator('[class*="z-[600]"]').first();
    await expect(header, "sticky ContextHeader(600)가 이 화면에 없다 — 경쟁자 없는 판정은 공허하다").toBeAttached();

    // 헤더와 목록이 **실제로 겹치도록** 스크롤한다 — 겹치지 않은 상태에서 재면 공허한 통과다.
    //   sticky 헤더는 뷰포트 상단에 머무르므로, 목록이 헤더 아래로 파고들 만큼 내린다.
    await page.evaluate(() => {
      const ul = document.querySelector('ul[role="listbox"][aria-label="주소 후보"]') as HTMLElement | null;
      const hdr = document.querySelector('[class*="z-[600]"]') as HTMLElement | null;
      if (!ul || !hdr) return;
      const delta = ul.getBoundingClientRect().top - hdr.getBoundingClientRect().bottom + 24;
      if (delta > 0) window.scrollBy(0, delta);
    });
    await page.waitForTimeout(300);

    const verdict = await page.evaluate(() => {
      const ul = document.querySelector('ul[role="listbox"][aria-label="주소 후보"]') as HTMLElement | null;
      const hdr = document.querySelector('[class*="z-[600]"]') as HTMLElement | null;
      if (!ul || !hdr) return { overlapped: false as const };
      const a = ul.getBoundingClientRect();
      const b = hdr.getBoundingClientRect();
      const x1 = Math.max(a.left, b.left);
      const x2 = Math.min(a.right, b.right);
      const y1 = Math.max(a.top, b.top);
      const y2 = Math.min(a.bottom, b.bottom);
      if (x2 - x1 < 4 || y2 - y1 < 4) return { overlapped: false as const, a, b };
      // 겹치는 박스 안 3점에서 **페인트 순서**로 판정한다(좌표 교차가 아니라).
      const pts: Array<[number, number]> = [
        [x1 + (x2 - x1) * 0.25, y1 + (y2 - y1) * 0.5],
        [x1 + (x2 - x1) * 0.5, y1 + (y2 - y1) * 0.5],
        [x1 + (x2 - x1) * 0.75, y1 + (y2 - y1) * 0.5],
      ];
      const hits = pts.map(([x, y]) => {
        const el = document.elementFromPoint(Math.round(x), Math.round(y));
        return { popoverWins: !!(el && ul.contains(el)), el: el ? `${el.tagName}.${String(el.className).slice(0, 40)}` : null };
      });
      return { overlapped: true as const, hits };
    });

    // ★전제: 실제로 겹쳐야 판정이 의미를 갖는다. **skip 이 아니라 실패**로 둔다 —
    //   위 뷰포트에서 겹침이 재현되는 것을 확인했으므로, 안 겹치면 그건 레이아웃 변화이지
    //   "판정 불가"가 아니다. skip 으로 두면 경쟁이 사라진 줄도 모르고 초록이 유지된다
    //   (이 저장소는 "겹치지 않은 상태에서 재서 공허하게 통과"한 이력이 있다).
    expect(
      verdict.overlapped,
      "헤더와 팝오버가 겹치지 않는다 — 판정이 공허해졌다. 레이아웃이 바뀌었으면 이 스펙을 갱신할 것",
    ).toBe(true);

    for (const hit of verdict.hits ?? []) {
      expect(hit.popoverWins, `겹치는 지점에서 팝오버가 졌다 — 실제로 그린 것: ${hit.el}`).toBe(true);
    }
  });
});
