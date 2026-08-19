/**
 * 사통맵 **pane 사다리** 락 — 상수가 아니라 **효과**를 잠근다.
 *
 * ## 왜 이 파일이 있나
 *
 * `satong-map-z.test.ts` 는 `LEAFLET_PANE_Z` 와 `SATONG_PANE_Z` 의 대소를 단언한다. 그 단언은
 * **같은 모듈 안 리터럴끼리의 비교**라 항상 참이고, 그래서 런타임을 전혀 보증하지 못했다.
 * 실제로 2026-08-17 까지 런타임은 그 단언의 **정반대**였다:
 *
 *   · `globals.css` 의 `.leaflet-pane { z-index: 1 !important }` 가 pane 을 전부 1 로 눌렀다
 *     (라이브 실측 `.leaflet-popup-pane` 계산값 = **1**).
 *   · 전부 같은 z 면 **페인트 순서 = DOM 순서**다. 실측 DOM 순서:
 *       tile < overlay < shadow < marker < tooltip < popup < proxy < **label**
 *     → 커스텀 label pane 이 **팝업 위**에 그려진다.
 *   · 그런데 그 테스트의 제목은 *"라벨이 팝업을 가리면 안 된다"* 이고 **초록**이었다.
 *     공허한 락을 넘어 **거짓을 보증하는 락**이었다.
 *
 * → 그래서 이 파일은 **CSS 를 본다.** 상수가 효과를 가질 수 있는 조건이 성립하는지,
 *   그리고 평탄화를 걷어낸 뒤 **유일하게 남은 방어**가 살아 있는지를 잠근다.
 *
 * ## 무엇을 잠그지 *못* 하나 (정직 경계)
 *
 * 이것은 여전히 **소스 검사**다. 실제 페인트 순서는 브라우저에서만 확정된다.
 * 계산된 z 와 DOM 순서 판정은 e2e 몫이다 — `e2e/popover-layer.spec.ts` 계열에서
 * `elementFromPoint` 로 재는 것이 정본이다(CLAUDE.md §D.18).
 * 여기서 잡는 것은 **"평탄화가 조용히 되돌아오는 것"** 과 **"격리가 사라지는 것"** 두 가지다.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { LEAFLET_PANE_Z, SATONG_PANE_Z } from "../satong-map-z";

const WEB_ROOT = join(__dirname, "..", "..");
const read = (rel: string) => readFileSync(join(WEB_ROOT, rel), "utf8");

/** 주석에 뚫리지 않게 블록 주석을 걷어낸다 — 이 저장소가 반복해 데인 형태(§회귀망 A.3). */
const stripCssComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");

/** `.leaflet-pane` 이 선택자 목록에 **규칙으로** 등장하는가(주석 언급이 아니라). */
const flattensPane = (code: string) =>
  /(^|[,{}\s])\.leaflet-pane\s*(,|\{)/m.test(code);

describe("사통맵 pane 사다리 — 상수가 아니라 효과를 잠근다", () => {
  it("전제: globals.css 를 실제로 읽었고 Leaflet 규칙이 그 안에 있다(공허 진리 가드)", () => {
    // ★이게 없으면 아래 "평탄화 없음"이 참인 이유가 "파일을 못 읽었다"일 수 있다.
    const code = stripCssComments(read("app/globals.css"));
    expect(code.length).toBeGreaterThan(10_000);
    expect(code).toContain(".leaflet-container"); // 양성대조 — 조회기 생존
    expect(code).not.toContain("zzz-absent-sentinel"); // 음성대조
  });

  it("★평탄화가 되돌아오지 않았다 — `.leaflet-pane` 을 z-index 로 누르지 않는다", () => {
    const code = stripCssComments(read("app/globals.css"));
    expect(
      flattensPane(code),
      "`.leaflet-pane` 을 다시 평탄화하고 있다. 그러면 LEAFLET_PANE_Z·SATONG_PANE_Z 가 " +
        "런타임 무효가 되고, 페인트 순서가 DOM 순서로 떨어져 **label pane 이 팝업 위**로 온다. " +
        "격리(isolation:isolate)만으로 새는 것은 이미 막힌다 — 2026-08-17 라이브 실험(합성 z=50 " +
        "형제 + 음성대조)에서 평탄화 유/무의 페인트순서 판정이 동일했다.",
    ).toBe(false);
  });

  it("★★격리는 남아 있다 — 평탄화를 걷어낸 지금 이것이 **유일한 방어**다", () => {
    const code = stripCssComments(read("app/globals.css"));
    const m = code.match(/\.leaflet-container\s*\{([^}]*)\}/);
    expect(m, "`.leaflet-container` 규칙 자체가 없다 — 지도가 헤더 위로 샌다").toBeTruthy();
    const body = m![1];
    expect(body, "isolation:isolate 가 사라졌다. 이제 pane 이 z 700 까지 살아 있으므로 " +
      "격리가 없으면 팝업·마커가 sticky 헤더(z-50) 위로 떠오른다.").toMatch(/isolation:\s*isolate/);
    expect(body, "컨테이너 z-index 가 사라졌다 — 격리는 만들어도 층 위치가 떠 버린다").toMatch(/z-index:\s*0/);
  });

  it("컨트롤 평탄화는 그대로 둔다 — 이 PR 이 건드리지 않은 범위임을 명시", () => {
    // 범위를 넓히지 않았다는 사실 자체를 잠근다. 나중에 누가 "왜 controls 는 남았지"를
    // 물을 때 근거가 여기에 있다(실험에서 1000 으로 되돌려도 새지 않았으나 무관해 제외).
    const code = stripCssComments(read("app/globals.css"));
    expect(code).toMatch(/\.leaflet-control\s*\{[^}]*z-index:\s*1\s*!important/);
  });

  it("상수 사다리가 Leaflet 실제 순서와 어긋나지 않는다(리터럴 항등식임을 알고 쓴다)", () => {
    // ★이 단언은 **항등식**이다 — 런타임을 보증하지 않는다. 상수를 손댈 때 순서가
    //   흐트러지는 것만 막는 용도이고, 효과 보증은 위 CSS 단언이 한다.
    //   (이 사실을 적어 두지 않으면 다음 사람이 이 초록을 런타임 보증으로 읽는다.)
    expect(LEAFLET_PANE_Z.overlay).toBeLessThan(SATONG_PANE_Z.label);
    expect(SATONG_PANE_Z.label).toBeLessThan(LEAFLET_PANE_Z.marker);
    expect(LEAFLET_PANE_Z.marker).toBeLessThan(LEAFLET_PANE_Z.tooltip);
    expect(LEAFLET_PANE_Z.tooltip).toBeLessThan(LEAFLET_PANE_Z.popup);
  });

  it("★검사기 자체의 판별력 — 평탄화 표기를 실제로 잡는가(대조군)", () => {
    // "평탄화 없음"이 참인 이유가 "정규식이 아무것도 못 잡아서"일 수 있다.
    // 잡아야 하는 표기와 잡으면 안 되는 표기를 둘 다 태운다.
    expect(flattensPane(".leaflet-pane { z-index: 1 !important; }")).toBe(true);
    expect(flattensPane(".leaflet-pane,\n.leaflet-top { z-index: 1 !important; }")).toBe(true);
    expect(flattensPane(".leaflet-top,\n.leaflet-pane,\n.leaflet-control { z-index: 1; }")).toBe(true);
    // 형제 선택자는 **평탄화가 아니다** — 이것들을 위반으로 신고하면 정상 CSS 를 막는다(§A.6).
    expect(flattensPane(".leaflet-pane-custom { z-index: 1; }")).toBe(false);
    expect(flattensPane(".leaflet-popup-pane { z-index: 700; }")).toBe(false);
    expect(flattensPane(".leaflet-label-pane { z-index: 450; }")).toBe(false);
  });
});
