/**
 * ★계약 락 — 지연 **발화 축 라벨**이 백엔드와 1:1 인가.
 *
 * ## 왜 이 파일이 따로 필요한가 (2026-08-28 · 적대 리뷰가 실증)
 *
 * `GrowthDashboard.tsx` 주석이 *"양쪽을 파생시켜 대조하는 락이 잡는다"* 라고 **단언했는데
 * 그 락이 없었다.** 리뷰가 반증을 실행했다 — 백엔드에 세 번째 축 `trend` 를 생산자와
 * `_LATENCY_TRIGGER_LABELS` 양쪽에 추가하고 프론트만 안 고쳤더니 **프론트 89건이 전부 초록**
 * 이었고, 화면에는 `trend` 가 **영문 raw** 로 떴다.
 *
 * CLAUDE.md §C-11 *「면역을 거짓 주장하지 마라」* · 메모리 «"1:1 일치" 주석에는 락이 없다».
 *
 * ## 어떻게 잠그는가
 *
 * **양쪽을 파일에서 파생**한다(손 목록을 쓰면 그 목록이 곧 상한이 된다).
 * ★추출이 비면 **시끄럽게 실패**한다 — 정규식이 죽으면 "0 == 0" 으로 **공허하게 초록**이 된다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const WEB = join(__dirname, "..", "..", "..");
const API = join(WEB, "..", "api");

function backendLabelKeys(): string[] {
  const src = readFileSync(join(API, "app/services/growth/analyzer.py"), "utf-8");
  const block = src.match(/_LATENCY_TRIGGER_LABELS\s*=\s*\{([\s\S]*?)\}/);
  if (!block) throw new Error("★백엔드 _LATENCY_TRIGGER_LABELS 를 못 찾았다 — 조회기 사망(이름이 바뀌었나?)");
  return [...block[1].matchAll(/"([^"]+)"\s*:/g)].map((m) => m[1]);
}

/** 백엔드가 **실제로 생산하는** 축 이름 — 라벨표가 아니라 `triggers = [...]` 에서 뽑는다. */
function backendProducedAxes(): string[] {
  const src = readFileSync(join(API, "app/services/growth/analyzer.py"), "utf-8");
  const block = src.match(/triggers\s*=\s*\[n for n, v in \(([\s\S]*?)\) if v\]/);
  if (!block) throw new Error("★백엔드 triggers 생산부를 못 찾았다 — 조회기 사망");
  return [...block[1].matchAll(/\("([^"]+)"\s*,/g)].map((m) => m[1]);
}

function frontendLabelKeys(): string[] {
  const src = readFileSync(join(WEB, "components/settings/GrowthDashboard.tsx"), "utf-8");
  const block = src.match(/const LATENCY_TRIGGER_LABELS: Record<string, string> = \{([\s\S]*?)\};/);
  if (!block) throw new Error("★프론트 LATENCY_TRIGGER_LABELS 를 못 찾았다 — 조회기 사망");
  return [...block[1].matchAll(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/gm)].map((m) => m[1]);
}

describe("★계약 — 지연 발화 축 라벨이 백엔드와 1:1", () => {
  it("★추출이 비지 않는다(공허한 초록 방지) — 단언 **앞에** 둔다", () => {
    // 정규식이 죽으면 아래 집합 비교가 "0 == 0" 으로 공허하게 참이 된다.
    expect(backendLabelKeys().length).toBeGreaterThanOrEqual(2);
    expect(frontendLabelKeys().length).toBeGreaterThanOrEqual(2);
    expect(backendProducedAxes().length).toBeGreaterThanOrEqual(2);
  });

  it("백엔드 라벨표 ↔ 프론트 라벨표가 **전수 일치**", () => {
    expect([...frontendLabelKeys()].sort()).toEqual([...backendLabelKeys()].sort());
  });

  it("★**생산되는 축**이 전부 프론트 라벨을 갖는다 — 라벨표끼리만 맞으면 둘 다 틀릴 수 있다", () => {
    // 전수일치는 「둘 다 없음」과 구별하지 못한다. 생산자를 **세 번째 모집단**으로 태운다.
    const fe = new Set(frontendLabelKeys());
    const missing = backendProducedAxes().filter((a) => !fe.has(a));
    expect(missing, `생산되는데 프론트 라벨이 없는 축(영문 raw 로 샌다): ${missing.join(", ")}`).toEqual([]);
  });
});
