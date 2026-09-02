// @vitest-environment node
/**
 * `.mjs` 스크립트의 **미정의 참조가 실제로 error 인가** — 선언이 아니라 **동작**을 잠근다.
 *
 * ★왜(2026-08-27 실측): `e2e/support/hydration-probe.mjs` 의 `run` 모드가 다른 모듈의 **지역**
 *   상수 `NOISE_RE` 를 자유 식별자로 참조한 채 남아 **실행 즉시 `ReferenceError`** 로 죽었다.
 *   `control` 모드는 그 줄을 지나지 않아 통과했고, 그래서 **측정 모드만 죽은 도구가 살아 보였다.**
 *   세 층이 전부 통과시켰다 — `tsc` 는 `.mjs` 미대상 · eslint 는 `no-undef` **미설정** ·
 *   순수부 테스트는 **스크립트 자체를 import 하지 않는다**.
 *
 * ★이 테스트는 `eslint.config.mjs` 에 그 규칙이 **적혀 있는지**를 보지 않는다(그건 대리 변수다).
 *   실제 설정으로 픽스처를 **태워서** error 가 나오는지 본다 — 규칙을 `off`/`warn` 으로 낮추면
 *   이 테스트가 빨개진다.
 */
import { describe, expect, it } from "vitest";

/** 실제 프로젝트 설정으로 텍스트 하나를 lint 한다(파일은 만들지 않는다). */
async function lintMjs(code: string, filePath: string) {
  const { ESLint } = await import("eslint");
  const eslint = new ESLint({ cwd: process.cwd() });
  const [res] = await eslint.lintText(code, { filePath });
  return res.messages;
}

describe(".mjs 자유 식별자 — 실행 불가를 lint 가 잡는다", () => {
  const 경로 = "e2e/support/__fixture__.mjs"; // `**/*.mjs` 블록에 걸리는 실경로 형태

  it("★원결함 형태(정의되지 않은 식별자)는 **error** 다", async () => {
    const msgs = await lintMjs("const rel = [].filter((e) => !NOISE_RE.test(e));\nexport default rel;\n", 경로);
    const undef = msgs.filter((m) => m.ruleId === "no-undef");
    expect(undef.length, "no-undef 가 꺼졌거나 이 경로가 규칙 블록에 안 걸린다").toBeGreaterThan(0);
    // ★severity 까지 못 박는다 — `warn` 으로 낮추면 lint 가 exit 0 이라 게이트가 아무것도 막지 않는다.
    expect(undef[0].severity, "warn 은 게이트가 아니다 — error 여야 한다").toBe(2);
    expect(undef[0].message).toContain("NOISE_RE");
  });

  it("★`.js` 도 같은 규칙 아래 있다 — `public/sw.js` 는 **프로덕션에 실리는** 서비스워커다", async () => {
    // 확장자를 하나만 잠그면 나머지가 조용히 사각으로 남는다(`tsc` 는 둘 다 안 본다).
    const msgs = await lintMjs("export const f = () => UNDEFINED_IN_JS;\n", "public/__fixture__.js");
    const undef = msgs.filter((m) => m.ruleId === "no-undef");
    expect(undef.length, "`.js` 가 규칙 블록에서 빠졌다").toBeGreaterThan(0);
    expect(undef[0].severity).toBe(2);
  });

  it("★음성 대조군 — 정상 코드는 걸리지 않는다(위양성도 결함이다)", async () => {
    // 같은 파일에서 선언한 것 · import 한 것 · 선언된 전역(process/console) 전부 통과해야 한다.
    const 정상 = [
      'import { readFileSync } from "node:fs";',
      "const NOISE = /x/;",
      "const rel = [].filter((e) => !NOISE.test(e));",
      'console.log(process.argv.length, rel.length, typeof readFileSync);',
      "export default rel;",
    ].join("\n");
    const msgs = await lintMjs(정상, 경로);
    expect(msgs.filter((m) => m.ruleId === "no-undef")).toEqual([]);
  });

  it("★브라우저 전역도 선언돼 있다 — 프로브가 page.evaluate 안에서 쓴다", async () => {
    const msgs = await lintMjs(
      "export const f = () => document.querySelectorAll('*').length + localStorage.length + window.innerWidth;\n",
      경로,
    );
    expect(msgs.filter((m) => m.ruleId === "no-undef"), "빠진 전역은 **정상 코드를 막는다**").toEqual([]);
  });
});
