// @vitest-environment node
/**
 * 하이드레이션 프로브의 **판정 순수부**를 잠근다.
 *
 * ★왜(2026-08-27 · 독립 리뷰 F7): 프로브가 종료코드 계약(0=생존 / 1=프로브 사망 / 2=무효)을
 *   커밋 본문에 **표로 선언**했는데 그것을 지키는 검사가 **0건**이었다 —
 *   `vitest.config.ts` 가 `e2e/**` 를 수집에서 제외하므로 어떤 러너도 그 파일을 안 태운다.
 *   ★그리고 직전 커밋의 계획서 잠금표는 그 프로브 행을 싣고 표 아래에
 *   *"전부 필수 CI(vitest)에서 돈다"* 라고 적었다 — **그 행에 대해서는 거짓**이었다.
 *   선언을 락으로 바꾼다: 판정에 쓰이는 세 함수를 여기서 태운다.
 */
import { describe, expect, it } from "vitest";

import { countHydration, samePath, pickMutableText } from "@/lib/hydration/probe-text.mjs";

describe("countHydration — 두 모드가 공유하는 계수 경로", () => {
  it("하이드레이션 서명만 센다", () => {
    expect(countHydration([
      "[pageerror] Minified React error #418; visit https://react.dev/errors/418?args[]=text&args[]=",
      "[console] Hydration failed because the server rendered text didn't match the client.",
      "[console] Text content does not match server-rendered HTML.",
    ])).toBe(3);
  });
  it("★잡음은 세지 않는다 — 이게 없으면 대조군이 잡음으로 초록이 된다", () => {
    expect(countHydration([
      "[pageerror] PROBE_ALIVE",
      "[console] Failed to load resource: the server responded with a status of 401 ()",
      "[console] net::ERR_FAILED",
      "[console] Access to resource blocked by CORS policy",
    ])).toBe(0);
  });
  it("★잡음과 진짜가 섞여도 진짜만 센다(두 모집단이 갈린다)", () => {
    expect(countHydration([
      "[pageerror] PROBE_ALIVE",
      "[pageerror] Minified React error #418; …args[]=text",
    ])).toBe(1);
  });
});

describe("samePath — 가드의 위양성도 결함이다", () => {
  const BASE = "https://4t8t.net";
  it("같은 경로면 참", () => {
    expect(samePath("https://4t8t.net/ko/permits", "/ko/permits", BASE)).toBe(true);
  });
  it("다른 경로면 거짓(리다이렉트를 잡는다)", () => {
    expect(samePath("https://4t8t.net/ko/login?next=%2Fko%2Fpermits", "/ko/permits", BASE)).toBe(false);
  });
  it("★한글 경로에서 위양성이 없다 — 초판은 여기서 멀쩡한 측정을 무효로 버렸다", () => {
    expect(samePath("https://4t8t.net/ko/%EA%B7%9C%EC%A0%9C", "/ko/규제", BASE)).toBe(true);
  });
  it("★쿼리가 붙어도 위양성이 없다", () => {
    expect(samePath("https://4t8t.net/ko/permits", "/ko/permits?tab=1", BASE)).toBe(true);
  });
});

describe("pickMutableText — 개변 대상은 **파생**한다(목록은 곧 상한이 된다)", () => {
  it("★`<head>` 는 고르지 않는다 — React 가 하이드레이트하는 자리가 아니라 개변해도 불일치가 안 난다", () => {
    const html = `<html><head><title>유일한제목</title></head><body><main><p>본문유일텍스트</p></main></body></html>`;
    const got = pickMutableText(html);
    expect(got?.text).toBe("본문유일텍스트");
    expect(got?.at).toBeGreaterThan(html.indexOf("<body"));
  });
  it("★문서에서 여러 번 나오는 텍스트는 고르지 않는다(어디를 바꿨는지 알 수 없다)", () => {
    // ★4자 미만은 애초에 후보가 아니다(잡음 회피) — 픽스처도 그 계약을 지켜야 한다.
    const html = `<body><span>반복되는텍스트</span><span>반복되는텍스트</span><span>유일한텍스트</span></body>`;
    expect(pickMutableText(html)?.text).toBe("유일한텍스트");
  });
  it("★`<script>`·`<style>` 안은 고르지 않는다", () => {
    const html = `<body><script>var x=">스크립트안텍스트<";</script><p>진짜본문</p></body>`;
    expect(pickMutableText(html)?.text).toBe("진짜본문");
  });
  it("뒤쪽(라우트 고유 영역)을 앞쪽(공용 셸)보다 먼저 고른다", () => {
    const html = `<body><a>본문으로건너뛰기</a><footer><p>꼬리말고유</p></footer></body>`;
    expect(pickMutableText(html)?.text).toBe("꼬리말고유");
  });
  it("고를 것이 없으면 null — 호출부가 exit 2(무효)로 갈린다", () => {
    expect(pickMutableText("<body><span>x</span></body>")).toBeNull();
  });
  it("★4자 미만은 후보가 아니다(짧은 잡음 회피) — 위 픽스처들이 그 계약 위에 선다", () => {
    expect(pickMutableText("<body><span>세글자</span></body>")).toBeNull();
  });
  it("★앞뒤 문맥을 함께 돌려준다 — `picked` 문자열만으로는 공용 셸인지 라우트 고유인지 구별 못 한다", () => {
    const html = `<body><div class="wrap"><p>고유한본문텍스트</p></div></body>`;
    expect(pickMutableText(html)?.context).toContain("class=\"wrap\"");
  });
});

/**
 * ★**사각을 초록 안에 드러낸다**(동료 세션 제안 · 저장소 §B-13).
 *   PR 본문에만 적으면 머지되는 순간 아무도 안 읽는다. `it.todo` 는 러너가 매번 인쇄한다.
 */
describe("★프로브의 알려진 사각 — 부채를 초록 안에 남긴다", () => {
  it.todo(
    "필터가 `#418`·`Hydration failed`·`Text content` 만 본다 — **#423/#425 계열은 안 잡는다.** " +
      "control 은 자기가 이미 잡는 것만 태우므로 **이 사각을 스스로 드러내지 못한다**",
  );
  it.todo(
    "개변 텍스트가 `suppressHydrationWarning` 서브트리나 **Suspense 경계 안쪽**에 떨어졌을 때도 " +
      "같은 서명이 나는지 — **미측정**",
  );
  it.todo(
    "서비스워커의 `navigationNetworkFirst`(캐시 폴백) 경로를 control 이 **안 태운다** — " +
      "*\"SW 캐시가 준 옛 HTML + 새 JS\"* 라는 실제 불일치 원인 하나가 사정권 밖이다",
  );
  it.todo(
    "브라우저를 태우는 부분(로그인·내비·가로채기)은 여전히 **무잠금**이다 — " +
      "여기서 잠근 것은 판정 **순수부**뿐이다",
  );
});
