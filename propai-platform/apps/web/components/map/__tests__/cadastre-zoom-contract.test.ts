/**
 * 지적도 저배율 계약 — "안 보임"을 "오류"로 말하지 않는다.
 *
 * ★왜 (2026-08-12 프로덕션 실측):
 *   사용자가 "지도에 정보가 전혀 안 나온다"고 지적한 화면을 추적하니 원인이 **두 개**였다.
 *     ① 축척 — VWorld 연속지적도는 z18 미만에서 **완전투명 타일**(1,784B·불투명 0픽셀)을
 *        준다. 200 OK 라 tileerror 도 안 뜬다. 종전 레이어 minZoom 은 10 이라
 *        z10~17 여덟 배율에서 **반드시 빈 타일**을 요청하고 있었다.
 *        같은 좌표 줌별 실측(강남·256px): z15/16/17 = 1,784B · z18 = 24,493B · z19 = 9,818B
 *     ② 상류 간헐 502 — 이건 진짜 오류이고 백엔드 재시도로 따로 봉합했다.
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
    expect(CADASTRE_MIN_ZOOM).toBe(18);
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
