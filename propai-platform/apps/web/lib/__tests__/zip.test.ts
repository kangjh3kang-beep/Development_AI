/**
 * ZIP 작성기의 **외부 오라클 검증**.
 *
 * 내가 쓴 파서로 내가 쓴 ZIP 을 읽으면 둘이 같은 오해를 공유해도 초록이다(자기참조).
 * 그래서 **파이썬 `zipfile`** 로 실제 해제해 대조한다 — 우리 코드와 무관한 판정자다.
 * 파이썬이 없는 환경에서는 그 사실을 말하고 건너뛴다(조용한 초록 금지).
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { buildZip, crc32, safeFileName, uniqueName } from "@/lib/zip";

const enc = (s: string) => new TextEncoder().encode(s);

function pythonAvailable(): boolean {
  try {
    execFileSync("python3", ["-c", "import zipfile"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

/** 파이썬으로 해제해 {이름: 내용} 을 돌려준다. 깨진 아카이브면 던진다. */
function unzipWithPython(bytes: Uint8Array): Record<string, string> {
  const dir = mkdtempSync(join(tmpdir(), "ziptest-"));
  const zipPath = join(dir, "a.zip");
  try {
    writeFileSync(zipPath, bytes);
    const out = execFileSync(
      "python3",
      [
        "-c",
        [
          "import json,sys,zipfile",
          "z=zipfile.ZipFile(sys.argv[1])",
          "bad=z.testzip()",
          "assert bad is None, bad",
          "print(json.dumps({n: z.read(n).decode('utf-8') for n in z.namelist()}))",
        ].join("\n"),
        zipPath,
      ],
      { encoding: "utf8" },
    );
    return JSON.parse(out);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

describe("crc32", () => {
  it("표준 검증값 — \"123456789\" 의 CRC-32 는 0xCBF43926", () => {
    expect(crc32(enc("123456789"))).toBe(0xcbf43926);
  });

  it("빈 입력은 0", () => {
    expect(crc32(new Uint8Array(0))).toBe(0);
  });

  it("한 바이트만 달라도 값이 바뀐다(대조군)", () => {
    expect(crc32(enc("abc"))).not.toBe(crc32(enc("abd")));
  });
});

describe("buildZip — 외부 오라클(python zipfile)", () => {
  const hasPython = pythonAvailable();

  it("전제: 판정자(python zipfile)를 쓸 수 있다", () => {
    // 못 쓰면 아래 검증들은 **감사되지 않은 것**이다 — 조용히 넘어가지 않도록 여기서 말한다.
    expect(hasPython, "python3 가 없어 ZIP 을 외부에서 검증하지 못했다").toBe(true);
  });

  it.runIf(hasPython)("★파이썬이 해제한 내용이 넣은 것과 같다", () => {
    const zip = buildZip([
      { name: "a.txt", data: enc("hello") },
      { name: "b.txt", data: enc("world") },
    ]);
    expect(unzipWithPython(zip)).toEqual({ "a.txt": "hello", "b.txt": "world" });
  });

  it.runIf(hasPython)("★한글 파일명이 깨지지 않는다(UTF-8 플래그)", () => {
    const zip = buildZip([{ name: "등기부_내삼미동 448-2.txt", data: enc("본문") }]);
    const got = unzipWithPython(zip);
    expect(Object.keys(got)).toEqual(["등기부_내삼미동 448-2.txt"]);
    expect(got["등기부_내삼미동 448-2.txt"]).toBe("본문");
  });

  it.runIf(hasPython)("빈 아카이브도 유효하다", () => {
    expect(unzipWithPython(buildZip([]))).toEqual({});
  });

  it.runIf(hasPython)("항목이 많아도 오프셋이 어긋나지 않는다(30건)", () => {
    const entries = Array.from({ length: 30 }, (_, i) => ({
      name: `f${i}.txt`,
      data: enc(`내용-${i}-${"x".repeat(i * 7)}`),
    }));
    const got = unzipWithPython(buildZip(entries));
    expect(Object.keys(got)).toHaveLength(30);
    expect(got["f29.txt"]).toBe(`내용-29-${"x".repeat(203)}`);
  });

  it.runIf(hasPython)("★CRC 가 틀리면 파이썬이 잡는다(오라클이 실제로 판정함을 확인)", () => {
    const zip = buildZip([{ name: "a.txt", data: enc("hello") }]);
    // ★본문 한 바이트를 뒤집는다 → 기록된 CRC 와 어긋나 `testzip()` 이 실패해야 한다.
    //   (로컬 헤더 CRC 를 건드리는 것으로는 부족하다 — 파이썬은 **중앙 디렉터리**의
    //    메타데이터를 읽으므로 로컬 헤더 변조를 그냥 지나친다. 실측으로 확인했다.)
    const dataAt = 30 + "a.txt".length;
    const broken = new Uint8Array(zip);
    broken[dataAt] ^= 0xff;
    expect(() => unzipWithPython(broken)).toThrow();
  });
});

describe("safeFileName", () => {
  it("★지번의 숫자·하이픈을 지우지 않는다 — 문자 범위 오작성으로 숫자가 사라진 적이 있다", () => {
    expect(safeFileName("내삼미동 448-2", "x")).toBe("내삼미동 448-2");
  });

  it("경로 구분자와 상위 참조를 없앤다(zip slip)", () => {
    expect(safeFileName("../../etc/passwd", "x")).not.toContain("/");
    expect(safeFileName("../../etc/passwd", "x")).not.toContain("..");
  });

  it("경로 구분자만 있으면 밑줄로 바뀐다(비지 않는다)", () => {
    expect(safeFileName("///", "대체")).toBe("___");
  });

  it("정말로 비면 대체 이름을 쓴다 — 이름 없는 엔트리를 만들지 않는다", () => {
    expect(safeFileName("   ", "대체")).toBe("대체");
    expect(safeFileName("", "대체")).toBe("대체");
  });
});

describe("uniqueName", () => {
  it("★같은 지번이 둘이면 덮어쓰지 않는다", () => {
    const taken = new Set<string>();
    expect(uniqueName("a.pdf", taken)).toBe("a.pdf");
    expect(uniqueName("a.pdf", taken)).toBe("a_2.pdf");
    expect(uniqueName("a.pdf", taken)).toBe("a_3.pdf");
  });

  it("확장자가 없어도 동작한다", () => {
    const taken = new Set<string>(["a"]);
    expect(uniqueName("a", taken)).toBe("a_2");
  });
});
