/**
 * 탁상감정 보고서 — **라벨이 거짓말하지 않는다.**
 *
 * ## 왜 (2026-09-07 라이브 적발)
 *
 * ① 「지가변동률 추이 … — **R-ONE 실데이터**」가 **조건 없이** 출력됐다. 실측하니 그
 *    시계열은 기간 고유가 **1개**(전부 202607) — 24개월이 아니라 **같은 달의 24개 지역**.
 *    ★같은 파일의 형제들(cap_rate·전월세·주택지수)은 **이미 `source === "R-ONE"` 로
 *    분기**하고 있었다. **여기만 안 했다**(§29 형제를 먼저 봐라).
 * ② §Ⅳ 제목이 **「복수 시나리오 교차검증」** 인데 본문 note 는 *"이는 교차검증이
 *    아닙니다"* 라고 말했다. **제목과 본문이 정면 모순**이고 사람은 **제목을 믿는다**.
 *
 * ★소스 검사이지만 **주석을 걷어내고** 본다 — 위 설명문 자체가 위양성이 되지 않게.
 */
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const SRC = path.resolve(__dirname, "..", "DeskAppraisalReportClient.tsx");

/** 실행 라인만 — JSX 주석·블록 주석·줄 주석 제거. */
function code(): string {
  return fs
    .readFileSync(SRC, "utf8")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
}

describe("탁상감정 보고서 라벨", () => {
  it("★스캔이 실제 파일을 읽는다(공허진리 차단)", () => {
    const src = code();
    expect(src.length).toBeGreaterThan(5000);
    expect(src).toContain("지가변동률 추이");
  });

  it("「R-ONE 실데이터」를 **무조건** 쓰지 않는다", () => {
    const src = code();
    // 지가변동률 추이 라벨 줄에 그 문구가 리터럴로 박혀 있으면 실패.
    const idx = src.indexOf("지가변동률 추이");
    const around = src.slice(idx, idx + 400);
    expect(around, "지가변동률 라벨이 조건 없이 「R-ONE 실데이터」라고 단정한다").not.toContain(
      "R-ONE 실데이터",
    );
    // 대신 백엔드가 준 scope 를 읽어야 한다.
    expect(around).toContain("scope");
  });

  it("시계열이 아닐 때 **그 사실을 화면이 말한다**", () => {
    const src = code();
    expect(src).toContain("is_time_series");
    expect(src).toContain("distinct_periods");
  });

  it("★「교차검증」은 방법이 2개 이상일 때만 제목에 쓴다", () => {
    const src = code();
    const idx = src.indexOf('no="Ⅳ"');
    expect(idx, "§Ⅳ 섹션을 찾지 못했다 — 조회기 사망").toBeGreaterThan(-1);
    const sec = src.slice(idx, idx + 700);
    // ★★독립 리뷰 적발(MEDIUM-8) — 종전 락은 `/methods\??\.\s*length/` 존재와
    //   「민감도」 문자열만 봐서, 임계를 `>= 1` 로 바꾸거나 **방향을 `< 2` 로 뒤집어도
    //   통과**했다(변이 2/2 SURVIVED). **임계도 방향도 안 잠갔다.**
    // ★그리고 CRITICAL-3 — 축이 `methods.length` 면 W5 등재 때문에 **항상 참**이라
    //   그 분기는 도달 불가였다. 축은 **적용된 개수**여야 한다.
    expect(sec, "축이 «적용된 방법 수»가 아니다 — 목록 길이는 W5 등재로 항상 2 이상이다")
      .toMatch(/filter\(\s*\(m\)\s*=>\s*m\.applicable\s*!==\s*false\s*\)\s*\.length/);
    // ★임계와 방향을 못 박는다(>= 2 · 그 이상/이하가 아니라 정확히).
    expect(sec, "임계·방향이 잠기지 않았다").toMatch(/\.length\s*>=\s*2\s*$/m);
    // 두 갈래 문구가 **둘 다** 있어야 한다(한쪽만 있으면 분기가 죽어도 통과한다).
    expect(sec).toContain("민감도");
    expect(sec).toContain("교차검증");
  });

  it("★미적용 방법의 단가를 **0 으로 그리지 않는다**", () => {
    // 종전 `Math.round(m.unit_price)` 는 null → **0** 이라 「0원/㎡」가 값처럼 보였다.
    // ★★자체 적발: 첫 판은 `Math.round(m.unit_price)` 라는 **정확한 철자**만 막았는데,
    //   변이가 `m.unit_price as number` 로 쓰자 **통과**했다(정규식이 좁았다).
    //   → **가드 없이 쓰이는 형태 전부**를 막고, 삼항이 실제로 있는지도 본다.
    const src = code();
    const idx = src.indexOf("m.unit_price");
    expect(idx, "단가 렌더를 찾지 못했다 — 조회기 사망").toBeGreaterThan(-1);
    // `Math.round(m.unit_price …)` 앞에 같은 줄/근처에 hasPrice 삼항이 있어야 한다.
    const guarded = /hasPrice\s*\?\s*Math\.round\(m\.unit_price/;
    expect(src, "null 단가가 가드 없이 0 으로 그려진다").toMatch(guarded);
    // 가드 밖에서 unit_price 를 반올림하는 곳이 있으면 실패.
    const unguarded = src
      .split("\n")
      .filter((ln) => /Math\.round\(m\.unit_price/.test(ln) && !/hasPrice/.test(ln));
    expect(unguarded, `가드 없는 단가 렌더: ${unguarded.join(" | ")}`).toEqual([]);
    // "—" 폴백이 실제로 있어야 한다(0 대신 무엇을 그리는지).
    expect(src).toMatch(/hasPrice[\s\S]{0,80}"—"/);
  });

  it("★4방법 표가 적용 여부와 미적용 사유를 그린다", () => {
    const src = code();
    expect(src).toContain("m.applicable");
    expect(src).toContain("m.why_not");
    expect(src).toContain("미적용");
  });

  it("★물건표시 정합을 «확인 요청»으로 보여 준다(판정 아님)", () => {
    // ★★자체 적발: 첫 판은 `toContain("subject_consistency")` 라 **이름이 있는지**만
    //   봤다. 변이가 조건을 `{false && (` 로 바꾸자 **통과**했다 — 문자열은 남으니까.
    //   → **조건식의 구조**를 본다(이 세션에서 내가 반복해 지적한 그 결함이다).
    const src = code();
    expect(src, "정합 카드가 응답 값으로 분기하지 않는다(조건이 죽었을 수 있다)").toMatch(
      /res\.subject_consistency\s*&&\s*!res\.subject_consistency\.ok\s*&&/,
    );
    expect(src).toContain("확인이 필요한 표시 조합");
    // conflicts 를 실제로 순회해야 한다(카드만 있고 내용이 없으면 무의미).
    expect(src).toMatch(/subject_consistency\.conflicts\.map/);
    // 근거 문구도 함께(법적 근거 미확인을 숨기지 않게).
    expect(src).toMatch(/subject_consistency\.basis/);
  });

  it("★위양성 축 — 형제 라벨(cap_rate 등)의 source 분기를 깨지 않는다", () => {
    const src = code();
    expect(src).toContain('cap_rate?.source === "R-ONE"');
    expect(src).toContain("!ms.rone_available");
  });

  // ★★독립 리뷰 R3 HIGH-3 회귀 락(2026-09-08)
  //   백엔드가 「전국 대체」를 scope + basis 로 정직하게 말하도록 고쳤는데, 이 줄은 factor 만
  //   렌더해 **정직성이 화면에 도달하지 않았다** — 요청 시·도가 아닌 계수가 아무 단서 없이
  //   「주택가격지수 누적변동: 1.0243」으로 보였다.
  //   ★바로 위 형제(cap_rate)는 이미 basis 를 렌더한다 — **같은 블록 안의 비대칭**이었다.
  it("주택가격지수 줄이 basis(정직 고지)를 함께 렌더한다 — 형제와 대칭", () => {
    const lines = code().split("\n");
    const line = lines.find((l) => l.includes("housing_time_adjust?.source") && l.includes("<li>"));
    expect(line, "housing_time_adjust 렌더 줄을 못 찾았다(수집기 사망)").toBeTruthy();
    expect(line!).toContain("housing_time_adjust.basis");
    // 대조군 — 형제가 실제로 basis 를 렌더하는가(이 락의 기준점).
    const sibling = lines.find((l) => l.includes("cap_rate?.source") && l.includes("<li>"));
    expect(sibling, "형제 줄을 못 찾았다").toBeTruthy();
    expect(sibling!).toContain("cap_rate.basis");
  });

  it("Stat 타입이 scope 를 담는다 — 기계 판독 축이 프론트에 도달 가능해야 한다", () => {
    const ts = fs.readFileSync(
      path.resolve(__dirname, "..", "..", "..", "lib", "land", "desk-appraisal.ts"),
      "utf8",
    );
    expect(ts).toMatch(/type Stat = \{[^}]*scope\?: string/);
  });
});
