import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * ★콜백 화면이 **내부 구현을 사용자에게 말하지 않는다**.
 *
 *   2026-09-06 실측: 네이버·구글 콜백에
 *   *「인가 코드를 실제 `/auth/naver/callback` API에 전달해 브라우저 세션을 복구합니다」*
 *   가 사용자 화면에 떠 있었다(카카오엔 0건 — **형제가 갈렸다**).
 *   ★네이버 검수가 요구하는 **4번 캡처(완료 화면)** 가 정확히 이 화면이라,
 *     심사자에게 내부 API 경로가 찍힌 화면을 제출하게 된다.
 *
 * ★주석은 걷어내고 검사한다 — 이 파일들의 주석에는 **위 문구가 인용으로 남아 있고**,
 *   그것을 세면 정상 코드를 위반으로 신고한다(§8 「주석에 적은 예시가 다음 검사의 위양성」).
 *   실제로 이 락을 만들며 그 위양성을 한 번 냈다.
 */

const AUTH_DIR = path.resolve(__dirname, "..");

/** ★공급자를 **디렉토리에서 파생**한다 — 목록형은 곧 상한이 된다. */
function discoverCallbackClients(): string[] {
  return fs
    .readdirSync(AUTH_DIR)
    .filter((f) => /CallbackWorkspaceClient\.tsx$/.test(f))
    .sort();
}

/**
 * 주석(줄 주석과 블록 주석)을 걷어낸 실행 코드만 돌려준다.
 * ★블록 주석의 닫는 기호를 **여기 예시로 적지 않는다** — 주석이 조기 종료돼
 *   파서가 깨진다(이 파일을 쓰며 실제로 겪었다).
 */
function codeOnly(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .join("\n");
}

/**
 * ★검사 범위를 **사용자 대면 문구 블록(LABELS)** 으로 좁힌다.
 *   파일 전체를 훑으면 `apiClient.post("/auth/naver/callback", …)` 같은 **정당한 코드**까지
 *   위반으로 신고한다(이 락을 만들며 실제로 3사 전부 위양성을 냈다 · §A-6 위양성도 결함이다).
 */
function labelsBlock(src: string): string {
  const code = codeOnly(src);
  // ★경계를 건다 — indexOf("const LABELS") 는 `const LABELS_RENAMED` 도 잡는다
  //   (변이로 실증 · 오늘 세 번째 부분문자열 위음성).
  const m = /\bconst LABELS\s*:/.exec(code);
  if (!m) return "";
  const start = m.index;
  // 중괄호 균형으로 블록 끝을 찾는다 — 리터럴 모양이 아니라 구조로.
  let depth = 0;
  let i = code.indexOf("{", start);
  if (i < 0) return "";
  const from = i;
  for (; i < code.length; i++) {
    if (code[i] === "{") depth++;
    else if (code[i] === "}") {
      depth--;
      if (depth === 0) return code.slice(from, i + 1);
    }
  }
  return "";
}

/** 사용자에게 보이면 안 되는 개발자 언어. */
const FORBIDDEN: Array<[string, RegExp]> = [
  ["내부 API 경로", /\/auth\/[a-z]+\/callback/],
  ["API에 전달", /API에 전달/],
  ["callback 파라미터", /callback 파라미터/],
  ["code 확인 요구", /code[\u00b7\u30fb]?state?를? 확인|Check that the code parameter/],
  ["回调参数", /回调参数/],
];

describe("콜백 화면 문구 위생", () => {
  const files = discoverCallbackClients();

  it("공급자를 파생으로 찾는다 — 하한을 걸어 공허한 통과를 막는다", () => {
    // ★이 단언이 없으면 files=[] 일 때 아래 전부가 「대상 0개」로 조용히 통과한다.
    expect(files.length).toBeGreaterThanOrEqual(3);
    expect(files.join(",")).toMatch(/Kakao/);
    expect(files.join(",")).toMatch(/Naver/);
    expect(files.join(",")).toMatch(/Google/);
  });

  it.each(discoverCallbackClients())("%s: 개발자 언어가 없다", (file) => {
    const block = labelsBlock(fs.readFileSync(path.join(AUTH_DIR, file), "utf-8"));
    // ★하한 — 블록을 못 찾으면 "" 가 되어 모든 단언이 공허해진다
    expect(block.length, `${file}: LABELS 블록 추출 실패`).toBeGreaterThan(200);
    for (const [label, re] of FORBIDDEN) {
      expect(block, `${file}: ${label} 노출`).not.toMatch(re);
    }
  });

  it.each(discoverCallbackClients())(
    "%s: ★사용자 문구가 실재한다(문구를 전부 지운 구현은 통과 못 한다)",
    (file) => {
      const code = codeOnly(fs.readFileSync(path.join(AUTH_DIR, file), "utf-8"));
      // ★두 번째 모집단 — 금지어 부재만 보면 「전부 삭제」가 만점이 된다.
      const block = labelsBlock(fs.readFileSync(path.join(AUTH_DIR, file), "utf-8"));
      expect(block.length, `${file}: LABELS 블록 추출 실패`).toBeGreaterThan(200);
      // ★키마다 **비어 있지 않은** 문구가 있어야 한다.
      //   파일 전체에서 낱말 하나만 찾으면 `title: ""` 로 비워도 통과한다(변이로 실증).
      const empties = [...block.matchAll(/(\w+):\s*""/g)].map((x) => x[1]);
      expect(empties, `${file}: 빈 문구 키`).toEqual([]);
      expect(block).toMatch(/로그인(되었습니다|하는 중|을 완료하지)/);
      expect(block).toMatch(/다시 시도해 주세요/);
      // 3언어가 다 살아 있는가
      // ★실측: ko·en 은 따옴표 없이, zh-CN 은 하이픈 때문에 따옴표로 쓰인다.
      //   한 형식만 가정하면 정상 코드를 위반으로 신고한다.
      for (const loc of ["ko", "en", "zh-CN"]) {
        const re = new RegExp('(^|[\\s{,])"?' + loc.replace("-", "\\-") + '"?\\s*:\\s*\\{', "m");
        expect(re.test(code), `${file}: ${loc} 블록 없음`).toBe(true);
      }
    },
  );

  it("★주석 스트립이 실제로 동작한다(검사기 자신의 생존 대조군)", () => {
    const withComment = '// 인가 코드를 실제 `/auth/naver/callback` API에 전달해\nconst a = 1;';
    expect(codeOnly(withComment)).not.toMatch(/API에 전달/);
    // 대조군: 주석이 아니면 남아야 한다
    expect(codeOnly('const s = "API에 전달";')).toMatch(/API에 전달/);
  });
});
