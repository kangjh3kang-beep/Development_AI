import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { BUSINESS_INFO } from "@/components/layout/SiteFooter";

/**
 * ★전자상거래법 표기 락 — 네이버 로그인 검수 반려(2026.05.13) 사유였다.
 *
 *   요구: *「네이버 로그인을 적용할 **모든 서비스 환경(PC/모바일 화면 하단 푸터)** 에
 *   [대표자명, 사업자등록번호, 통신판매업 신고번호]가 확인되도록」*
 *
 *   반려 당시 실측: /ko 0·0·0 · /ko/login 0·0·0 · /ko/legal/terms 1·1·**0**
 *   ⇒ 값이 **대시보드에만** 있었고 통신판매업 신고번호는 **어디에도 없었다**.
 */

const WEB = path.resolve(__dirname, "..", "..", "..");
const LAYOUT = path.join(WEB, "app", "[locale]", "layout.tsx");

describe("전자상거래법 3종 표기", () => {
  it("★세 항목이 모두 비어 있지 않다 — 하나라도 비면 검수가 반려된다", () => {
    expect(BUSINESS_INFO.representative.trim()).not.toBe("");
    expect(BUSINESS_INFO.businessNumber.trim()).not.toBe("");
    expect(BUSINESS_INFO.mailOrderNumber.trim()).not.toBe("");
    // ★대조군: 형식까지 본다(빈 문자열 아닌 아무 값이나 통과하는 것을 막는다)
    expect(BUSINESS_INFO.businessNumber).toMatch(/^\d{3}-\d{2}-\d{5}$/);
    expect(BUSINESS_INFO.mailOrderNumber).toMatch(/^제\d{4}-.+-\d+호$/);
  });

  it("★전역 레이아웃이 푸터를 렌더한다 — 초기 화면·로그인 화면이 여기에 걸린다", () => {
    const src = fs.readFileSync(LAYOUT, "utf-8");
    // 재료
    expect(src).toMatch(/from "@\/components\/layout\/SiteFooter"/);
    // ★행위 — 실제로 렌더에 들어갔는가(임포트만으로는 배선이 아니다)
    expect(src).toMatch(/<SiteFooter\s+locale=/);
  });

  it("★값이 **한 곳에만** 있다 — 두 곳에 있으면 한쪽만 고쳐진다(§29)", () => {
    const hits: string[] = [];
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name);
        if (e.isDirectory()) {
          if (["node_modules", ".next", "__tests__", "e2e"].includes(e.name)) continue;
          walk(p);
        } else if (/\.tsx?$/.test(e.name)) {
          const t = fs.readFileSync(p, "utf-8");
          if (t.includes(BUSINESS_INFO.businessNumber)) hits.push(path.relative(WEB, p));
        }
      }
    };
    walk(WEB);
    // ★대조군: 하한을 걸어 「walk 가 아무것도 못 읽어서 0」인 경우를 배제한다
    expect(hits.length).toBeGreaterThan(0);
    // 허용: SiteFooter(단일 출처) + legal 2페이지(법적 고지문 본문)
    const allowed = new Set([
      "components/layout/SiteFooter.tsx",
      "app/[locale]/legal/terms/page.tsx",
      "app/[locale]/legal/privacy/page.tsx",
    ]);
    const stray = hits.filter((h) => !allowed.has(h));
    expect(stray).toEqual([]);
  });

  it("★legal 두 페이지에 3종이 모두 있다 — 전수로 확인", () => {
    for (const rel of [
      "app/[locale]/legal/terms/page.tsx",
      "app/[locale]/legal/privacy/page.tsx",
    ]) {
      const t = fs.readFileSync(path.join(WEB, rel), "utf-8");
      expect(t, `${rel}: 대표자`).toContain(BUSINESS_INFO.representative);
      expect(t, `${rel}: 사업자등록번호`).toContain(BUSINESS_INFO.businessNumber);
      expect(t, `${rel}: 통신판매업`).toContain(BUSINESS_INFO.mailOrderNumber);
    }
  });

  it("★대시보드가 자체 사업자 정보를 다시 들고 있지 않다(중복 부활 방지)", () => {
    const t = fs.readFileSync(
      path.join(WEB, "components", "layout", "DashboardChromeGate.tsx"),
      "utf-8",
    );
    expect(t).not.toContain(BUSINESS_INFO.businessNumber);
    // 대조군: 파일 자체는 살아 있어야 위 단언이 의미를 갖는다
    expect(t.length).toBeGreaterThan(1000);
  });
});
