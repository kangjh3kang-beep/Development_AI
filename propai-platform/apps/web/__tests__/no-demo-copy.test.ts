import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// apps/web 루트(이 파일은 apps/web/__tests__/ 안에 있으므로 한 단계 상위).
const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// 데모/가상 수치의 실화면 이식 금지(무목업). 과탐 위험이 있는 대형수치 정규식은
// 쓰지 않고, 핸드오프 목업에서 유입될 수 있는 명시 3종 문자열만 정적 차단한다.
const FORBIDDEN_DEMO_STRINGS = ["정자동 178-1", "18,921", "214,000"] as const;

/** 지정 디렉토리의 소스 파일(.ts/.tsx/.css)을 재귀 수집. __tests__/node_modules 제외. */
function collectSourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__tests__" || entry.name === "node_modules") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectSourceFiles(full));
    } else if (/\.(tsx?|css)$/.test(entry.name)) {
      files.push(full);
    }
  }
  return files;
}

const targetFiles = [
  ...collectSourceFiles(path.join(webRoot, "components/marketing")),
  path.join(webRoot, "components/dashboard/DashboardHome.tsx"),
];

describe("데모/가상 수치 정적 가드 (무목업)", () => {
  it("검사 대상 소스 파일을 하나 이상 수집한다", () => {
    expect(targetFiles.length).toBeGreaterThan(0);
  });

  for (const file of targetFiles) {
    const rel = path.relative(webRoot, file);
    it(`${rel} 에 금지된 데모 수치 문자열이 없다`, () => {
      const source = readFileSync(file, "utf8");
      for (const needle of FORBIDDEN_DEMO_STRINGS) {
        expect(
          source.includes(needle),
          `${rel} 에서 금지 데모 문자열 "${needle}" 발견`,
        ).toBe(false);
      }
    });
  }
});
