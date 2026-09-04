import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/**
 * 잉크 계약 게이트 — 흰 배경 + 흰 글씨(비가시) 재발 방지.
 *
 * ■ 왜 필요한가 (재발 이력)
 *   2026-07-12 PR#270 이 "CTA 흰on흰 비가시"를 --saas-ink 고정으로 고쳤으나,
 *   막는 장치가 없어 2026-07-15 수지분석 입력 select 에서 같은 결함이 재발했다.
 *   개별 수정만으로는 계속 돌아온다 → 계약을 코드로 못박는다.
 *
 * ■ 근본 원인 (한 문장)
 *   밝은 배경을 칠하면서 자기 글자색을 선언하지 않으면, 조상의 색을 상속한다.
 *   앱에는 다크 서피스 컨테이너에 `text-white` 를 거는 지점이 200곳 넘게 있고
 *   (그 자체는 정상·필요), 그 안의 자식이 잉크를 빠뜨리면 즉시 흰on흰이 된다.
 *
 * ■ 계약
 *   밝은 배경을 칠하는 요소는 같은 className 에서 자기 글자색도 선언한다.
 *   (배경을 소유하면 잉크도 소유한다 — "칠했으면 책임진다")
 *
 * ■ 왜 토큰이 근본 해법인가
 *   `bg-white ... dark:bg-slate-950 dark:text-slate-100` 처럼 Tailwind 팔레트 +
 *   dark: 변종으로 짜면 라이트/다크를 손으로 짝맞춰야 하고 한쪽을 빠뜨리기 쉽다.
 *   `bg-[var(--surface-secondary)] text-[var(--text-primary)]` 는 선언 하나로
 *   양 테마가 해결되어 빠뜨릴 수가 없다. (DESIGN.md §D · B1)
 */

const WEB_ROOT = join(__dirname, "..");
const SCAN_DIRS = ["components", "app"];

/**
 * 잉크 의무가 생기는 배경 = **테마 불변** 밝은 배경만.
 *
 * `bg-white` / `bg-[var(--paper)]` 는 다크 테마에서도 밝다. 반면 상속색
 * `--text-primary` 는 다크에서 #e1e1ee(거의 흰색)로 뒤집힌다 →
 * **조상이 무엇이든 다크 테마에서 흰on흰**. 그래서 잉크를 반드시 고정해야 한다.
 *
 * 반대로 `bg-[var(--surface)]` 등 **테마 인식 토큰**은 짝인 `--text-primary` 도
 * 함께 뒤집히므로 기본 상속이 항상 안전하다 → 의무 없음(오탐 방지).
 */
const LIGHT_BG = /\bbg-(white|\[var\(--paper\)\])(?![/\w-])/;

/**
 * 배경이 다크 테마에서 뒤집히면(`dark:bg-…`) 상속색과 짝이 맞으므로 안전 → 의무 면제.
 * 즉 위험한 것은 "다크 대응이 없는 고정 흰 배경"이다.
 */
const HAS_DARK_BG = /\bdark:bg-/;

/** 자기 글자색 선언 — 임의값·팔레트·유틸 모두 인정. dark:/hover: 등 변종 전용은 불인정. */
const OWN_INK = /(^|\s)text-(\[|white\b|black\b|slate-|gray-|zinc-|neutral-|stone-|blue-|indigo-|emerald-|rose-|red-|amber-|cyan-|violet-)/;

/** 잉크 의무가 없는 요소 — 텍스트를 담지 않는 순수 도형/장식. */
const NO_TEXT_HINT = /\b(animate-ping|animate-pulse)\b|\bh-[0-9.]+ w-[0-9.]+\b.*\brounded-full\b/;

/** 의도적 예외는 이 주석을 같은 줄 또는 바로 윗줄에 단다. */
const IGNORE = "@ink-contract-ignore";

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx$/.test(entry) && !/\.test\.tsx$/.test(entry)) out.push(p);
  }
  return out;
}

type Violation = { file: string; line: number; snippet: string };

function findViolations(): Violation[] {
  const files = SCAN_DIRS.flatMap((d) => walk(join(WEB_ROOT, d)));
  const out: Violation[] = [];

  for (const file of files) {
    const lines = readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      const m = line.match(/className="([^"]*)"/);
      if (!m) return;
      const cls = m[1];
      if (!LIGHT_BG.test(cls)) return;
      if (HAS_DARK_BG.test(cls)) return; // 배경이 테마를 따라가면 상속색과 짝이 맞다
      if (OWN_INK.test(cls)) return;
      if (NO_TEXT_HINT.test(cls)) return;
      if (line.includes(IGNORE) || (i > 0 && lines[i - 1].includes(IGNORE))) return;
      out.push({
        file: relative(WEB_ROOT, file),
        line: i + 1,
        snippet: cls.length > 110 ? `${cls.slice(0, 110)}…` : cls,
      });
    });
  }
  return out;
}

describe("잉크 계약 — 밝은 배경은 자기 글자색을 선언해야 한다", () => {
  it("신규 위반이 없다 (흰 배경 + 잉크 미선언 = 흰on흰 위험)", () => {
    const violations = findViolations();

    // 실패 시 어디를 어떻게 고칠지 바로 보이게 한다.
    const report = violations
      .map((v) => `  ${v.file}:${v.line}\n    className="${v.snippet}"`)
      .join("\n");

    expect(
      violations.length,
      violations.length === 0
        ? ""
        : [
            "",
            `밝은 배경을 칠하면서 자기 글자색을 선언하지 않은 지점 ${violations.length}건.`,
            "조상에 text-white 가 있으면 흰 배경에 흰 글씨가 되어 보이지 않는다.",
            "",
            report,
            "",
            "고치는 법 — 토큰으로 배경·잉크를 함께 선언한다(라이트/다크 자동):",
            '  bg-[var(--surface-secondary)] text-[var(--text-primary)]',
            "온-다크 서피스 위의 흰 버튼이면 테마 불변 잉크를 고정한다:",
            '  bg-white text-[var(--saas-ink)]',
            `텍스트를 담지 않는 순수 도형이면 같은 줄/윗줄에 ${IGNORE} 주석을 단다.`,
            "",
          ].join("\n"),
    ).toBe(0);
  });

  it("검사기 자체가 동작한다 — 탐지 규칙 자기검증", () => {
    // 위반: 밝은 배경 + 잉크 없음
    expect(LIGHT_BG.test("rounded-xl border bg-white px-3")).toBe(true);
    expect(LIGHT_BG.test("bg-[var(--surface-secondary)] p-4")).toBe(false); // 테마 인식 토큰 = 의무 없음
    expect(OWN_INK.test("rounded-xl border bg-white px-3")).toBe(false);

    // 정상 1: 토큰으로 배경·잉크 동시 선언
    expect(
      OWN_INK.test("bg-[var(--surface-secondary)] text-[var(--text-primary)]"),
    ).toBe(true);

    // 정상 2: 온-다크 흰 버튼 + 테마 불변 잉크(PR#270 패턴)
    expect(OWN_INK.test("bg-white text-[var(--saas-ink)]")).toBe(true);

    // 알파 오버레이는 대상 아님(텍스트 서피스가 아니라 장식)
    expect(LIGHT_BG.test("absolute inset-0 bg-white/20")).toBe(false);

    // 배경이 dark: 로 뒤집히면 상속색과 짝이 맞으므로 면제(오탐 방지)
    expect(HAS_DARK_BG.test("bg-white shadow-sm dark:bg-slate-900")).toBe(true);

    // ★ 재발 결함의 실제 형태 — dark: 에만 잉크가 있고 라이트는 상속
    const regressed =
      "rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none dark:bg-slate-950 dark:text-slate-100";
    expect(LIGHT_BG.test(regressed)).toBe(true);
    expect(OWN_INK.test(regressed)).toBe(false); // text-sm 은 크기지 색이 아니다
  });
});
