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
import { buildMarketBasisLines } from "../../../lib/land/desk-appraisal-basis";

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

  // ─────────────────────────────────────────────────────────────
  // ★★독립 리뷰 R4 MEDIUM-2(2026-09-08) — **소스 grep 락을 행위 락으로 바꿨다**
  //   종전 락은 문자열 검사라, 렌더를 죽여도 토큰이 남아 초록이었다(리뷰어 실증):
  //       `{ms.housing_time_adjust.basis ?` → `{false && ms.housing_time_adjust.basis ?`
  //       → 10 passed  ::VERDICT=SURVIVED
  //   저장소 §A-3 이 *"소스 grep 대신 렌더 결과를 본다"* 라고 이미 적어 둔 자리다.
  //   ⇒ 줄 조립을 순수 함수로 꺼내고(`buildMarketBasisLines`) **그 함수를 직접 태운다**.
  // ─────────────────────────────────────────────────────────────
  describe("§Ⅵ 근거 줄 조립(행위)", () => {
    const base = { market_stats: { region: "서울", rone_available: true } } as never;

    function build(ms: Record<string, unknown>, extra: Record<string, unknown> = {}) {
      return buildMarketBasisLines({
        ...(base as object),
        ...extra,
        market_stats: { region: "서울", rone_available: true, ...ms },
      } as never);
    }

    it("★R-ONE 출처가 아니면 줄을 **만들지 않는다**(지어낸 실측 라벨 금지)", () => {
      const lines = build({ cap_rate: { source: "기본", pct: 4.5, basis: "문서화된 기본값" } });
      expect(lines.join("\n")).not.toContain("자본환원율");
    });

    it("★세 형제가 **모두** basis 를 싣는다 — 비대칭이 구조적으로 불가능하다", () => {
      const lines = build({
        cap_rate: { source: "R-ONE", pct: 4.5, basis: "상업용 실측" },
        jeonse_conversion_rate: { source: "R-ONE", pct: 5.4, basis: "전월세전환율 실측" },
        housing_time_adjust: { source: "R-ONE", factor: 1.0243, basis: "주택지수 실측" },
      });
      // ★공허 방지 — 세 줄이 실제로 만들어졌는가.
      expect(lines.filter((l) => l.startsWith("· 자본환원율")).length).toBe(1);
      expect(lines.filter((l) => l.startsWith("· 전월세전환율")).length).toBe(1);
      expect(lines.filter((l) => l.startsWith("· 주택가격지수")).length).toBe(1);
      for (const head of ["· 자본환원율", "· 전월세전환율", "· 주택가격지수"]) {
        const line = lines.find((l) => l.startsWith(head))!;
        expect(line, `${head} 줄이 basis 를 안 싣는다`).toContain("실측");
        expect(line).toContain(" — ");
      }
    });

    it("★basis 가 없으면 빈 대시를 그리지 않는다(위양성 축)", () => {
      const lines = build({ cap_rate: { source: "R-ONE", pct: 4.5 } });
      const line = lines.find((l) => l.startsWith("· 자본환원율"))!;
      expect(line).toBe("· 자본환원율(R-ONE 실측): 4.5%");
    });

    // ★★독립 리뷰 R5 MEDIUM-3(2026-09-08): 이 락은 종전에 **`cap_rate` 로** scope 분기를 태웠다.
    //   그런데 `commercial_cap_rate`·`jeonse_conversion_rate` 는 `scope` 키를 **한 번도 싣지 않는다**
    //   (전국 대체를 안 하므로 실을 이유가 없다) — 즉 그 조합은 **라이브에서 발생 불가**였고,
    //   실제로 대체가 일어나는 유일한 통계(`housing_time_adjust`)는 태워지지 않았다.
    //   함수는 잠겨 있었지만 «실소비를 잠갔다» 는 라벨이 과장이었다. ⇒ 발생 가능한 조합으로 옮긴다.
    it("★scope 가 요청 지역과 다르면 **화면이 그렇게 말한다**(실제로 대체가 일어나는 통계로)", () => {
      const substituted = build({
        housing_time_adjust: { source: "R-ONE", factor: 1.0243, basis: "주택지수 실측", scope: "전국" },
      });
      const line = substituted.find((l) => l.startsWith("· 주택가격지수"))!;
      expect(line).toContain("범위 전국");
      expect(line).toContain("실데이터가 아닙니다");

      // ★두 모집단을 가른다 — 같은 지역이면 그 경고가 **뜨면 안 된다**.
      const own = build({
        housing_time_adjust: { source: "R-ONE", factor: 1.0243, basis: "주택지수 실측", scope: "서울" },
      });
      expect(own.find((l) => l.startsWith("· 주택가격지수"))!).not.toContain("실데이터가 아닙니다");
    });

    it("★시·도 미해석이면 화면이 **그 사실을 말한다**(R5 LOW-1 — 전국 == 전국 침묵 봉합)", () => {
      const unresolved = buildMarketBasisLines({
        market_stats: { region: "전국", region_resolved: false, rone_available: true },
      } as never);
      expect(unresolved.some((l) => l.includes("시·도를 해석하지 못해"))).toBe(true);

      // ★위양성 축 — 해석에 성공했으면 그 줄이 **뜨면 안 된다**.
      const resolved = build({});
      expect(resolved.some((l) => l.includes("시·도를 해석하지 못해"))).toBe(false);
    });

    it("★R-ONE 미가용이면 근사값 고지가 뜬다", () => {
      const lines = build({ rone_available: false });
      expect(lines.some((l) => l.startsWith("· 시장통계:"))).toBe(true);
    });

    it("★시점수정 사유는 그대로 첫 줄에 실린다", () => {
      const lines = build({}, { time_adjust_basis: "R-ONE 지가변동률 서울 실데이터" });
      expect(lines[0]).toBe("· 시점수정: R-ONE 지가변동률 서울 실데이터");
    });
  });

  it("★컴포넌트가 그 순수 함수를 **실제로 부른다**(배선 축은 따로 잠근다)", () => {
    // ★함수가 옳아도 화면이 안 부르면 아무 일도 일어나지 않는다 — 축이 다르다.
    expect(code()).toContain("buildMarketBasisLines(res)");
  });

});
