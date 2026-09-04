/**
 * 운영 화면 정직 계약 — 수집원이 없는데 "실시간·연결됨"이라 말하지 않는다.
 *
 * ★왜 (2026-08-16 프로덕션 실측):
 *   백엔드는 성격이 전혀 다른 두 프로젝트에 **바이트 단위로 같은 값**을 돌려줬다
 *   (강남 상업지 vs 147,074㎡ 임야 → 둘 다 입주율 92.5 · IoT 센서 45/48).
 *   그런데 이 화면은 **뜨지 않았다** — `TypeError: kpis.map is not a function`
 *   (백엔드가 dict 를 주는데 프론트가 배열을 가정). 즉 **고장이 거짓말을 가리고 있었다.**
 *
 *   ★그래서 크래시만 고치면 **그때부터** 거짓 지표가 사용자에게 보인다. 이 락은 그 역전을
 *   막는다 — 배열 접지(크래시 방지)와 문구 정직화를 **함께** 잠근다.
 *
 * ★소스 검사는 주석에 뚫린다(이 저장소에서 배선 락 38개가 그렇게 관통됐다).
 *   공용 `stripBlockComments` 를 경유한다 — 위 주석의 "실시간"·"92.5" 가 이 테스트를
 *   스스로 빨갛게 만들면 위양성이다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const REL = "app/[locale]/(dashboard)/projects/[id]/operations/page.tsx";
const FILE = join(process.cwd(), REL);

function code(): string {
  return __stripCommentsForScan(readFileSync(FILE, "utf8"), REL);
}

describe("운영 화면 정직 계약", () => {
  it("★검사가 공허하지 않다 — 대상 파일이 실제로 이 엔드포인트를 부른다", () => {
    // 이 단언이 없으면 파일이 통째로 비어도 아래 '위반 0'이 참이 된다.
    const src = code();
    expect(src.length).toBeGreaterThan(500);
    expect(src).toContain("operations/status");
  });

  it("★수집원이 없는데 실시간·연결됨을 단정하지 않는다", () => {
    const src = code();
    for (const claim of [
      "오케스트레이터",          // "…와 연결된 스마트 센서 네트워크"
      "실시간 스트림",
      "LIVE STREAM",
      "Real-time Performance",
      "NOMINAL",                 // 값과 무관하게 박혀 있던 상태 칩
    ]) {
      expect(src, `거짓 단정이 되돌아왔다: ${claim}`).not.toContain(claim);
    }
  });

  it("★배열 접지 — 응답 형태가 어긋나도 화면이 죽지 않는다", () => {
    const src = code();
    // 종전 `data?.kpis.map` 은 옵셔널 체인이 `data` 에서만 멈춰 `undefined.map` 이 됐다.
    for (const key of ["kpis", "maintenance", "sensors"]) {
      expect(src, `${key} 가 빈 배열로 접지되지 않았다`).toContain(`(data?.${key} ?? []).map(`);
      expect(src, `${key} 에 접지 없는 .map 이 남아 있다`).not.toContain(`data?.${key}.map(`);
    }
  });

  it("★수집원 부재를 화면에 고지한다 — 빈 화면은 고장으로 읽힌다", () => {
    const src = code();
    expect(src).toContain('data?.available === false');
    expect(src).toContain("operations-unavailable-notice");
  });
});
