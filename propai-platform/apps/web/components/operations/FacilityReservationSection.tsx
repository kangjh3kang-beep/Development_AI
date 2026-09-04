"use client";

/**
 * FacilityReservationSection — "공유시설 예약" 접힘 섹션(배선 캠페인 3차).
 *
 * 배경: 배선설계도 P2 트리아지(_workspace/TRIAGE_wiring_p2_2026-07-11.md) ② 프론트 배선
 * 후보 중 facilities(routers/facility_reservations.py, POST /api/v1/facilities/reserve·
 * /cancel)는 공유시설(커뮤니티 라운지·GX룸 등) 예약/취소 비관적 락 로직이 이미 완성돼
 * 있는데 화면이 없어 아무도 호출하지 못했다.
 *
 * ★TenantWorkspaceClient는 프로젝트 스코프 라우트(/projects/[id]/...)가 아니라 전역
 * "/tenant" 페이지라 useProjectContextStore SSOT의 "현재 프로젝트" 개념이 없다. 그래서
 * 이 컴포넌트는 부모가 이미 GET /projects로 조회해둔 프로젝트 목록을 그대로 넘겨받아
 * (중복 API 호출 없음) 사용자가 직접 예약 대상 프로젝트를 고르게 한다(무날조 — 프리필 없음).
 *
 * SSOT 커밋 없음: 시설 예약은 프로젝트 물리량(면적·용적률 등)과 무관한 운영 이벤트이므로
 * useProjectContextStore에 되먹임하지 않는다. 기본 접힘(AdvancedDrawer).
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input, Select } from "@propai/ui";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { apiClient } from "@/lib/api-client";
import {
  facilityReserveInitialValues,
  buildFacilityReserveBody,
  buildFacilityCancelBody,
} from "@/lib/workspace-extended-panels";
import { extractApiErrorMessage } from "@/lib/esg-extended-panels";
import type { Locale } from "@/i18n/config";

type ReservationResponse = {
  id: string;
  facility_name: string;
  status: string;
  start_time: string;
  end_time: string;
  reserved_by: string;
};


/**
 * ★로케일 라벨 — 종전에는 **전부 한국어 하드코딩**이라 `/en`·`/zh-CN` 사용자에게도
 *   한국어가 그대로 나갔다(실측 2026-08-16: `시설명(예: 커뮤니티 라운지)` 등).
 *   구조는 형제인 `TenantWorkspaceClient` 의 `Record<Locale, Labels>` 관례를 그대로 따른다
 *   (새 규약을 발명하지 않는다).
 */
type Labels = {
  drawerLabel: string;
  projectSelectLabel: string;
  facilityPlaceholder: string;
  notePlaceholder: string;
  cancelIdPlaceholder: string;
  reserveAction: string;
  reservePending: string;
  cancelAction: string;
  cancelPending: string;
  errorTitle: string;
  errorDescription: string;
  retryAction: string;
  authError: string;
  missingProject: string;
  missingFields: string;
  missingReservationId: string;
  reservationIdLabel: string;
  emptyHint: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    drawerLabel: "공유시설 예약",
    projectSelectLabel: "예약 대상 프로젝트",
    facilityPlaceholder: "시설명(예: 커뮤니티 라운지)",
    notePlaceholder: "메모(선택)",
    cancelIdPlaceholder: "취소할 예약 ID",
    reserveAction: "예약 생성",
    reservePending: "예약 중...",
    cancelAction: "예약 취소",
    cancelPending: "취소 중...",
    errorTitle: "공유시설 예약 오류",
    errorDescription: "입력값을 확인한 뒤 다시 시도하세요.",
    retryAction: "다시 시도",
    authError: "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.",
    missingProject: "예약할 프로젝트를 선택하세요.",
    missingFields: "시설명·시작·종료 시각을 모두 입력하세요.",
    missingReservationId: "취소할 예약 ID를 입력하세요.",
    reservationIdLabel: "예약 ID",
    emptyHint: "프로젝트를 선택하고 예약을 생성하면 결과가 표시됩니다.",
  },
  en: {
    drawerLabel: "Shared facility reservation",
    projectSelectLabel: "Project to reserve for",
    facilityPlaceholder: "Facility name (e.g. community lounge)",
    notePlaceholder: "Note (optional)",
    cancelIdPlaceholder: "Reservation ID to cancel",
    reserveAction: "Create reservation",
    reservePending: "Reserving...",
    cancelAction: "Cancel reservation",
    cancelPending: "Cancelling...",
    errorTitle: "Facility reservation error",
    errorDescription: "Check the inputs and try again.",
    retryAction: "Try again",
    authError: "API authentication is required for live workspace calls.",
    missingProject: "Select a project to reserve for.",
    missingFields: "Enter the facility name and both start and end times.",
    missingReservationId: "Enter the reservation ID to cancel.",
    reservationIdLabel: "Reservation ID",
    emptyHint: "Select a project and create a reservation to see the result here.",
  },
  "zh-CN": {
    drawerLabel: "共享设施预约",
    projectSelectLabel: "预约对象项目",
    facilityPlaceholder: "设施名称（例：社区休息室）",
    notePlaceholder: "备注（可选）",
    cancelIdPlaceholder: "要取消的预约 ID",
    reserveAction: "创建预约",
    reservePending: "预约中...",
    cancelAction: "取消预约",
    cancelPending: "取消中...",
    errorTitle: "共享设施预约错误",
    errorDescription: "请检查输入后重试。",
    retryAction: "重试",
    authError: "实时工作区调用需要 API 认证。",
    missingProject: "请选择要预约的项目。",
    missingFields: "请填写设施名称与开始·结束时间。",
    missingReservationId: "请输入要取消的预约 ID。",
    reservationIdLabel: "预约 ID",
    emptyHint: "选择项目并创建预约后，结果将显示在这里。",
  },
};

export function FacilityReservationSection({
  projects,
  canUseLiveApi,
  locale,
}: {
  projects: { id: string; name: string }[];
  canUseLiveApi: boolean;
  locale: Locale;
}) {
  const labels = LABELS[locale] ?? LABELS.ko;
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [values, setValues] = useState(() => facilityReserveInitialValues());
  const [reservationId, setReservationId] = useState("");
  const [result, setResult] = useState<ReservationResponse | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"reserve" | "cancel" | null>(null);

  // ★projects는 부모(TenantWorkspaceClient)의 GET /projects가 비동기로 채운다 — 최초
  // 렌더 시점엔 빈 배열일 수 있어(useState 초기화는 1회뿐) 목록이 도착한 뒤 아직
  // 아무것도 선택되지 않았다면 첫 프로젝트를 기본 선택한다(DigitalTwinControlTowerWorkspaceClient
  // 의 동일 패턴 재사용).
  useEffect(() => {
    if (!projectId && projects.length > 0) {
      setProjectId(projects[0].id);
    }
  }, [projectId, projects]);

  const authErrorMessage = labels.authError;

  const reserve = useCallback(async () => {
    setError("");
    if (!projectId) {
      setError(labels.missingProject);
      return;
    }
    if (!values.facilityName.trim() || !values.startTime || !values.endTime) {
      setError(labels.missingFields);
      return;
    }
    setPending("reserve");
    try {
      const response = await apiClient.post<ReservationResponse>("/facilities/reserve", {
        useMock: false,
        body: buildFacilityReserveBody(values, { projectId }),
      });
      setResult(response);
    } catch (err) {
      setError(extractApiErrorMessage(err, authErrorMessage));
    } finally {
      setPending(null);
    }
  }, [projectId, values]);

  const cancel = useCallback(async () => {
    setError("");
    if (!reservationId.trim()) {
      setError(labels.missingReservationId);
      return;
    }
    setPending("cancel");
    try {
      const response = await apiClient.post<ReservationResponse>("/facilities/cancel", {
        useMock: false,
        body: buildFacilityCancelBody(reservationId),
      });
      setResult(response);
    } catch (err) {
      setError(extractApiErrorMessage(err, authErrorMessage));
    } finally {
      setPending(null);
    }
  }, [reservationId]);

  async function handleReserveSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await reserve();
  }

  async function handleCancelSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await cancel();
  }

  return (
    <AdvancedDrawer label={labels.drawerLabel}>
      <Card>
        <CardContent className="p-6">
          <p className="label-caps text-[var(--text-tertiary)]">
            공유시설 예약 생성
          </p>
          <form className="mt-4 grid gap-3" onSubmit={handleReserveSubmit}>
            <Select
              value={projectId}
              onValueChange={setProjectId}
              options={projects.map((p) => ({ label: p.name, value: p.id }))}
              className="h-11 rounded-[var(--radius-md)] border-[var(--line)] bg-[var(--surface)]"
            />
            <Input
              value={values.facilityName}
              onChange={(e) => setValues((prev) => ({ ...prev, facilityName: e.target.value }))}
              placeholder={labels.facilityPlaceholder}
            />
            <div className="grid gap-3 md:grid-cols-2">
              <input
                type="datetime-local"
                value={values.startTime}
                onChange={(e) => setValues((prev) => ({ ...prev, startTime: e.target.value }))}
                className="h-11 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
              <input
                type="datetime-local"
                value={values.endTime}
                onChange={(e) => setValues((prev) => ({ ...prev, endTime: e.target.value }))}
                className="h-11 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
            </div>
            <Input
              value={values.notes}
              onChange={(e) => setValues((prev) => ({ ...prev, notes: e.target.value }))}
              placeholder={labels.notePlaceholder}
            />
            <Button type="submit" disabled={!canUseLiveApi || pending === "reserve"}>
              {pending === "reserve" ? labels.reservePending : labels.reserveAction}
            </Button>
          </form>

          <form className="mt-4 flex gap-2" onSubmit={handleCancelSubmit}>
            <Input
              value={reservationId}
              onChange={(e) => setReservationId(e.target.value)}
              placeholder={labels.cancelIdPlaceholder}
            />
            <Button
              type="submit"
              variant="secondary"
              disabled={!canUseLiveApi || pending === "cancel"}
            >
              {pending === "cancel" ? labels.cancelPending : labels.cancelAction}
            </Button>
          </form>

          {error ? (
            <div className="mt-4">
              <WorkspaceQueryErrorCard
                title={labels.errorTitle}
                description={labels.errorDescription}
                message={error}
                actionLabel={labels.retryAction}
                onRetry={pending === "cancel" ? cancel : reserve}
              />
            </div>
          ) : null}

          {result ? (
            <div className="mt-6 grid gap-2 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm">
              <p className="font-semibold text-[var(--text-primary)]">
                {result.facility_name} — {result.status}
              </p>
              <p className="text-[var(--text-secondary)]">
                {result.start_time} ~ {result.end_time}
              </p>
              <p className="text-xs text-[var(--text-tertiary)]">{labels.reservationIdLabel}: {result.id}</p>
            </div>
          ) : !error ? (
            <div className="mt-6 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.emptyHint}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </AdvancedDrawer>
  );
}
