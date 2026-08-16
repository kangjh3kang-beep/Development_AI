/**
 * 상세정보팝업 **양보 계약** 락 — 사용자 신고("팝업이 다른 정보에 가려진다")의 처방을 잠근다.
 *
 * ## 왜 이 파일이 있나
 *
 * 팝업은 `.leaflet-container`(`isolation:isolate; z-index:0`) **안**에 있어 바깥 오버레이
 * (380~500)를 **z 로는 이길 수 없다**. 라이브 실측에서 `.leaflet-popup-pane` 의 계산된 z 는
 * **1** 이었다. 그래서 처방은 "팝업을 올린다"가 아니라 **"수동적 크롬이 물러난다"** 다.
 *
 * 그 처방은 **세 조각이 서로 맞아야만** 작동한다 — 하나라도 어긋나면 조용히 무효가 된다:
 *   ① SSOT 상수(`SATONG_POPUP_YIELD`)
 *   ② `globals.css` 의 감쇄 규칙(선택자·값)
 *   ③ 컴포넌트가 다는 속성
 * 이 파일은 ①↔② 일치와 ③의 실재를 잠근다.
 *
 * ★특히 **값 일치**가 중요하다: 상수와 CSS 가 각자 0.25 를 들고 있으면, 한쪽만 바뀌어도
 *   테스트는 초록인데 화면은 안 바뀐다(이 저장소가 반복해 데인 "무잠금 상수" 형태).
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { SATONG_POPUP_YIELD, SATONG_UI_Z } from "../satong-map-z";

const WEB_ROOT = join(__dirname, "..", "..");
const read = (rel: string) => readFileSync(join(WEB_ROOT, rel), "utf8");

/** 주석·문자열이 아니라 실제 규칙만 보게 하기 위한 최소 전처리(블록 주석 제거). */
const stripCssComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");

describe("상세팝업 양보 계약 — SSOT ↔ CSS ↔ 컴포넌트", () => {
  it("계약 상수가 비어 있지 않다(공허 진리 가드)", () => {
    // 이게 없으면 아래 단언들이 빈 문자열끼리 비교해 거저 통과한다.
    expect(SATONG_POPUP_YIELD.wrapperAttr).toMatch(/^data-/);
    expect(SATONG_POPUP_YIELD.passiveAttr).toMatch(/^data-/);
    expect(SATONG_POPUP_YIELD.passiveValue.length).toBeGreaterThan(0);
    expect(SATONG_POPUP_YIELD.dimOpacity).toBeGreaterThan(0);
    expect(SATONG_POPUP_YIELD.dimOpacity).toBeLessThan(1);
  });

  it("globals.css 의 감쇄 규칙이 계약 선택자와 **정확히** 맞는다", () => {
    const css = stripCssComments(read("app/globals.css"));
    const selector = `[${SATONG_POPUP_YIELD.wrapperAttr}="true"] [${SATONG_POPUP_YIELD.passiveAttr}="${SATONG_POPUP_YIELD.passiveValue}"]`;
    expect(css).toContain(selector);
  });

  it("★감쇄 값이 상수와 일치한다 — 한쪽만 바뀌면 초록인데 화면은 안 바뀐다", () => {
    const css = stripCssComments(read("app/globals.css"));
    const selector = `[${SATONG_POPUP_YIELD.wrapperAttr}="true"] [${SATONG_POPUP_YIELD.passiveAttr}="${SATONG_POPUP_YIELD.passiveValue}"]`;
    const block = css.slice(css.indexOf(selector));
    const body = block.slice(block.indexOf("{"), block.indexOf("}"));
    expect(body).toContain(`opacity: ${SATONG_POPUP_YIELD.dimOpacity}`);
    // 시각만 흐리고 클릭은 그대로면 "가려서 못 누르는" 상태가 남는다.
    expect(body).toContain("pointer-events: none");
  });

  it("★감쇄 규칙은 @layer 밖이어야 한다 — 안에 있으면 Leaflet 무레이어 CSS 에 진다", () => {
    const css = read("app/globals.css");
    const idx = css.indexOf(`[${SATONG_POPUP_YIELD.wrapperAttr}="true"]`);
    expect(idx).toBeGreaterThan(-1);
    // 규칙 앞부분에서 열린 중괄호와 닫힌 중괄호 수가 같아야 depth 0(무레이어)이다.
    const before = stripCssComments(css.slice(0, idx));
    const open = (before.match(/\{/g) || []).length;
    const close = (before.match(/\}/g) || []).length;
    expect(open).toBe(close);
  });

  it("지도 컴포넌트가 래퍼 속성을 팝업 상태로 토글한다(배선 실재)", () => {
    const src = read("components/map/SatongMultiMap.tsx");
    expect(src).toContain("SATONG_POPUP_YIELD.wrapperAttr");
    // Leaflet 이벤트에 실제로 물려 있어야 한다 — 상태만 있고 배선이 없으면 영원히 false 다.
    expect(src).toContain('map.on("popupopen"');
    expect(src).toContain('map.on("popupclose"');
  });

  it("양보 대상이 **두 파일 모두**에 표시돼 있다(한쪽만 하면 반쪽 처방)", () => {
    // 지도 자신의 크롬(코너 도크)과 셸이 주입하는 크롬(레일·배지행)은 같은 스택에서 경쟁한다.
    expect(read("components/map/SatongMultiMap.tsx")).toContain("SATONG_POPUP_YIELD.passiveAttr");
    expect(read("components/precheck/SatongMapShell.tsx")).toContain("SATONG_POPUP_YIELD.passiveAttr");
  });

  it("★중복 표면 상호배제 — 부모가 상세를 맡으면 지도는 팝업을 걸지 않는다", () => {
    const src = read("components/map/SatongMultiMap.tsx");
    // 라이브 실측(포항 호미곶 산1-1)에서 폴리곤 클릭 시 **같은 필지 정보 표면 둘**이 열리고
    // 상세 패널(z430)이 Leaflet 팝업을 덮었다(elementFromPoint 3점 전부 rival).
    // z 를 조정해도 "같은 내용을 두 번 그린다"는 사실은 남으므로, 소유권으로 가른다.
    expect(src).toContain("featureDetailOwnedRef");
    // 판정 기준이 onFeatureClick 프롭의 존재여야 한다 — 다른 기준으로 바뀌면 알린다.
    expect(src).toContain("const featureDetailOwnedByParent = !!onFeatureClick");
    // ★형제 둘 다 적용됐는가: 폴리곤 경로와 지오메트리 없는 대체 마커 경로.
    //   한쪽만 고치면 대체 마커에서 중복이 그대로 남는다(형제 스윕).
    const guarded = src.match(/featureDetailOwnedRef\.current\s*\?/g) || [];
    expect(guarded.length).toBeGreaterThanOrEqual(2);
  });

  it("불양보 표면은 표시하지 않는다 — 확인 카드는 사용자 결정 흐름이다", () => {
    const src = read("components/map/SatongMultiMap.tsx");
    const confirmIdx = src.indexOf("SATONG_UI_Z.confirmCard");
    expect(confirmIdx).toBeGreaterThan(-1);
    // 확인 카드 선언 근처(±400자)에 양보 표시가 붙어 있으면 안 된다.
    const around = src.slice(Math.max(0, confirmIdx - 400), confirmIdx + 400);
    expect(around).not.toContain("SATONG_POPUP_YIELD.passiveAttr");
    // 대조군: 확인 카드가 실제로 최상위 층에 있다는 전제가 유지되는가.
    expect(SATONG_UI_Z.confirmCard).toBe(Math.max(...Object.values(SATONG_UI_Z)));
  });
});
