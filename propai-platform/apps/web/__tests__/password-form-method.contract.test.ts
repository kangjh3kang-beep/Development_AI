/**
 * 비밀번호를 다루는 `<form>` 은 **반드시 `method="post"`** 여야 한다.
 *
 * ★왜 계약인가(실측된 사고): `<form>` 의 기본 method 는 **GET** 이다. 이 앱의 로그인 폼은
 *   `onSubmit={handleSubmit}` + `preventDefault()` 로 JS 가 처리하지만, **하이드레이션 전에
 *   제출되면 그 핸들러가 아직 없다** → 브라우저가 기본 동작(GET)을 수행하고
 *   **비밀번호가 URL 쿼리스트링에 실린다.**
 *
 *   실제 브라우저 재현(2026-08-13, `/en/login`):
 *     클릭 후 URL = `/en/login?email=ops%40propai.dev&password=super-secret-password`
 *     그 사이 API 요청은 **0건**(핸들러가 안 붙은 상태였다)
 *
 *   URL 에 실린 비밀번호는 브라우저 히스토리·Referer 헤더·프록시/서버 액세스 로그에 남는다.
 *   `method="post"` 를 주면 JS 가 붙기 전이라도 **본문으로** 나가고 URL 에 남지 않는다
 *   (JS 가 붙은 뒤에는 `preventDefault` 가 먼저라 동작 변화가 없다).
 *
 * ★목록이 아니라 **파생**으로 검사한다(규율 A-4): "비밀번호 입력이 있는 파일"을 코드에서
 *   찾아 그 안의 모든 `<form` 을 본다. 새 인증 화면이 생겨도 자동으로 감시망에 들어온다.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it, vi } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

// ── 저장소 전수 스캔 테스트의 시간 상한 ──────────────────────────────────────
//  이 파일은 `it` 안에서 저장소의 **모든 소스 파일(약 941개)** 을 다시 읽는다. 그래서 실행
//  시간이 **검증 대상의 성질이 아니라 그때의 CPU 경합**에 좌우된다 — 전체 스위트를 돌리면
//  워커가 붙는 만큼 느려져 기본 10초를 넘고, 단독 실행은 항상 통과한다(실측: 실패는 전부
//  `Test timed out in 10000ms` 이고 비타임아웃 실패는 0건). CI 는 더 느릴 수 있다.
//  ★10초는 **정확성 경계가 아니라 벽시계**다. 늘려도 잡아내는 결함은 그대로다.
//  ★근본 처방은 941파일 읽기를 모듈 스코프로 호이스팅하는 것이고, 별건으로 남겼다.
vi.setConfig({ testTimeout: 60_000 });


const ROOTS = ["components", "app"];

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (name === "node_modules" || name === ".next") continue;
    if (statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith(".tsx") && !p.includes("__tests__")) out.push(p);
  }
  return out;
}

describe("비밀번호 폼 계약 — method=post", () => {
  it("★비밀번호 입력을 가진 파일의 모든 <form> 이 method=\"post\" 다", () => {
    const files = ROOTS.flatMap((r) => walk(resolve(process.cwd(), r)));
    // 주석·문자열 트릭에 속지 않도록 스캔 전 주석을 벗긴다.
    const withPassword = files
      .map((f) => ({ f, src: __stripCommentsForScan(readFileSync(f, "utf-8"), f) }))
      .filter(({ src }) => /type="password"/.test(src));

    // 공허 진리 방지 — 대상이 0이면 이 검사는 무의미하다.
    expect(
      withPassword.length,
      "비밀번호 입력을 가진 파일을 하나도 못 찾았다 — 검사가 공허해진다",
    ).toBeGreaterThan(0);

    const offenders: string[] = [];
    let formCount = 0;
    for (const { f, src } of withPassword) {
      for (const m of src.matchAll(/<form\b[^>]*>/g)) {
        formCount += 1;
        if (!/\bmethod\s*=\s*"post"/.test(m[0])) {
          offenders.push(`${f.replace(process.cwd() + "/", "")}: ${m[0].slice(0, 80)}`);
        }
      }
    }

    // 공허 진리 방지 — `<form` 을 하나도 못 찾았다면 정규식이 죽은 것이다.
    expect(formCount, "비밀번호 파일에서 <form> 을 하나도 못 찾았다").toBeGreaterThan(0);

    expect(
      offenders,
      `기본 method 는 GET 이다 — 하이드레이션 전에 제출되면 비밀번호가 URL 에 실린다:\n${offenders.join("\n")}`,
    ).toEqual([]);
  });
});
