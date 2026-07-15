"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type { Locale } from "@/i18n/config";
import { ApiClientError, apiClient } from "@/lib/api-client";

type ProjectResponse = {
  id: string;
  name: string;
  status: string;
  address: string | null;
  total_area_sqm: number | null;
  created_at: string;
  updated_at: string;
};

type ContractKeyTerm = {
  label: string;
  value: string;
};

type ContractClause = {
  title: string;
  body: string;
};

type ContractDraftResponse = {
  draft_id: string;
  project_id: string;
  project_name: string;
  contract_type: string;
  target_language: string;
  title: string;
  counterparty_name: string;
  effective_date: string;
  contract_amount_krw: number | null;
  document_url: string;
  status: string;
  sign_status: string;
  key_terms: ContractKeyTerm[];
  clauses: ContractClause[];
  summary: string;
  rendered_markdown: string;
  esign_request_id: string | null;
  created_at: string;
};

type Labels = {
  heroBadge: string;
  heroTitle: string;
  heroDescription: string;
  tokenHint: string;
  authError: string;
  projectTitle: string;
  projectStatusLabel: string;
  projectAddressLabel: string;
  projectUpdatedLabel: string;
  generationTitle: string;
  contractTypeLabel: string;
  languageLabel: string;
  counterpartyLabel: string;
  effectiveDateLabel: string;
  amountLabel: string;
  specialClausesLabel: string;
  generateAction: string;
  signerTitle: string;
  signerNameLabel: string;
  signerEmailLabel: string;
  signerPhoneLabel: string;
  requestESignAction: string;
  latestTitle: string;
  latestEmpty: string;
  statusLabel: string;
  signStatusLabel: string;
  documentUrlLabel: string;
  keyTermsLabel: string;
  clausesLabel: string;
  projectLoadErrorTitle: string;
  projectLoadErrorDetail: string;
  draftLoadErrorTitle: string;
  draftLoadErrorDetail: string;
  retryAction: string;
  missingCounterpartyError: string;
  missingSignerError: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    heroBadge: "PROJECT / CONTRACTS",
    heroTitle: "자동 계약초안 및 전자서명 작업 공간",
    heroDescription:
      "프로젝트 컨텍스트를 기준으로 계약 초안을 생성하고, 최신 초안을 다시 불러온 뒤 곧바로 전자서명 요청으로 넘깁니다.",
    tokenHint:
      "분석을 위해 로그인이 필요합니다.",
    authError: "실연동 API 인증이 필요합니다.",
    projectTitle: "프로젝트 컨텍스트",
    projectStatusLabel: "상태",
    projectAddressLabel: "주소",
    projectUpdatedLabel: "최근 갱신",
    generationTitle: "계약 초안 생성",
    contractTypeLabel: "계약 유형",
    languageLabel: "문서 언어",
    counterpartyLabel: "상대방 명칭",
    effectiveDateLabel: "효력발생일",
    amountLabel: "계약 금액 (KRW)",
    specialClausesLabel: "특약",
    generateAction: "계약 초안 생성",
    signerTitle: "전자서명 요청",
    signerNameLabel: "서명자 이름",
    signerEmailLabel: "서명자 이메일",
    signerPhoneLabel: "서명자 연락처",
    requestESignAction: "전자서명 요청 보내기",
    latestTitle: "최신 계약 초안",
    latestEmpty:
      "아직 생성된 초안이 없습니다. 현재 프로젝트에서 계약 유형과 언어를 선택해 초안을 생성하세요.",
    statusLabel: "초안 상태",
    signStatusLabel: "서명 상태",
    documentUrlLabel: "문서 URL",
    keyTermsLabel: "핵심 조건",
    clausesLabel: "주요 조항",
    projectLoadErrorTitle: "프로젝트 메타데이터 로드 실패",
    projectLoadErrorDetail:
      "프로젝트 상세를 불러오지 못했습니다. 현재 라우트 컨텍스트를 복구한 뒤 다시 시도하세요.",
    draftLoadErrorTitle: "계약 초안 로드 실패",
    draftLoadErrorDetail:
      "현재 계약 유형의 최신 초안을 불러오지 못했습니다. 다시 시도해 주세요.",
    retryAction: "다시 시도",
    missingCounterpartyError: "상대방 명칭이 필요합니다.",
    missingSignerError: "전자서명 요청에는 이름과 이메일이 필요합니다.",
  },
  en: {
    heroBadge: "PROJECT / CONTRACTS",
    heroTitle: "Automated contract draft and e-sign workspace",
    heroDescription:
      "Generate a project-aware contract draft, reload the latest persisted draft, and hand it off directly into the e-sign workflow.",
    tokenHint:
      "분석을 위해 로그인이 필요합니다.",
    authError: "API authentication is required for live workspace calls.",
    projectTitle: "Project context",
    projectStatusLabel: "Status",
    projectAddressLabel: "Address",
    projectUpdatedLabel: "Updated",
    generationTitle: "Generate contract draft",
    contractTypeLabel: "Contract type",
    languageLabel: "Document language",
    counterpartyLabel: "Counterparty",
    effectiveDateLabel: "Effective date",
    amountLabel: "Contract amount (KRW)",
    specialClausesLabel: "Special clauses",
    generateAction: "Generate contract draft",
    signerTitle: "Request e-signature",
    signerNameLabel: "Signer name",
    signerEmailLabel: "Signer email",
    signerPhoneLabel: "Signer phone",
    requestESignAction: "Send e-sign request",
    latestTitle: "Latest contract draft",
    latestEmpty:
      "No contract draft has been generated yet. Pick a contract type and language to create the first draft for this project.",
    statusLabel: "Draft status",
    signStatusLabel: "Sign status",
    documentUrlLabel: "Document URL",
    keyTermsLabel: "Key terms",
    clausesLabel: "Clauses",
    projectLoadErrorTitle: "Project metadata unavailable",
    projectLoadErrorDetail:
      "The routed project context failed to load from the live API. Retry before generating or handing off contracts.",
    draftLoadErrorTitle: "Contract draft unavailable",
    draftLoadErrorDetail:
      "The latest persisted draft for the selected contract type failed to load. Retry before issuing a new handoff.",
    retryAction: "Retry",
    missingCounterpartyError: "A counterparty name is required.",
    missingSignerError: "Signer name and email are required for e-sign handoff.",
  },
  "zh-CN": {
    heroBadge: "PROJECT / CONTRACTS",
    heroTitle: "自动合同草案与电子签署工作台",
    heroDescription:
      "基于项目上下文生成合同草案，读取最新持久化草案，并直接移交到电子签署流程。",
    tokenHint:
      "分析需要登录。",
    authError: "实时工作台调用需要 API 认证。",
    projectTitle: "项目上下文",
    projectStatusLabel: "状态",
    projectAddressLabel: "地址",
    projectUpdatedLabel: "更新时间",
    generationTitle: "生成合同草案",
    contractTypeLabel: "合同类型",
    languageLabel: "文档语言",
    counterpartyLabel: "相对方名称",
    effectiveDateLabel: "生效日期",
    amountLabel: "合同金额 (KRW)",
    specialClausesLabel: "特别条款",
    generateAction: "生成合同草案",
    signerTitle: "发送电子签署请求",
    signerNameLabel: "签署人姓名",
    signerEmailLabel: "签署人邮箱",
    signerPhoneLabel: "签署人电话",
    requestESignAction: "发送电子签署请求",
    latestTitle: "最新合同草案",
    latestEmpty:
      "尚未生成合同草案。请选择合同类型和语言，为当前项目生成首份草案。",
    statusLabel: "草案状态",
    signStatusLabel: "签署状态",
    documentUrlLabel: "文档 URL",
    keyTermsLabel: "关键条款",
    clausesLabel: "主要条款",
    projectLoadErrorTitle: "项目元数据不可用",
    projectLoadErrorDetail:
      "无法从实时 API 加载当前路由的项目上下文。请先重试，再生成或移交合同。",
    draftLoadErrorTitle: "合同草案不可用",
    draftLoadErrorDetail:
      "无法加载所选合同类型的最新持久化草案。请先重试，再执行新的签署移交。",
    retryAction: "重试",
    missingCounterpartyError: "需要填写相对方名称。",
    missingSignerError: "电子签署移交需要签署人姓名和邮箱。",
  },
};

const CONTRACT_TYPE_OPTIONS = [
  { label: "Construction", value: "construction" },
  { label: "Lease", value: "lease" },
  { label: "Sale", value: "sale" },
  { label: "Consulting", value: "consulting" },
];

const LANGUAGE_OPTIONS = [
  { label: "Korean", value: "ko" },
  { label: "English", value: "en" },
  { label: "简体中文", value: "zh-CN" },
];

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatCurrency(locale: string, value: number | null) {
  if (value == null) {
    return "-";
  }
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
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

function splitClauses(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function ProjectContractWorkspaceClient({
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
  const [isGenerating, setIsGenerating] = useState(false);
  const [isRequestingESign, setIsRequestingESign] = useState(false);
  const [generatedDraft, setGeneratedDraft] = useState<ContractDraftResponse | null>(
    null,
  );
  const [form, setForm] = useState({
    contractType: "construction",
    targetLanguage: locale as Locale,
    counterpartyName: "",
    effectiveDate: "2026-04-01",
    contractAmount: "4800000000",
    specialClauses:
      "Performance bond before mobilization\nWeekly progress reporting\nWritten approval for permit scope changes",
    signerName: "",
    signerEmail: "",
    signerPhone: "",
  });

  const projectQuery = useQuery({
    queryKey: ["projects", "detail", projectId, "contracts-live"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ProjectResponse>(`/projects/${projectId}`, { useMock: false }),
  });

  const latestDraftQuery = useQuery({
    queryKey: ["contracts", "latest", projectId, form.contractType],
    enabled: canUseLiveApi,
    queryFn: async () => {
      try {
        return await apiClient.get<ContractDraftResponse>(
          `/contracts/${projectId}/latest?contract_type=${form.contractType}`,
          { useMock: false },
        );
      } catch (error) {
        if (error instanceof ApiClientError && error.status === 404) {
          return null;
        }
        throw error;
      }
    },
  });

  useEffect(() => {
    setGeneratedDraft(null);
  }, [form.contractType, projectId]);

  useEffect(() => {
    if (!projectQuery.data?.name) {
      return;
    }
    setForm((current) => ({
      ...current,
      counterpartyName: current.counterpartyName || `${projectQuery.data.name} Counterparty`,
      signerName: current.signerName || "Project Signatory",
    }));
  }, [projectQuery.data]);

  const projectError = projectQuery.error
    ? extractErrorMessage(projectQuery.error, labels.authError)
    : "";
  const latestDraftError = latestDraftQuery.error
    ? extractErrorMessage(latestDraftQuery.error, labels.authError)
    : "";

  async function handleGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    if (!form.counterpartyName.trim()) {
      setWorkspaceError(labels.missingCounterpartyError);
      return;
    }

    setIsGenerating(true);

    try {
      const response = await apiClient.post<ContractDraftResponse>(
        "/contracts/generate",
        {
          useMock: false,
          body: {
            project_id: projectId,
            contract_type: form.contractType,
            target_language: form.targetLanguage,
            counterparty_name: form.counterpartyName.trim(),
            effective_date: new Date(form.effectiveDate).toISOString(),
            contract_amount_krw: form.contractAmount.trim()
              ? Number(form.contractAmount)
              : null,
            special_clauses: splitClauses(form.specialClauses),
          },
        },
      );
      setGeneratedDraft(response);
      void latestDraftQuery.refetch();
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleRequestESign() {
    const activeDraft = generatedDraft ?? latestDraftQuery.data;

    if (!activeDraft) {
      return;
    }

    if (!form.signerName.trim() || !form.signerEmail.trim()) {
      setWorkspaceError(labels.missingSignerError);
      return;
    }

    setWorkspaceError("");
    setIsRequestingESign(true);

    try {
      const response = await apiClient.post<ContractDraftResponse>(
        `/contracts/${activeDraft.draft_id}/esign`,
        {
          useMock: false,
          body: {
            signer_name: form.signerName.trim(),
            signer_email: form.signerEmail.trim(),
            signer_phone: form.signerPhone.trim() || null,
          },
        },
      );
      setGeneratedDraft(response);
      void latestDraftQuery.refetch();
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsRequestingESign(false);
    }
  }

  const latestDraft = generatedDraft ?? latestDraftQuery.data ?? null;

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 label-caps text-[var(--accent-strong)]">
              {labels.heroBadge}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            {labels.heroTitle}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            {labels.heroDescription}
          </p>
          {!canUseLiveApi && (
          <p className="mt-3 text-xs uppercase tracking-[0.18em] text-[var(--text-hint)]">
            {labels.tokenHint}
          </p>
          )}
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--status-warning)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="grid gap-3">
            <CardTitle>{labels.projectTitle}</CardTitle>
            {projectQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-32" />
            ) : projectQuery.isError ? (
              <WorkspaceQueryErrorCard
                title={labels.projectLoadErrorTitle}
                description={labels.projectLoadErrorDetail}
                message={projectError}
                actionLabel={labels.retryAction}
                onRetry={() => {
                  void projectQuery.refetch();
                }}
              />
            ) : projectQuery.data ? (
              <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-5 text-sm text-[var(--text-secondary)]">
                <p className="text-xs uppercase tracking-[0.22em] text-[var(--text-hint)]">
                  {projectQuery.data.id}
                </p>
                <h4 className="mt-3 text-xl font-semibold text-[var(--text-primary)]">
                  {projectQuery.data.name}
                </h4>
                <div className="mt-4 grid gap-2">
                  <p>
                    {labels.projectStatusLabel}: {projectQuery.data.status}
                  </p>
                  <p>
                    {labels.projectAddressLabel}: {projectQuery.data.address ?? "-"}
                  </p>
                  <p>
                    {labels.projectUpdatedLabel}:{" "}
                    {formatDate(locale, projectQuery.data.updated_at)}
                  </p>
                </div>
              </div>
            ) : null}
          </div>

          <form className="grid gap-4" onSubmit={handleGenerate}>
            <CardTitle>{labels.generationTitle}</CardTitle>
            <div className="grid gap-4 md:grid-cols-2">
              <Select
                label={labels.contractTypeLabel}
                value={form.contractType}
                options={CONTRACT_TYPE_OPTIONS}
                onValueChange={(value) =>
                  setForm((current) => ({ ...current, contractType: value }))
                }
              />
              <Select
                label={labels.languageLabel}
                value={form.targetLanguage}
                options={LANGUAGE_OPTIONS}
                onValueChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    targetLanguage: value as Locale,
                  }))
                }
              />
              <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                <span>{labels.counterpartyLabel}</span>
                <Input
                  value={form.counterpartyName}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      counterpartyName: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                <span>{labels.effectiveDateLabel}</span>
                <Input
                  type="date"
                  value={form.effectiveDate}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      effectiveDate: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
                <span>{labels.amountLabel}</span>
                <Input
                  inputMode="decimal"
                  value={form.contractAmount}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      contractAmount: event.target.value,
                    }))
                  }
                />
              </label>
            </div>
            <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
              <span>{labels.specialClausesLabel}</span>
              <textarea
                className="min-h-28 rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-strong)]"
                value={form.specialClauses}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    specialClauses: event.target.value,
                  }))
                }
              />
            </label>
            <Button type="submit" disabled={isGenerating}>
              {isGenerating ? "Submitting..." : labels.generateAction}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="grid gap-4">
            <CardTitle>{labels.latestTitle}</CardTitle>
            {latestDraftQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-48" />
            ) : latestDraftQuery.isError ? (
              <WorkspaceQueryErrorCard
                title={labels.draftLoadErrorTitle}
                description={labels.draftLoadErrorDetail}
                message={latestDraftError}
                actionLabel={labels.retryAction}
                onRetry={() => {
                  void latestDraftQuery.refetch();
                }}
              />
            ) : latestDraft ? (
              <div className="grid gap-4 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface)] p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h4 className="text-xl font-semibold text-[var(--text-primary)]">
                      {latestDraft.title}
                    </h4>
                    <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {latestDraft.summary}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs font-medium">
                    <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-3 py-1 text-[var(--accent-strong)]">
                      {labels.statusLabel}: {latestDraft.status}
                    </span>
                    <span className="rounded-full border border-[var(--line)] px-3 py-1 text-[var(--text-secondary)]">
                      {labels.signStatusLabel}: {latestDraft.sign_status}
                    </span>
                  </div>
                </div>
                <div className="grid gap-2 text-sm text-[var(--text-secondary)]">
                  <p>
                    {labels.documentUrlLabel}: {latestDraft.document_url}
                  </p>
                  <p>
                    {labels.projectUpdatedLabel}: {formatDate(locale, latestDraft.created_at)}
                  </p>
                  <p>
                    {labels.amountLabel}:{" "}
                    {formatCurrency(locale, latestDraft.contract_amount_krw)}
                  </p>
                </div>
                <div className="grid gap-3">
                  <p className="text-xs uppercase tracking-[0.22em] text-[var(--text-hint)]">
                    {labels.keyTermsLabel}
                  </p>
                  <div className="grid gap-2 md:grid-cols-2">
                    {(latestDraft.key_terms ?? []).map((term) => (
                      <div
                        key={`${term.label}-${term.value}`}
                        className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm"
                      >
                        <p className="text-xs uppercase tracking-[0.2em] text-[var(--text-hint)]">
                          {term.label}
                        </p>
                        <p className="mt-2 text-[var(--text-primary)]">{term.value}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="grid gap-3">
                  <p className="text-xs uppercase tracking-[0.22em] text-[var(--text-hint)]">
                    {labels.clausesLabel}
                  </p>
                  <div className="grid gap-3">
                    {(latestDraft.clauses ?? []).map((clause) => (
                      <div
                        key={clause.title}
                        className="rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-4"
                      >
                        <p className="font-semibold text-[var(--text-primary)]">
                          {clause.title}
                        </p>
                        <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                          {clause.body}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface)] p-6 text-sm leading-7 text-[var(--text-secondary)]">
                {labels.latestEmpty}
              </div>
            )}
          </div>

          <div className="grid gap-4 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-5">
            <CardTitle>{labels.signerTitle}</CardTitle>
            <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
              <span>{labels.signerNameLabel}</span>
              <Input
                value={form.signerName}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    signerName: event.target.value,
                  }))
                }
              />
            </label>
            <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
              <span>{labels.signerEmailLabel}</span>
              <Input
                value={form.signerEmail}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    signerEmail: event.target.value,
                  }))
                }
              />
            </label>
            <label className="grid gap-2 text-sm font-medium text-[var(--text-primary)]">
              <span>{labels.signerPhoneLabel}</span>
              <Input
                value={form.signerPhone}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    signerPhone: event.target.value,
                  }))
                }
              />
            </label>
            <Button
              type="button"
              disabled={!latestDraft || isRequestingESign}
              onClick={() => {
                void handleRequestESign();
              }}
            >
              {isRequestingESign ? "Submitting..." : labels.requestESignAction}
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
