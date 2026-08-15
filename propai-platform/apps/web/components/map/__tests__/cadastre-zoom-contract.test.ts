/**
 * 지적도 저배율 계약 — "안 보임"을 "오류"로 말하지 않는다.
 *
 * ★왜 (2026-08-12 프로덕션 실측):
 *   사용자가 "지도에 정보가 전혀 안 나온다"고 지적한 화면을 추적하니 원인이 **두 개**였다.
 *     ① 축척 — VWorld 연속지적도는 임계 미만에서 **완전투명 타일**(1,784B·불투명 0픽셀)을
 *        준다. 200 OK 라 tileerror 도 안 뜬다. 종전 레이어 minZoom 은 10 이라
 *        일곱 배율에서 **반드시 빈 타일**을 요청하고 있었다.
 *     ② 상류 간헐 502 — 이건 진짜 오류이고 백엔드 재시도로 따로 봉합했다.
 *
 * ★임계값 이력: 18 → **17**(2026-08-15 재측정). 6지역 × 채움/_line 2스타일 전부 z17 렌더 ·
 *   z16 전부 빈 타일. 근거표는 SatongMultiMap.tsx 의 CADASTRE_MIN_ZOOM 주석에 있다.
 *   **이 상수는 상류 사정에 딸린 값이라 주기적 재측정 대상**이다 — 여기 숫자를 바꾸려면
 *   그 주석의 재측정 절차(타일격자 정렬 BBOX · 불투명 픽셀 집계 · 다지역 · 2스타일)를 먼저 돌려라.
 *
 *   둘을 같은 문구("지적 타일 오류")로 보여주면 사용자는 만성 장애로 읽는다.
 *   ①은 정상 동작이므로 **안내**여야 한다.
 *
 * ★소스 검사는 공용 도구(assertWiredThrough)를 쓴다 — 직접 파일을 읽으면 주석이 조건을
 *   대신 충족시킨다(그 함정은 이 저장소에서 다섯 번 봉합됐다).
 */
import { describe, expect, it } from "vitest";

import { CADASTRE_MIN_ZOOM, CADASTRE_ZOOM_HINT } from "@/components/map/SatongMultiMap";
import { assertWiredThrough } from "@/lib/source-invariant";

const FILE = "components/map/SatongMultiMap.tsx";

describe("지적도 저배율 계약", () => {
  it("★minZoom 이 실측 임계에 결속돼 있다 — 대역이 아니라 상수", () => {
    expect(CADASTRE_MIN_ZOOM).toBe(17);
    // 상수를 만들어 놓고 레이어가 옛 값을 쓰면 상수가 장식이 된다.
    expect(() =>
      assertWiredThrough({
        file: FILE,
        scope: /minZoom: CADASTRE_MIN_ZOOM,/,
        mustContain: "CADASTRE_MIN_ZOOM",
        mustNotContain: /minZoom: 10\b/,
        minMatches: 1,
      }),
    ).not.toThrow();
  });

  it("★저배율 문구는 '오류'라고 말하지 않는다", () => {
    // 이 화면의 결함은 정상 동작을 오류로 표기한 것이었다 — 문구가 계약이다.
    expect(CADASTRE_ZOOM_HINT).not.toMatch(/오류|실패|error/i);
    expect(CADASTRE_ZOOM_HINT).toContain(String(CADASTRE_MIN_ZOOM));
    // 사용자가 무엇을 하면 되는지 말해야 한다(현상만 알리고 끝내지 않는다).
    expect(CADASTRE_ZOOM_HINT).toMatch(/확대/);
  });

  it("★막다른 안내를 하지 않는다 — 이 배율에서 해 볼 것을 말한다", () => {
    // "확대하세요"로만 끝내면 지금 볼 수 있는 것을 못 보고 지나간다.
    expect(CADASTRE_ZOOM_HINT).toContain("용도지역");
  });

  it("★★레이어 유무를 단정하지 않는다 — 지역 편차가 있는 것은 권유형으로만 말한다", () => {
    // 2026-08-15 실측: 호미곶면 3개 지점에서 lt_c_uq111(용도지역)이 z11~17 **전부 빈 타일**인데
    // 종전 문구는 "용도지역 레이어가 표시됩니다"라고 단정해 그 지역에서 **거짓말**이었다.
    // (같은 포항 시내·오산·양평은 렌더 — 국지적 데이터 구멍이라 도시/비도시로도 못 가른다.)
    // 이 파일의 규칙은 "늘 참인 것만 말한다"이고, 단정형은 그 규칙을 지킬 수 없다.
    expect(CADASTRE_ZOOM_HINT).not.toMatch(/용도지역[^.]{0,12}(표시됩니다|나옵니다|제공됩니다)/);
    // 권유형이어야 한다 — 데이터가 없는 지역에서도 거짓이 되지 않는다.
    expect(CADASTRE_ZOOM_HINT).toMatch(/용도지역[^.]{0,12}(확인|켜)/);
  });

  it("★안내가 진짜 오류 노트를 덮지 않는다", () => {
    // 상류 502 로 뜬 진짜 오류를 줌 변화가 지워 버리면 장애가 보이지 않게 된다.
    expect(() =>
      assertWiredThrough({
        file: FILE,
        scope: /if \(below\) return prev/,
        mustContain: "prev !== CADASTRE_ZOOM_HINT",
        minMatches: 1,
      }),
    ).not.toThrow();
    expect(() =>
      assertWiredThrough({
        file: FILE,
        scope: /return prev === CADASTRE_ZOOM_HINT/,
        mustContain: '""',
        minMatches: 1,
      }),
    ).not.toThrow();
  });

  it("★zoomend 구독을 정리한다 — 언마운트 후 setState 누수 방지", () => {
    expect(() =>
      assertWiredThrough({
        file: FILE,
        scope: /map\.off\("zoomend", syncZoomNote\)/,
        mustContain: "syncZoomNote",
        minMatches: 1,
      }),
    ).not.toThrow();
  });
});
