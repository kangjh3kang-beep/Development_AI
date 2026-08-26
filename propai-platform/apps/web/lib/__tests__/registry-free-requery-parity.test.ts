/**
 * ★계약 락 — 화면이 말하는 **무과금 기간**이 백엔드 캐시 TTL 과 같은가.
 *
 * ## 왜 필요한가 (2026-08-25 실측)
 *
 * 등기 화면과 경매 화면이 둘 다 *"동일 물건 재조회 무료"* 라고 **조건 없이** 말했다.
 * 그런데 무과금은 **성공한 분석이 캐시에 살아 있는 동안만** 참이다:
 *
 *  · `_ANALYZE_DB_TTL = 7 * 24 * 3600` — DB 공유 캐시 7일
 *  · `_cache_success()` — **성공만** 저장한다. 그때 실패했던 건은 캐시가 없다
 *  · 캐시 미스면 `RegistryService.get_one()` 이 다시 돌아 **발급이 다시 나간다**
 *    (사용자 청구는 `analysis_charged` 가 막지만 **벤더 선불 잔액은 탄다** —
 *     돈은 축이 둘이고, 한쪽만 막고 "무과금"이라 쓰면 다른 쪽이 샌다)
 *
 * 즉 기간 없는 "무료"는 **8일째에 거짓이 된다.** 문구만 고치면 다음에 또 갈라지므로
 * 상수로 묶고 여기서 백엔드 값과 대조한다.
 *
 * ★파서 주의: 고정 길이 창으로 자르지 않는다(옆 상수를 읽어 없는 불일치를 만든다).
 *   `_ANALYZE_DB_TTL` **선언 줄**만 앵커로 집고, 추출이 비면 시끄럽게 실패시킨다.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { FREE_REQUERY_DAYS } from "../registry-analyze";
import { __stripCommentsForScan } from "../source-invariant";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = resolve(HERE, "../..");
const SERVICE = resolve(WEB_ROOT, "../api/app/services/registry/registry_analysis_service.py");

/** `_ANALYZE_DB_TTL = 7 * 24 * 3600` 의 **일수**를 뽑는다(선언 줄 앵커 · 주석 제외). */
function backendCacheDays(): number {
  const src = readFileSync(SERVICE, "utf-8");
  const line = src
    .split("\n")
    .map((l) => l.replace(/(^|\s)#.*$/, "$1"))     // 주석의 예시값이 잡히지 않게
    .find((l) => /^_ANALYZE_DB_TTL\s*=/.test(l.trim()));
  expect(line, "_ANALYZE_DB_TTL 선언을 찾지 못했다 — 파서가 낡았다").toBeTruthy();
  const m = (line as string).match(/=\s*(\d+)\s*\*\s*(\d+)\s*\*\s*(\d+)/);
  expect(m, `_ANALYZE_DB_TTL 의 값 형태가 바뀌었다: ${line}`).toBeTruthy();
  const [, a, b, c] = m as RegExpMatchArray;
  const seconds = Number(a) * Number(b) * Number(c);
  expect(seconds, "TTL 초 계산이 0이다 — 추출 실패").toBeGreaterThan(0);
  return seconds / 86400;
}

describe("★계약 — 화면의 무과금 기간 ≡ 백엔드 캐시 TTL", () => {
  it("추출이 비어 있지 않다(공허한 초록 방지)", () => {
    // ★단언 **앞에** 둔다 — 파서가 깨져 0 이 되면 아래 비교가 공허하게 참이 될 수 있다.
    expect(backendCacheDays()).toBeGreaterThan(0);
    expect(FREE_REQUERY_DAYS).toBeGreaterThan(0);
  });

  it("두 값이 같다 — 갈리면 화면이 거짓 기간을 말한다", () => {
    expect(FREE_REQUERY_DAYS).toBe(backendCacheDays());
  });

  it("★화면 문구가 **조건 없는 '재조회 무료'** 를 말하지 않는다", () => {
    // 기간이 빠진 "무료"는 캐시 만료 뒤 거짓이 된다. 실행되는 줄만 본다(주석 제외).
    const targets = [
      resolve(WEB_ROOT, "components/operations/RegistryAnalysisWorkspaceClient.tsx"),
      resolve(WEB_ROOT, "components/auction/AuctionWorkspace.tsx"),
    ];
    let checked = 0;
    for (const f of targets) {
      // ★주석은 **공용 헬퍼**로 걷어낸다(손으로 짜면 뚫린다 — 첫 판이 JSX 주석
      //   `{/* … 재조회·재과금 없음 … */}` 을 집어 정상 주석을 위반으로 신고했다.
      //   CLAUDE.md §A-3 이 지목한 바로 그 함정이고, 헬퍼는 이미 옆에 있었다 — §29).
      const live = __stripCommentsForScan(readFileSync(f, "utf-8"), f)
        .split("\n")
        .filter((l) => {
          const t = l.trim();
          return t && !t.startsWith("//") && !t.startsWith("*");
        });
      // 대조군: 그 문구가 있는 줄이 실제로 존재해야 이 검사가 의미를 가진다.
      const claim = live.filter((l) => l.includes("재조회"));
      expect(claim.length, `${f}: '재조회' 문구를 못 찾았다 — 검사가 대상을 잃었다`).toBeGreaterThan(0);
      for (const l of claim) {
        // ★기간을 **상수 참조**로 쓰는 편이 리터럴보다 낫다(백엔드와 갈리지 않는다).
        //   둘 다 허용한다 — 리터럴만 허용하면 이 가드가 더 나은 설계를 막는다
        //   (가드의 위양성도 결함이다 · 규율 §A-6). 실제로 첫 판이 그 실수를 했다.
        const hasPeriod = /\d+\s*일/.test(l) || /FREE_REQUERY_DAYS\s*\}?\s*일/.test(l);
        expect(
          hasPeriod,
          `${f}: 기간 없는 무과금 주장 — "${l.trim().slice(0, 120)}"`,
        ).toBe(true);
      }
      checked += 1;
    }
    expect(checked, "검사한 파일이 0개다").toBe(targets.length);
  });
});
