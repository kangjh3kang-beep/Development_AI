/**
 * `RegistryAnalysisWorkspaceClient` 가 필지 행에 **지번을 파생해 넣고 pnu 를 담는지** 잠근다.
 *
 * 【실장애 2026-08-18 · 사용자 스크린샷】
 * `/ko/registry-analysis` 의 "프로젝트 필지 (77)" 이 **77행 전부 "경기도 오산시 내삼미동"** 이었다.
 * #673 이 같은 결함을 고치며 형제를 스윕했으나 **이 화면을 놓쳤다**(사람이 센 목록이 상한이 됐다).
 *
 * 【왜 파생형 전수 락을 안 쓰나 — 정직 고지】
 * `parcels.map(` 으로 전수 파생을 시도했더니 **지도 레이어·요청본문 조립**까지 잡혀 위양성이 3~4건
 * 남았다(A6: 가드의 위양성도 결함이다). 축을 두 번 좁혀도 `SiteAnalysisDetail`(이미 jibun 우선 처리)
 * 같은 정상 코드가 계속 걸려서 **폐기했다.** 대신 실제 결함이 난 표면을 직접 태운다.
 * → 전수 락이 필요하면 "주소가 지번 칸으로 들어가는" 신호를 **기계적으로** 가릴 방법이 먼저 있어야 한다.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { __stripCommentsForScan } from "@/lib/source-invariant";

const F = join(__dirname, "..", "..", "components", "operations", "RegistryAnalysisWorkspaceClient.tsx");
const src = __stripCommentsForScan(readFileSync(F, "utf8"), F);

describe("등기분석 워크스페이스 — 필지 행 지번·PNU", () => {
  it("전제: 대상 파일을 읽었고 필지를 행으로 펼친다(공허한 초록 방지)", () => {
    expect(src.length, "파일을 못 읽었다").toBeGreaterThan(500);
    expect(/parcels\s*\.\s*map\s*\(/.test(src), "필지를 행으로 펼치지 않는다 — 전제가 바뀌었다").toBe(true);
  });

  it("★주소를 그대로 쓰지 않고 지번을 파생한다", () => {
    // 동 단위 주소만 오면 전 행이 같은 글자가 된다. 헬퍼는 PNU 에서 지번을 파생하되
    // 만들 수 없으면 주소를 그대로 둔다(무날조).
    expect(
      /parcelDisplayAddress\s*\(/.test(src),
      "지번 파생을 안 쓴다 — 동 단위 주소면 전 행이 같은 글자가 된다",
    ).toBe(true);
  });

  it("★★행에 pnu 를 담는다 — 안 담으면 '대표값 누출 차단'이 무력화된다", () => {
    // run() 이 `row?.pnu` 를 읽어 개별 필지 조회를 만든다. 행에 pnu 가 없으면 항상 undefined 라
    // 대표 PNU 로 떨어지고, 그 방어를 설명하는 주석만 남고 동작은 사라진다.
    expect(
      /\bpnu:\s*pnu\s*\|\|\s*null/.test(src),
      "mk() 가 pnu 를 담지 않는다 — 개별 필지 조회가 대표값으로 떨어진다",
    ).toBe(true);
    expect(/row\?\.\s*pnu/.test(src), "전제: run() 이 row.pnu 를 소비한다").toBe(true);
  });
});
