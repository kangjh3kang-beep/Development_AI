"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type EscrowTransactionResponse = {
  id: string;
  project_id: string;
  status: string;
  amount_wei: string;
  on_chain_escrow_id: number | null;
  tx_hash: string | null;
  contract_address: string | null;
  buyer_address: string;
  seller_address: string;
  created_at: string;
};

type OnChainEscrowResponse = {
  on_chain_escrow_id: number;
  payer: string;
  payee: string;
  subcontractor: string;
  total_amount_wei: string;
  remaining_amount_wei: string;
  expires_at: number;
  condition_hash: string;
  status: string;
};

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  contextTitle: string;
  contextHint: string;
  createTitle: string;
  payerLabel: string;
  payeeLabel: string;
  subcontractorLabel: string;
  expiresAtLabel: string;
  conditionHashLabel: string;
  createAction: string;
  nextEscrowTitle: string;
  nextEscrowLabel: string;
  statusLookupTitle: string;
  statusLookupLabel: string;
  loadStatusAction: string;
  escrowResultTitle: string;
  statusLabel: string;
  onChainIdLabel: string;
  txHashLabel: string;
  contractLabel: string;
  buyerLabel: string;
  sellerLabel: string;
  onChainStatusTitle: string;
  totalAmountLabel: string;
  remainingAmountLabel: string;
  missingConditionHashError: string;
  placeholder: string;
  projectFallback: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  nextEscrowLoadErrorTitle: string;
  nextEscrowLoadErrorDetail: string;
  retryAction: string;
};

const EN_LABELS: Labels = {
  heroTitle: "Project blockchain live workspace",
  heroDescription:
    "Create and inspect escrow state for the current project route through the live blockchain API.",
  heroHint:
    "This route uses the project id from the URL, reads the next escrow id, creates an escrow record, and optionally loads on-chain status.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  contextTitle: "Project context",
  contextHint:
    "This project route is bound to a narrower escrow workspace: next-id, create escrow, and status lookup.",
  createTitle: "Create escrow",
  payerLabel: "Payer address",
  payeeLabel: "Payee address",
  subcontractorLabel: "Subcontractor address",
  expiresAtLabel: "Expiry unix timestamp",
  conditionHashLabel: "Condition hash",
  createAction: "Create escrow",
  nextEscrowTitle: "Next escrow id",
  nextEscrowLabel: "Available on-chain id",
  statusLookupTitle: "On-chain status lookup",
  statusLookupLabel: "On-chain escrow id",
  loadStatusAction: "Load escrow status",
  escrowResultTitle: "Created escrow record",
  statusLabel: "Status",
  onChainIdLabel: "On-chain escrow id",
  txHashLabel: "Transaction hash",
  contractLabel: "Contract address",
  buyerLabel: "Buyer address",
  sellerLabel: "Seller address",
  onChainStatusTitle: "On-chain status",
  totalAmountLabel: "Total amount (wei)",
  remainingAmountLabel: "Remaining amount (wei)",
  missingConditionHashError: "A condition hash is required.",
  placeholder:
    "Create or inspect an escrow to validate the blockchain response chain for this project route.",
  projectFallback: "Project metadata could not be loaded from the live API.",
  projectLoadErrorTitle: "Project metadata unavailable",
  projectLoadErrorDetail:
    "The routed project context failed to load from the live API. Retry to restore the escrow route metadata.",
  nextEscrowLoadErrorTitle: "Next escrow id unavailable",
  nextEscrowLoadErrorDetail:
    "The live blockchain service failed to return the next on-chain escrow id. Retry before creating a new escrow.",
  retryAction: "Retry",
};

const KO_LABELS: Labels = {
  heroTitle: "프로젝트 블록체인 라이브 작업 공간",
  heroDescription:
    "에스크로 거래를 생성하고 관리합니다.",
  heroHint:
    "현재 프로젝트 ID를 기반으로 다음 에스크로 ID를 조회하고, 에스크로를 생성하며, 온체인 상태를 확인합니다.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출에 API 인증이 필요합니다.",
  contextTitle: "프로젝트 컨텍스트",
  contextHint:
    "이 프로젝트 경로는 에스크로 작업 공간(다음 ID, 에스크로 생성, 상태 조회)에 바인딩됩니다.",
  createTitle: "에스크로 생성",
  payerLabel: "납부자 주소",
  payeeLabel: "수취인 주소",
  subcontractorLabel: "하도급자 주소",
  expiresAtLabel: "만료 Unix 타임스탬프",
  conditionHashLabel: "조건 해시",
  createAction: "에스크로 생성",
  nextEscrowTitle: "다음 에스크로 ID",
  nextEscrowLabel: "사용 가능한 온체인 ID",
  statusLookupTitle: "온체인 상태 조회",
  statusLookupLabel: "온체인 에스크로 ID",
  loadStatusAction: "에스크로 상태 조회",
  escrowResultTitle: "생성된 에스크로 기록",
  statusLabel: "상태",
  onChainIdLabel: "온체인 에스크로 ID",
  txHashLabel: "트랜잭션 해시",
  contractLabel: "컨트랙트 주소",
  buyerLabel: "매수인 주소",
  sellerLabel: "매도인 주소",
  onChainStatusTitle: "온체인 상태",
  totalAmountLabel: "총 금액 (wei)",
  remainingAmountLabel: "잔여 금액 (wei)",
  missingConditionHashError: "조건 해시를 입력해 주세요.",
  placeholder:
    "에스크로를 생성하거나 조회하여 이 프로젝트 경로의 블록체인 응답 체인을 검증하세요.",
  projectFallback: "라이브 API에서 프로젝트 메타데이터를 불러올 수 없습니다.",
  projectLoadErrorTitle: "프로젝트 메타데이터 조회 불가",
  projectLoadErrorDetail:
    "프로젝트 정보를 불러오지 못했습니다. 재시도하여 에스크로 경로 메타데이터를 복원하세요.",
  nextEscrowLoadErrorTitle: "다음 에스크로 ID 조회 불가",
  nextEscrowLoadErrorDetail:
    "블록체인 서비스에서 다음 온체인 에스크로 ID를 반환하지 못했습니다. 새 에스크로 생성 전 재시도하세요.",
  retryAction: "재시도",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatUnixDate(locale: string, value: number) {
  return formatDate(locale, new Date(value * 1000).toISOString());
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return authMessage;
    }

    return `API request failed with status ${error.status}.`;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed.";
}

export function ProjectBlockchainWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [workspaceError, setWorkspaceError] = useState("");
  const [createResult, setCreateResult] =
    useState<EscrowTransactionResponse | null>(null);
  const [statusResult, setStatusResult] = useState<OnChainEscrowResponse | null>(
    null,
  );
  const [isCreating, setIsCreating] = useState(false);
  const [isLoadingStatus, setIsLoadingStatus] = useState(false);
  const [lookupEscrowId, setLookupEscrowId] = useState("");
  const [form, setForm] = useState(() => ({
    payerAddress: "0x1111111111111111111111111111111111111111",
    payeeAddress: "0x2222222222222222222222222222222222222222",
    subcontractorAddress: "0x3333333333333333333333333333333333333333",
    expiresAt: String(Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30),
    conditionHash: `0x${"ab".repeat(32)}`,
  }));

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "blockchain-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, {
        useMock: false,
      }),
  });

  const nextEscrowQuery = useQuery({
    queryKey: ["blockchain", "next-id", projectId],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<{ next_escrow_id: number | null }>(
        "/blockchain/escrow/next-id",
        {
          useMock: false,
        },
      ),
  });

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";
  const nextEscrowError = nextEscrowQuery.error
    ? extractErrorMessage(nextEscrowQuery.error, labels.authError)
    : "";

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    if (!form.conditionHash.trim()) {
      setWorkspaceError(labels.missingConditionHashError);
      return;
    }

    setIsCreating(true);

    try {
      const response = await apiClient.post<EscrowTransactionResponse>(
        "/blockchain/escrow",
        {
          useMock: false,
          body: {
            project_id: projectId,
            payer_address: form.payerAddress.trim(),
            payee_address: form.payeeAddress.trim(),
            subcontractor_address: form.subcontractorAddress.trim(),
            expires_at: Number(form.expiresAt),
            condition_hash: form.conditionHash.trim(),
          },
        },
      );

      setCreateResult(response);
      if (response.on_chain_escrow_id != null) {
        setLookupEscrowId(String(response.on_chain_escrow_id));
      }
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsCreating(false);
    }
  }

  async function handleLoadStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    if (!lookupEscrowId.trim()) {
      return;
    }

    setIsLoadingStatus(true);

    try {
      const response = await apiClient.get<OnChainEscrowResponse>(
        `/blockchain/escrow/${lookupEscrowId.trim()}`,
        {
          useMock: false,
        },
      );
      setStatusResult(response);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsLoadingStatus(false);
    }
  }

  return (
    <section className="grid gap-6">
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.heroTitle}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            {labels.heroHint}
          </p>
          {!canUseLiveApi && (
            <p className="mt-3 max-w-3xl text-sm leading-8 text-[var(--text-tertiary)]">
            {labels.tokenHint}
          </p>
            )}
          {!canUseLiveApi ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.authError}
            </div>
          ) : null}
          {projectError ? (
            <div className="mt-6">
              <WorkspaceQueryErrorCard
                title={labels.projectLoadErrorTitle}
                description={labels.projectLoadErrorDetail}
                message={projectError}
                actionLabel={labels.retryAction}
                onRetry={() => {
                  void projectQuery.refetch();
                }}
              />
            </div>
          ) : null}
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="grid gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.contextTitle}
              </p>
              <CardTitle className="mt-2 text-xl">{labels.contextHint}</CardTitle>
            </div>
            {projectQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-28" />
            ) : (
              <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {projectQuery.data?.name ?? labels.projectFallback}
                </p>
                <p className="mt-2 break-all text-xs text-[var(--text-tertiary)]">
                  {projectId}
                </p>
                {projectQuery.data?.address ? (
                  <p className="mt-3 text-sm text-[var(--text-secondary)]">
                    {projectQuery.data.address}
                  </p>
                ) : null}
                {projectQuery.data ? (
                  <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                    {projectQuery.data.status} ·{" "}
                    {formatDate(locale, projectQuery.data.updated_at)}
                  </p>
                ) : null}
              </div>
            )}
            <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.nextEscrowTitle}
              </p>
              <p className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
                {nextEscrowQuery.data?.next_escrow_id ?? "-"}
              </p>
              <p className="mt-2 text-sm text-[var(--text-tertiary)]">
                {labels.nextEscrowLabel}
              </p>
              {nextEscrowError ? (
                <div className="mt-4">
                  <WorkspaceQueryErrorCard
                    title={labels.nextEscrowLoadErrorTitle}
                    description={labels.nextEscrowLoadErrorDetail}
                    message={nextEscrowError}
                    actionLabel={labels.retryAction}
                    onRetry={() => {
                      void nextEscrowQuery.refetch();
                    }}
                  />
                </div>
              ) : null}
            </div>
          </div>

          <Card className="bg-[var(--surface-soft)] shadow-none">
            <CardContent className="p-5">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.createTitle}
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleCreate}>
                <Input
                  value={form.payerAddress}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      payerAddress: event.target.value,
                    }))
                  }
                  placeholder={labels.payerLabel}
                />
                <Input
                  value={form.payeeAddress}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      payeeAddress: event.target.value,
                    }))
                  }
                  placeholder={labels.payeeLabel}
                />
                <Input
                  value={form.subcontractorAddress}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      subcontractorAddress: event.target.value,
                    }))
                  }
                  placeholder={labels.subcontractorLabel}
                />
                <Input
                  value={form.expiresAt}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      expiresAt: event.target.value,
                    }))
                  }
                  placeholder={labels.expiresAtLabel}
                />
                <Input
                  value={form.conditionHash}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      conditionHash: event.target.value,
                    }))
                  }
                  placeholder={labels.conditionHashLabel}
                />
                <Button type="submit" disabled={!canUseLiveApi || isCreating}>
                  {isCreating ? `${labels.createAction}...` : labels.createAction}
                </Button>
              </form>
            </CardContent>
          </Card>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.escrowResultTitle}
            </p>
            {createResult ? (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <MetricTile label={labels.statusLabel} value={createResult.status} />
                <MetricTile
                  label={labels.onChainIdLabel}
                  value={String(createResult.on_chain_escrow_id ?? "-")}
                />
                <MetricTile
                  label={labels.txHashLabel}
                  value={createResult.tx_hash ?? "-"}
                />
                <MetricTile
                  label={labels.contractLabel}
                  value={createResult.contract_address ?? "-"}
                />
                <MetricTile
                  label={labels.buyerLabel}
                  value={createResult.buyer_address}
                />
                <MetricTile
                  label={labels.sellerLabel}
                  value={createResult.seller_address}
                />
                <MetricTile
                  label="Created"
                  value={formatDate(locale, createResult.created_at)}
                />
                <MetricTile label="Amount (wei)" value={createResult.amount_wei} />
              </div>
            ) : (
              <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.placeholder}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-6">
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.statusLookupTitle}
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleLoadStatus}>
                <Input
                  value={lookupEscrowId}
                  onChange={(event) => setLookupEscrowId(event.target.value)}
                  placeholder={labels.statusLookupLabel}
                />
                <Button type="submit" disabled={!canUseLiveApi || isLoadingStatus}>
                  {isLoadingStatus
                    ? `${labels.loadStatusAction}...`
                    : labels.loadStatusAction}
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.onChainStatusTitle}
              </p>
              {statusResult ? (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <MetricTile label={labels.statusLabel} value={statusResult.status} />
                  <MetricTile
                    label={labels.onChainIdLabel}
                    value={String(statusResult.on_chain_escrow_id)}
                  />
                  <MetricTile
                    label={labels.totalAmountLabel}
                    value={statusResult.total_amount_wei}
                  />
                  <MetricTile
                    label={labels.remainingAmountLabel}
                    value={statusResult.remaining_amount_wei}
                  />
                  <MetricTile label="Payer" value={statusResult.payer} />
                  <MetricTile label="Payee" value={statusResult.payee} />
                  <MetricTile
                    label={labels.subcontractorLabel}
                    value={statusResult.subcontractor}
                  />
                  <MetricTile
                    label={labels.expiresAtLabel}
                    value={formatUnixDate(locale, statusResult.expires_at)}
                  />
                </div>
              ) : (
                <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                  {labels.placeholder}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}

function MetricTile({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-3 break-all text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}
