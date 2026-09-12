/**
 * 통합 필지 선택 → 건축개요 **대지면적 자동 산입** 판정.
 *
 * ★2026-08-23 실측 사고를 재현하지 않기 위한 게이트다:
 *   «15.86km 떨어진 6필지가 「통합 5,781㎡」로 묶여 있었다»
 *   (`components/precheck/SatongMapShell.tsx` 주석 · `lib/selection-integrity.ts`).
 *   합계 면적을 **「통합 대지면적」이라 부르기 전에** 그 전제를 검사해야 한다.
 *
 * ★막지 않고 고지한다 — 원거리 묶음은 «후보지 비교」라는 정당한 워크플로우일 수 있다.
 *   그래서 자동 산입만 **보류**하고 사람이 직접 넣을 길은 열어 둔다.
 */
import type { SelectionIntegrity } from "@/lib/selection-integrity";

export type LandAreaIntake = {
  /** 자동 산입할 대지면적(㎡). 보류하면 null. */
  autoLandAreaSqm: number | null;
  /** 자동 산입을 보류한 이유. 산입했으면 null. */
  withheldReason: string | null;
};

/**
 * @param areasSqm 선택 필지들의 면적(㎡)
 * @param integrity `classifySelection` 판정
 */
export function deriveLandAreaIntake(
  areasSqm: readonly (number | null | undefined)[],
  integrity: Pick<SelectionIntegrity, "verdict" | "spreadKm">,
): LandAreaIntake {
  const usable = areasSqm.filter(
    (a): a is number => typeof a === "number" && Number.isFinite(a) && a > 0,
  );
  // ★필지가 없으면 「0㎡」가 아니라 **모름**이다.
  if (usable.length === 0) {
    return { autoLandAreaSqm: null, withheldReason: "선택된 필지에 면적 정보가 없습니다." };
  }
  if (integrity.verdict === "malformed") {
    return {
      autoLandAreaSqm: null,
      withheldReason: "선택 목록에 주소가 아닌 값이 섞여 있어 합계를 대지면적으로 쓰지 않습니다.",
    };
  }
  if (integrity.verdict === "multi_region") {
    const km = integrity.spreadKm;
    // ★거리를 모르면 「0km」라고 쓰지 않는다 — 미상이다.
    const where = km === null ? "서로 다른 지역" : `최대 ${km.toFixed(1)}km 떨어진 지역`;
    return {
      autoLandAreaSqm: null,
      withheldReason: `${where}의 필지가 섞여 있어 합계를 하나의 대지면적으로 보지 않습니다(후보지 비교로 보입니다).`,
    };
  }
  return {
    autoLandAreaSqm: usable.reduce((a, b) => a + b, 0),
    withheldReason: null,
  };
}

/**
 * 선택 필지 합계를 **화면에 뭐라고 부를 것인가**.
 *
 * ★★2026-09-12 — `deriveLandAreaIntake` 는 **새 모달에만** 걸려 있었고, 같은 화면의
 *   접힌 셸 헤더는 여전히 게이트 없이 *"합산 면적 5,781㎡"* 라고 **단정**했다.
 *   그래서 15.86km 떨어진 6필지를 고른 사용자는 **헤더에서 「합산 면적」을 읽으면서**
 *   모달에선 「보류」를 본다 — 한 화면이 **두 가지 서사**를 말한다.
 *   이 PR 이 재현하지 않겠다고 인용한 바로 그 사고(2026-08-23)가 **다른 절반에 살아 있었다.**
 *
 * ★숨기지 않는다 — 사용자가 기대하는 숫자는 그대로 보여 주되 **주장을 고친다.**
 *   숫자를 지우면 «왜 안 보이지»가 되고, 그대로 두면 «하나의 대지»라는 거짓이 남는다.
 *
 * @param totalText 이미 서식된 합계 문자열(서식 규칙은 호출부가 안다)
 */
export function describeSelectionArea(
  totalText: string,
  intake: LandAreaIntake,
): { label: string; withheld: boolean } {
  if (intake.withheldReason === null) return { label: `합산 면적 ${totalText}`, withheld: false };
  // ★보류 사유를 **그대로 싣는다**(무언 보류 금지 — 사유가 없으면 사용자는 진단할 수 없다).
  return { label: `면적 합 ${totalText} · ★${intake.withheldReason}`, withheld: true };
}
