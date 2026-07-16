/**
 * NATIONAL_FAR_LIMITS 프론트 그림자표 parity 가드(WP-U1e) — 백엔드 원본 라이브 대조.
 *
 * 배경: zoning-ssot.ts의 NATIONAL_FAR_LIMITS_PCT는 백엔드
 * far_incentive_calculator.NATIONAL_FAR_LIMITS의 손사본으로, "백엔드 갱신 시 이 맵도
 * 함께 갱신(정합)" 불변식이 주석으로만 존재했다(침묵 드리프트 사각). 백엔드 내부는
 * test_far_hygiene_u1d.py ⑤가 NATIONAL_FAR_LIMITS ↔ ZONE_LIMITS(auto_zoning SSOT)를
 * 이미 잠갔으므로, 이 테스트가 프론트 사본 ↔ 백엔드 NATIONAL_FAR_LIMITS를 잠그면
 * 프론트는 법정 SSOT까지 이행적으로 정합된다(3중 그림자표 재발 단선 완성).
 *
 * 방식(라이브 파싱, 테스트 내 스냅샷 사본 아님): monorepo CI(ci.yml frontend-tests)는
 * 전체 체크아웃에서 vitest를 돌리므로 백엔드 .py 원본을 직접 읽어 대조한다 —
 * 테스트 내 명시 사본(4번째 표)은 백엔드 '단독' 변경을 잡지 못하고 자기 자신이
 * 또 하나의 드리프트원이 된다. 코드 생성/단일 JSON 소스는 과대설계로 배제(최소·실효).
 * 파싱 실패는 침묵 통과가 아니라 시끄러운 실패가 되도록 3중 가드(블록 존재·건수 하한·
 * 절대값 앵커)를 둔다.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, it, expect } from "vitest";
import { NATIONAL_FAR_LIMITS_PCT } from "@/lib/zoning-ssot";

/** 백엔드 원본(.py) 경로 — cwd 기준 상향 탐색(jsdom에선 import.meta.url이 file 스킴이
 *  아니라 사용 불가). apps/web·propai-platform·저장소 루트 어디서 실행해도 찾는다. */
function resolveBackendFile(): string {
  const suffix = "api/app/services/zoning/far_incentive_calculator.py";
  let dir = process.cwd();
  for (let i = 0; i < 6; i++) {
    for (const cand of [
      path.join(dir, "apps", suffix),
      path.join(dir, "propai-platform", "apps", suffix),
    ]) {
      if (existsSync(cand)) return cand;
    }
    dir = path.dirname(dir);
  }
  throw new Error(
    `백엔드 far_incentive_calculator.py를 찾지 못함(cwd=${process.cwd()}) — ` +
      "monorepo 전체 체크아웃에서 실행해야 하는 parity 가드입니다",
  );
}

const BACKEND_FILE = resolveBackendFile();

/** 백엔드 far_incentive_calculator.py에서 NATIONAL_FAR_LIMITS dict를 파싱한다. */
function parseBackendNationalFarLimits(): Record<string, number> {
  const src = readFileSync(BACKEND_FILE, "utf-8");
  // dict 블록만 슬라이스(다른 dict의 항목 오염 방지) — 선언부터 첫 닫는 중괄호까지.
  const blockMatch = src.match(
    /NATIONAL_FAR_LIMITS:\s*dict\[str,\s*float\]\s*=\s*\{([\s\S]*?)\n\}/,
  );
  expect(
    blockMatch,
    "백엔드 NATIONAL_FAR_LIMITS 선언 블록을 찾지 못함 — 파일 이동/개명 시 이 가드의 경로·패턴도 함께 갱신 필요",
  ).not.toBeNull();
  const entries: Record<string, number> = {};
  for (const m of blockMatch![1].matchAll(/"([^"]+)":\s*(\d+(?:\.\d+)?)\s*,/g)) {
    entries[m[1]] = Number(m[2]);
  }
  return entries;
}

describe("NATIONAL_FAR_LIMITS_PCT ↔ 백엔드 NATIONAL_FAR_LIMITS parity(그림자표 드리프트 가드)", () => {
  const backend = parseBackendNationalFarLimits();

  it("파싱 건전성: 20건 이상 + 절대값 앵커(제2종일반주거 250·자연녹지 100)", () => {
    // 파서가 엉뚱한 블록을 읽거나 포맷 변경으로 일부만 잡으면 여기서 시끄럽게 깨진다.
    expect(Object.keys(backend).length).toBeGreaterThanOrEqual(20);
    expect(backend["제2종일반주거지역"]).toBe(250);
    expect(backend["자연녹지지역"]).toBe(100);
  });

  it("키 집합 완전 일치(한쪽에만 zone 추가/삭제 시 즉시 실패)", () => {
    const frontKeys = Object.keys(NATIONAL_FAR_LIMITS_PCT).sort();
    const backKeys = Object.keys(backend).sort();
    expect(frontKeys).toEqual(backKeys);
  });

  it("전 zone max_far 값 완전 일치(값 드리프트 시 어느 zone인지 명시 실패)", () => {
    const drift = Object.keys(backend)
      .filter((zone) => NATIONAL_FAR_LIMITS_PCT[zone] !== backend[zone])
      .map(
        (zone) =>
          `${zone}: 프론트=${NATIONAL_FAR_LIMITS_PCT[zone]} vs 백엔드=${backend[zone]}`,
      );
    expect(drift, `그림자표 값 드리프트: ${drift.join(", ")}`).toEqual([]);
  });
});
