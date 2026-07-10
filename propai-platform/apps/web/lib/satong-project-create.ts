"use client";

import { apiClient } from "@/lib/api-client";
import { useProjectStore, type Project } from "@/store/useProjectStore";
import { deriveProjectNameFromParcels } from "@/components/precheck/satong-project-connect";
import type { SatongSelectionParcel } from "@/components/precheck/satong-map-selection";

/** 선택 필지로 프로젝트 생성(로컬 레코드 + 백엔드 best-effort). projects/new 페이지의
 *  생성 체인(addProject → POST /projects → 과금 best-effort)을 지도용으로 축약한 공용 유틸.
 *  반환 id는 백엔드 UUID 우선, 실패 시 로컬 id(오프라인에서도 진행 — 기준선과 동일).
 *  ※ projects/new 페이지는 수정하지 않는다 — 두 경로의 수렴은 후속 과제. */
export async function createProjectFromParcels(
  parcels: SatongSelectionParcel[],
): Promise<{ id: string; name: string; address: string } | null> {
  const name = deriveProjectNameFromParcels(parcels);
  if (!name) return null;

  const first = parcels[0];
  const address = first.address;
  const pnu = first.pnu ?? "";
  const areaSqm = parcels.reduce((sum, parcel) => sum + (parcel.areaSqm ?? 0), 0);

  const localId = useProjectStore.getState().addProject({
    name,
    address,
    pnu,
    area: areaSqm > 0 ? String(areaSqm) : "0",
    type: "mixed",
    parcelCount: parcels.length > 1 ? parcels.length : undefined,
  });

  // 서비스 사용료: 프로젝트 생성 1건 차감(로그인 구독자, best-effort — 실패해도 진행).
  void apiClient
    .post("/billing/charge", { body: { action: "project_create" }, useMock: false })
    .catch(() => { /* 비로그인/실패 무시 */ });

  // 백엔드 영속화: 실패해도 로컬 id로 계속 진행(오프라인 허용 — 기준선과 동일).
  let backendId = "";
  try {
    const res = await apiClient.post<{ id: string }>("/projects", {
      body: {
        name,
        address,
        ...(areaSqm > 0 ? { total_area_sqm: areaSqm } : {}),
      },
      useMock: false,
    });
    backendId = res?.id || "";
  } catch {
    backendId = "";
  }

  if (backendId && backendId !== localId) {
    // 옵션 value(로컬 레코드)와 connectTarget(반환 id)이 같은 id를 공유하도록 정합 —
    // 불일치 시 셀렉트가 첫 옵션('새 프로젝트')으로 보이고, 재선택 시 UUID→short 전환 와이프·
    // restoreSnapshot _isUuid 스킵이 생긴다.
    useProjectStore.getState().updateProject(localId, { id: backendId } as Partial<Project>);
  }

  const id = backendId || localId;
  return { id, name, address };
}
