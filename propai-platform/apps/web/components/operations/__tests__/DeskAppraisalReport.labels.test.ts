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
    // 조건 분기가 있어야 한다(methods 길이로).
    expect(sec, "제목이 무조건 「교차검증」이다 — 본문의 «교차검증이 아닙니다»와 모순된다")
      .toMatch(/methods\??\.\s*length/);
    // 1개일 때 쓰는 문구에 「민감도」가 있어야 한다.
    expect(sec).toContain("민감도");
  });

  it("★위양성 축 — 형제 라벨(cap_rate 등)의 source 분기를 깨지 않는다", () => {
    const src = code();
    expect(src).toContain('cap_rate?.source === "R-ONE"');
    expect(src).toContain("!ms.rone_available");
  });
});
