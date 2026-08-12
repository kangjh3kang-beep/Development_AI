/**
 * 지적도 저배율 계약 — "안 보임"을 "오류"로 말하지 않는다.
 *
 * ★왜 (2026-08-12 프로덕션 실측):
 *   사용자가 "지도에 정보가 전혀 안 나온다"고 지적한 화면을 추적하니 원인이 **두 개**였다.
 *     ① 축척 — VWorld 연속지적도는 z18 미만에서 **완전투명 타일**(1,784B·불투명 0픽셀)을
 *        준다. 200 OK 라 tileerror 도 안 뜬다. 종전 레이어 minZoom 은 10 이라, z10~17
 *        여덟 배율에서 **반드시 빈 타일**을 요청하고 있었다.
 *        같은 좌표 줌별 실측(강남·256px): z15/16/17 = 1,784B · z18 = 24,493B · z19 = 9,818B
 *     ② 상류 간헐 502 — 이건 진짜 오류이고 백엔드 재시도로 따로 봉합했다.
 *
 *   둘을 같은 문구("지적 타일 오류")로 보여주면 사용자는 만성 장애로 읽는다.
 *   ①은 정상 동작이므로 **안내**여야 한다.
 */
import { describe, expect, it } from "vitest";

import { CADASTRE_MIN_ZOOM, CADASTRE_ZOOM_HINT } from "@/components/map/SatongMultiMap";
import { readSource, stripComments } from "@/lib/source-invariant";

const SRC = stripComments(readSource("components/map/SatongMultiMap.tsx"));

describe("지적도 저배율 계약", () => {
  it("★minZoom 이 실측 임계(z18)에 결속돼 있다 — 대역이 아니라 상수", () => {
    // 상수를 만들어 놓고 레이어가 옛 값을 쓰면 상수가 장식이 된다.
    expect(CADASTRE_MIN_ZOOM).toBe(18);
    expect(SRC).toMatch(/minZoom:\s*CADASTRE_MIN_ZOOM/);
    // 종전 값이 남아 있으면 z10~17 헛요청이 되살아난다.
    expect(SRC).not.toMatch(/zIndex:\s*5,[\s\S]{0,120}minZoom:\s*10\b/);
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
    expect(SRC).toMatch(/prev\s*&&\s*prev\s*!==\s*CADASTRE_ZOOM_HINT\s*\?\s*prev\s*:\s*CADASTRE_ZOOM_HINT/);
    expect(SRC).toMatch(/prev\s*===\s*CADASTRE_ZOOM_HINT\s*\?\s*""\s*:\s*prev/);
  });

  it("★zoomend 구독을 정리한다 — 언마운트 후 setState 누수 방지", () => {
    expect(SRC).toMatch(/map\.on\("zoomend",\s*syncZoomNote\)/);
    expect(SRC).toMatch(/map\.off\("zoomend",\s*syncZoomNote\)/);
  });
});
