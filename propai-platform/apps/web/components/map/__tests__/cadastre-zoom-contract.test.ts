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
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { CADASTRE_MIN_ZOOM, CADASTRE_ZOOM_HINT } from "@/components/map/SatongMultiMap";
import { __blockCommentRangesForOracle, assertWiredThrough } from "@/lib/source-invariant";

const FILE = "components/map/SatongMultiMap.tsx";

/**
 * ── 근거 복제 금지 락 (2026-08-16 신설) ──────────────────────────────────────
 *
 * ★왜: 2026-08-15 재측정으로 임계가 18→17 로 내려갔을 때 **CADASTRE_MIN_ZOOM 독스트링만**
 *   갱신됐고, 같은 파일 안의 복제본 두 개(minZoom 옆 · syncZoomNote 위)가 옛 임계를
 *   그대로 들고 남았다. 다음 세션이 그 낡은 숫자를 읽고 **정상인 임계를 되돌리려다**
 *   판정이 하루 늦어졌다. 낡은 주석이 오판을 *지지하는 증거*로 작동한 것이다.
 *
 * ★그래서 잠그는 것은 문구가 아니라 **구조**다: 근거(배율·바이트)는 그것을 정당화하는
 *   **export 상수의 독스트링 한 곳**에만 산다. 다른 자리는 상수를 가리키기만 한다.
 *   문구 목록을 잠그면 새 문구가 그대로 빠져나가지만, 이 규칙은 파생형이라 따라온다.
 *
 * ★한계(정직 고지): 이 락은 `z<숫자> 미만/이하` 꼴의 임계 주장과 `1,784B` 꼴의 바이트
 *   수치만 본다. `z10~17 전부 빈 타일` 같은 **구간 서술은 잡지 못한다** — 같은 패턴이
 *   용도지역(다른 레이어)의 정당한 근거와 구분되지 않아 오탐이 나기 때문이다.
 *   실제 결함은 두 규칙 모두에 걸렸으므로 잠금은 성립하지만, 전수는 아니다.
 */
type Comment = { text: string; isExportDoc: boolean };

/** 파일의 모든 주석을, "export 선언의 독스트링인가"와 함께 뽑는다. */
function commentsOf(src: string): Comment[] {
  return __blockCommentRangesForOracle(src, FILE).map(([start, end]) => ({
    text: src.slice(start, end),
    // 주석 뒤 공백을 건너뛴 자리가 export 면 그 선언의 독스트링이다 = 근거가 사는 자리.
    isExportDoc: /^\s*export\b/.test(src.slice(end, end + 40)),
  }));
}

const BYTES = /\d{1,3},\d{3}\s*B/;
/** `z17 미만`·`z16 이하` 꼴 + 근처(±40자)의 "빈 타일" 계열 판정. */
const THRESHOLD = /z\s*(\d{1,2})\s*(미만|이하)/g;
const EMPTY_VERDICT = /(빈 타일|완전투명|투명 타일|나오지 않는다|나오지 않았다)/;

/** 상수와 어긋난 임계 주장을 모은다(주석 전체 대상 — 독스트링도 예외가 아니다). */
function inconsistentThresholdClaims(src: string, minZoom: number): string[] {
  const bad: string[] = [];
  for (const c of commentsOf(src)) {
    for (const m of c.text.matchAll(THRESHOLD)) {
      const at = m.index ?? 0;
      const near = c.text.slice(Math.max(0, at - 40), at + m[0].length + 40);
      if (!EMPTY_VERDICT.test(near)) continue;
      const claimed = Number(m[1]);
      // "z<N> 미만이 빈 타일" ⇔ N === 임계 · "z<N> 이하가 빈 타일" ⇔ N === 임계-1
      const expected = m[2] === "미만" ? minZoom : minZoom - 1;
      if (claimed !== expected) bad.push(near.replace(/\s+/g, " ").trim());
    }
  }
  return bad;
}

/** export 독스트링 **밖**에 있는 바이트 수치 = 근거표 복제. */
function duplicatedEvidence(src: string): string[] {
  return commentsOf(src)
    .filter((c) => !c.isExportDoc && BYTES.test(c.text))
    .map((c) => c.text.replace(/\s+/g, " ").trim().slice(0, 120));
}

/** 2026-08-15 에 실제로 남았던 복제본을 그대로 재현한 대조군 — 탐지기가 살아 있는지 먼저 본다. */
const REGRESSION_SPECIMEN = `
/** 연속지적도가 그려지기 시작하는 최소 줌. */
export const CADASTRE_MIN_ZOOM = 17;
function f() {
  const t = wms({
    // VWorld 연속지적도는 z18 미만에서 완전투명 타일(1,784B)을 준다.
    //   z15 1,784B · z16 1,784B · z17 1,784B · z18 24,493B
    minZoom: CADASTRE_MIN_ZOOM,
  });
  return t;
}
`;

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
    // ★2026-08-24 계약 확장 — 이 파일의 자체 안내가 **둘**이 됐다(일반 + 이격 전용).
    //   종전 락은 `prev !== CADASTRE_ZOOM_HINT` 라는 **한 문구만** 기대했다. 그대로 두면
    //   "자기 안내인지"를 두 문구로 판정하는 코드가 위반으로 잡혀, 락이 **개선을 막는다**.
    //   그래서 판정자(`isOwnHint`)에 결속시킨다 — 의도(자기 안내일 때만 갈아끼운다)는 그대로다.
    expect(() =>
      assertWiredThrough({
        file: FILE,
        scope: /if \(below\) return prev/,
        mustContain: "isOwnHint(prev)",
        minMatches: 1,
      }),
    ).not.toThrow();
    expect(() =>
      assertWiredThrough({
        file: FILE,
        scope: /return isOwnHint\(prev\)/,
        mustContain: '""',
        minMatches: 1,
      }),
    ).not.toThrow();
    // ★판정자가 **두 안내를 모두** 자기 것으로 인정해야 한다 — 하나만 인정하면 나머지 하나가
    //   진짜 오류 노트처럼 취급돼 영영 안 지워진다(반대 방향 결함).
    expect(() =>
      assertWiredThrough({
        file: FILE,
        scope: /const isOwnHint =/,
        mustContain: "CADASTRE_ZOOM_HINT",
        minMatches: 1,
      }),
    ).not.toThrow();
  });

  it("★★탐지기가 살아 있다 — 실제로 있었던 복제본을 대조군으로 먼저 태운다", () => {
    // "위반 0"을 믿으려면 **같은 도구가 진짜 위반을 잡는지**를 먼저 봐야 한다.
    // (0건은 부재가 아니라 조회 오류일 수 있다 — 이 저장소가 반복해서 데인 자리다.)
    expect(inconsistentThresholdClaims(REGRESSION_SPECIMEN, 17)).not.toHaveLength(0);
    expect(duplicatedEvidence(REGRESSION_SPECIMEN)).not.toHaveLength(0);
    // 임계가 실제로 그 값이었다면(=18) 같은 문장은 위반이 아니다 — 상수에 결속돼 있다.
    expect(inconsistentThresholdClaims(REGRESSION_SPECIMEN, 18)).toHaveLength(0);
  });

  it("★임계를 말하는 주석이 상수와 어긋나지 않는다", () => {
    const src = readFileSync(resolve(process.cwd(), FILE), "utf-8");
    // 공허 진리 가드 — 검사 대상이 0건이면 "위반 0"은 아무 뜻이 없다.
    expect(commentsOf(src).length).toBeGreaterThan(20);
    const claims = [...src.matchAll(THRESHOLD)];
    expect(claims.length).toBeGreaterThan(0);
    expect(inconsistentThresholdClaims(src, CADASTRE_MIN_ZOOM)).toEqual([]);
  });

  it("★근거표는 상수 독스트링 한 곳에만 산다 — 복제가 낡으면 오판을 지지한다", () => {
    const src = readFileSync(resolve(process.cwd(), FILE), "utf-8");
    // 대상 모집단이 비지 않았는지 먼저 본다: 근거를 담은 독스트링이 실재해야 한다.
    expect(commentsOf(src).filter((c) => c.isExportDoc && BYTES.test(c.text)).length).toBeGreaterThan(0);
    // 그리고 독스트링 밖에는 없어야 한다.
    expect(duplicatedEvidence(src)).toEqual([]);
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
