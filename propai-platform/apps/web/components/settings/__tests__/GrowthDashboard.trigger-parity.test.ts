/**
 * ★프론트 쪽 **생존 락** — 발화 축 라벨표가 실재하고 비어 있지 않은가.
 *
 * ## ★언어 간 대조는 여기서 하지 않는다 (2026-08-28 자기 감사)
 *
 * 이 파일은 처음에 **정규식으로 `analyzer.py` 를 긁어** 백엔드와 대조했다. 그런데 그
 * 정규식은 «파이썬 dict 표기법» 을 **내가 다시 구현한 것**이었고, 다시 구현한 것은 틀렸다:
 *
 *     _LATENCY_TRIGGER_LABELS = {"ratio": …, "absolute": …, 'trend': "추세"}
 *                                                           ↑ 세 번째만 작은따옴표
 *
 * 키 두 개는 여전히 추출되어 **생존 가드(>=2)를 통과**하고, 세 번째만 조용히 사라져
 * **전수 일치가 「참」이 된다** — 화면에는 `trend` 가 **영문 raw** 로 뜨는데 락은 초록이었다(실측).
 *
 * ★동료 세션이 같은 날 남긴 교훈과 같은 형태다:
 *   ***"내 락이 태우는 것이 프로덕션 코드인가, 복제본인가?"***
 *
 * → **판정은 파서로.** 언어 간 대조는 `ast` 로 진짜 파싱하는
 *   **`apps/api/tests/test_latency_trigger_label_parity.py` 가 권위를 갖는다**(백엔드 CI 필수 잡).
 *   여기서는 **`.tsx` 가 스스로 답할 수 있는 것만** 태운다 — 약한 중복 락을 남기면
 *   그것이 초록인 채로 진짜 계약이 깨질 수 있다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = readFileSync(join(__dirname, "..", "GrowthDashboard.tsx"), "utf-8");

/** 객체 리터럴 키 — **세 표기를 모두** 받는다(`"k":` · `'k':` · `k:`). */
const TS_KEY = /^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_$][\w$]*))\s*:/gm;

function labelKeys(): string[] {
  const m = SRC.match(/const LATENCY_TRIGGER_LABELS: Record<string, string> = \{([\s\S]*?)\};/);
  if (!m) throw new Error("★LATENCY_TRIGGER_LABELS 를 못 찾았다 — 조회기 사망");
  return [...m[1].matchAll(TS_KEY)].map((x) => x[1] ?? x[2] ?? x[3]);
}

describe("★프론트 발화 축 라벨표 — 생존", () => {
  it("라벨표가 실재하고 비어 있지 않다(공허한 초록 방지)", () => {
    expect(labelKeys().length).toBeGreaterThanOrEqual(2);
  });

  it("★라벨표가 **실제로 렌더에 쓰인다** — 선언만 하고 소비처 0 이면 장식이다", () => {
    // 선언 줄을 제외하고도 참조가 남아야 한다.
    const uses = SRC.split("\n").filter(
      (l) => l.includes("LATENCY_TRIGGER_LABELS") && !l.includes("const LATENCY_TRIGGER_LABELS"),
    );
    expect(uses.length, "라벨표가 어디에서도 안 쓰인다").toBeGreaterThanOrEqual(1);
  });

  it("★언어 간 대조의 권위 락이 **실재한다** — 이 파일이 그것을 대신하지 않는다", () => {
    // 그 파일이 지워지면 계약이 무잠금이 되는데, 여기 주석만 남아 「잠겼다」고 오도한다.
    const authoritative = join(
      __dirname, "..", "..", "..", "..", "api", "tests", "test_latency_trigger_label_parity.py",
    );
    expect(() => readFileSync(authoritative, "utf-8")).not.toThrow();
  });
});
