/**
 * 상세정보팝업 **양보 계약**의 형제 표면 락 — 목록형 금지, 소스에서 **파생**으로 전수 수집.
 *
 * ## 무엇이 뚫려 있었나(2026-08-18 실측)
 *
 * `#676` 이 만든 양보 계약은 CSS **자손 선택자** 하나였다:
 *   `[data-satong-popup-open="true"] [data-satong-chrome="passive"]`
 * 그래서 지도 래퍼 **안**의 크롬만 물러났다. 그런데 지도를 쓰는 화면들은 지도의 **형제**로
 * 오버레이를 얹는다(`NearbyTransactionsMap` 6개 · `ZoningSignalMap` 1개 ·
 * `ParcelBoundaryMap` 1개). 형제는 자손 선택자에 **원리적으로** 안 걸린다 —
 * 즉 그 오버레이들은 팝업을 **항상** 덮었고, 표시를 달아도 아무 일도 일어나지 않았을 것이다.
 *
 * ## 이 파일이 하는 일
 *
 * "지도(`<SatongMultiMap…`)를 렌더하면서 **그 뒤 형제 자리**에 절대위치 오버레이를 두는 곳"을
 * 소스에서 **파생**으로 전부 모아, 각각이 다음 둘 중 하나를 갖췄는지 단언한다:
 *   · `SATONG_POPUP_YIELD.passiveAttr` — 팝업이 열리면 물러난다
 *   · `SATONG_POPUP_YIELD.exemptAttr`  — 물러나면 **안 되는** 이유를 코드가 스스로 선언
 * 새 화면이 지도 옆에 오버레이를 얹으면 **자동으로** 이 감시망에 들어온다(손수 목록 없음).
 *
 * ★소스 검사는 주석·문자열에 뚫린다 — `__stripCommentsForScan`(TS 렉서 기반, 줄 주석 포함)을
 *   반드시 경유한다. 정규식으로 직접 주석을 지우려던 시도가 이 저장소에서 5번 관통당했다.
 * ★공허 진리 가드를 단언 **앞**에 둔다 — 수집이 0건이면 "위반 0"은 아무 뜻도 없다.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { SATONG_POPUP_YIELD } from "../../../lib/satong-map-z";
import { __stripCommentsForScan } from "../../../lib/source-invariant";

const WEB_ROOT = join(__dirname, "..", "..", "..");
/**
 * 동적 임포트 별칭(`<SatongMultiMapDynamic`)도 같은 접두라 함께 잡힌다 — 의도한 것이다.
 * ★앞에 식별자가 붙은 `<` 는 **제네릭**이다(`dynamic<SatongMultiMapProps>`) — JSX 태그가
 *   아니므로 뺀다. 이걸 안 뺐더니 파일 맨 위 `dynamic<…>` 한 줄이 잡혀 창이 파일 끝까지
 *   벌어졌고, 지도와 무관한 팝오버 4개가 위반으로 신고됐다(실측 — 위양성).
 */
const MAP_TAG = "<SatongMultiMap";
const MAP_TAG_RE = /(?<![A-Za-z0-9_$])<SatongMultiMap/;
/** 절대·고정 배치만이 형제를 덮을 수 있다(흐름 안 요소는 자리를 차지할 뿐 덮지 않는다). */
const POSITIONED = /\babsolute\b|\bfixed\b/;

function walk(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next" || name === "__tests__") continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, acc);
    else if (name.endsWith(".tsx") && !name.includes(".test.")) acc.push(full);
  }
  return acc;
}

/**
 * 여는 태그 하나를 통째로 떠낸다(`<div` 부터 짝이 맞는 `>` 까지).
 * 중괄호 깊이·따옴표를 세므로 `onClick={() => …}` 의 `>` 나 문자열 속 `>` 에 속지 않는다.
 */
function openingTags(text: string): string[] {
  const tags: string[] = [];
  const re = /<([A-Za-z][\w.]*)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    let i = re.lastIndex;
    let depth = 0;
    let quote: string | null = null;
    while (i < text.length) {
      const ch = text[i];
      if (quote) {
        if (ch === "\\") { i += 2; continue; }
        if (ch === quote) quote = null;
      } else if (ch === '"' || ch === "'" || ch === "`") {
        quote = ch;
      } else if (ch === "{") depth += 1;
      else if (ch === "}") depth -= 1;
      else if (ch === ">" && depth === 0) break;
      i += 1;
    }
    tags.push(text.slice(m.index, Math.min(i + 1, text.length)));
  }
  return tags;
}

/**
 * 지도 태그가 놓인 **부모 블록의 뒷부분**(= 지도의 뒤따르는 형제들이 사는 구간)을 떠낸다.
 * 들여쓰기로 가른다 — 이 저장소 JSX 는 prettier 로 일관 정렬돼 있다.
 * ★앞선 형제는 일부러 뺀다: 지도보다 먼저 그려지므로 팝업을 덮을 수 없다.
 */
function followingSiblingWindows(src: string): string[] {
  const lines = src.split("\n");
  const windows: string[] = [];
  lines.forEach((line, i) => {
    if (!MAP_TAG_RE.test(line)) return;
    const indent = line.length - line.trimStart().length;
    let end = lines.length;
    for (let j = i + 1; j < lines.length; j += 1) {
      if (!lines[j].trim()) continue;
      if (lines[j].length - lines[j].trimStart().length < indent) { end = j; break; }
    }
    windows.push(lines.slice(i, end).join("\n"));
  });
  return windows;
}

type Overlay = { file: string; tag: string };

const consumers: string[] = [];
const overlays: Overlay[] = [];

for (const full of walk(join(WEB_ROOT, "components")).concat(walk(join(WEB_ROOT, "app")))) {
  const raw = readFileSync(full, "utf8");
  if (!MAP_TAG_RE.test(raw)) continue;
  const src = __stripCommentsForScan(raw, full);
  if (!MAP_TAG_RE.test(src)) continue; // 주석 안에서만 언급한 파일 배제
  const file = relative(WEB_ROOT, full);
  consumers.push(file);
  for (const win of followingSiblingWindows(src)) {
    for (const tag of openingTags(win)) {
      if (tag.startsWith(MAP_TAG)) continue; // 지도 자신
      if (!POSITIONED.test(tag)) continue;
      overlays.push({ file, tag });
    }
  }
}

const has = (tag: string, member: "passiveAttr" | "exemptAttr") =>
  tag.includes(`SATONG_POPUP_YIELD.${member}`);

describe("사통맵 **형제** 오버레이 — 팝업 양보 계약 파생 락", () => {
  it("공허 진리 가드 — 수집이 실제로 있었다", () => {
    // 이게 없으면 아래 "위반 0"이 "대상 0" 때문일 수 있다(초록인데 아무것도 안 지킨 상태).
    expect(consumers.length).toBeGreaterThanOrEqual(4); // 실측 6개 파일
    expect(overlays.length).toBeGreaterThanOrEqual(6); // 실측 8개 오버레이
    expect(new Set(overlays.map((o) => o.file)).size).toBeGreaterThanOrEqual(2); // 실측 3개 파일
  });

  it("★형제 오버레이는 전부 '양보' 또는 '면제 사유'를 달고 있다", () => {
    const violations = overlays
      .filter((o) => !has(o.tag, "passiveAttr") && !has(o.tag, "exemptAttr"))
      .map((o) => `${o.file} :: ${o.tag.slice(0, 120).replace(/\s+/g, " ")}`);
    expect(violations).toEqual([]);
  });

  it("면제는 **빈 값으로 도장 찍기**가 안 된다 — 사유 문자열이 있어야 한다", () => {
    const exempts = overlays.filter((o) => has(o.tag, "exemptAttr"));
    expect(exempts.length).toBeGreaterThanOrEqual(1); // 대조군: 면제 채널이 실제로 쓰인다
    for (const o of exempts) {
      expect(o.tag).toMatch(/exemptAttr\]:\s*"[^"]+"/);
    }
  });

  it("대조군 — '양보' 채널도 실제로 쓰이고 있다", () => {
    // 전부 면제로 도망가면 계약이 이름만 남는다.
    expect(overlays.filter((o) => has(o.tag, "passiveAttr")).length).toBeGreaterThanOrEqual(3);
  });

  it("★CSS 가 형제 결합자를 갖는다 — 없으면 위 표시들이 전부 무효(조용한 무잠금)", () => {
    // ★여기만 정규식이다: `__stripCommentsForScan` 은 TS 렉서라 CSS 를 못 읽는다(진단 2343건).
    //   CSS 에는 줄 주석이 없고 블록 주석뿐이라, 이 한 줄로 **완전**하다(TS 와 달리 구멍이 없다).
    const css = readFileSync(join(WEB_ROOT, "app/globals.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const w = `[${SATONG_POPUP_YIELD.wrapperAttr}="true"]`;
    const p = `[${SATONG_POPUP_YIELD.passiveAttr}="${SATONG_POPUP_YIELD.passiveValue}"]`;
    expect(css).toContain(`${w} ${p}`); // 자손(지도 래퍼 안 크롬)
    expect(css).toContain(`${w} ~ ${p}`); // 뒤따르는 형제
    expect(css).toContain(`${w} ~ * ${p}`); // 형제의 자손(조건부 래퍼 한 겹)
  });

  it("★트리거가 지도 **루트**에 붙는다 — 안쪽에 있으면 형제 결합자가 닿지 않는다", () => {
    const src = __stripCommentsForScan(
      readFileSync(join(WEB_ROOT, "components/map/SatongMultiMap.tsx"), "utf8"),
      join(WEB_ROOT, "components/map/SatongMultiMap.tsx"),
    );
    // 종전 위치(지도 래퍼 `wrapperClass("relative")`)로 되돌아가면 이 단언이 깨진다.
    const wrapperIdx = src.indexOf('wrapperClass("relative")');
    expect(wrapperIdx).toBeGreaterThan(-1);
    const triggerIdx = src.indexOf("SATONG_POPUP_YIELD.wrapperAttr");
    expect(triggerIdx).toBeGreaterThan(-1);
    expect(triggerIdx).toBeLessThan(wrapperIdx);
  });

  it("★트리거 값이 팝업 상태에 묶여 있다 — 상수로 굳으면 계약이 영원히 잠든다", () => {
    // ★이 케이스는 **변이 검증이 만들어 냈다**: 값을 상수 "false" 로 바꿔도(팝업이 열려도
    //   절대 "true" 가 되지 않는다) 그때까지의 테스트가 하나도 안 죽었다(SURVIVED 실측).
    // ★왜 소스로 보나(런타임 불가 사유): Leaflet 은 jsdom 에서 뜨지 않아 `popupopen` 을
    //   발화시킬 수 없다 — 열림 상태를 실물로 만들 방법이 없다. 대신 `map.on("popupopen"`
    //   배선 실재는 `lib/__tests__/satong-popup-yield.test.ts` 가 따로 잠근다.
    const file = join(WEB_ROOT, "components/map/SatongMultiMap.tsx");
    const src = __stripCommentsForScan(readFileSync(file, "utf8"), file);
    const triggerIdx = src.indexOf("SATONG_POPUP_YIELD.wrapperAttr");
    expect(src.slice(triggerIdx, triggerIdx + 200)).toContain("detailPopupOpen");
  });
});
