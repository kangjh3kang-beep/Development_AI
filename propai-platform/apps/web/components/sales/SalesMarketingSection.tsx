"use client";

/**
 * SalesMarketingSection — "마케팅 콘텐츠·OM(투자설명서) 리포트 생성" 접힘 섹션(배선 캠페인 3차).
 *
 * 배경: 배선설계도 P2 트리아지 ② 프론트 배선 후보 중 marketing(routers/marketing.py,
 * POST /api/v1/marketing/generate·/om-report)은 채널별 마케팅 카피와 기관투자자용
 * 오퍼링 메모랜덤(OM) 초안을 생성하는 서비스가 이미 완성돼 있는데 화면이 없어 아무도
 * 호출하지 못했다.
 *
 * ★마운트 근거: 후보 두 곳(sales-info=청약홈 외부 분양정보 브라우저, sales=자사 분양현장
 * 관리) 중 sales(SalesSiteList)를 선택했다 — marketing 라우터는 project_id+project_name을
 * 요구하는데, sales-info는 타사 분양 공고를 열람할 뿐 내부 프로젝트 컨텍스트가 없고(project_id
 * 공급 불가), sales 페이지는 이미 프로젝트 목록(연결할 프로젝트 select)을 보유하고 있어
 * 그대로 재사용할 수 있다(중복 조회 없음).
 *
 * SSOT 커밋 없음(무날조): 마케팅 카피·OM 초안은 프로젝트 물리량이 아닌 생성형 콘텐츠라
 * useProjectContextStore에 되먹임하지 않는다. 기본 접힘(AdvancedDrawer).
 */

import { useCallback, useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input, Select } from "@propai/ui";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { apiClient } from "@/lib/api-client";
import {
  marketingContentInitialValues,
  buildMarketingContentBody,
  omReportInitialValues,
  buildOmReportBody,
} from "@/lib/workspace-extended-panels";
import { extractApiErrorMessage } from "@/lib/esg-extended-panels";

type MarketingContentResponse = {
  content_id: string;
  channel: string;
  headline: string;
  body: string;
  call_to_action: string;
};

type OmReportResponse = {
  memorandum_id: string;
  title: string;
  executive_summary: string;
  sections: Record<string, unknown>[];
  risk_factors: string[];
  output_format: string;
};

export function SalesMarketingSection({
  projects,
}: {
  projects: { id: string; name: string }[];
}) {
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const authErrorMessage = "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.";

  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const projectName = projects.find((p) => p.id === projectId)?.name ?? "";

  const [contentValues, setContentValues] = useState(() => marketingContentInitialValues());
  const [contentResult, setContentResult] = useState<MarketingContentResponse | null>(null);
  const [omValues, setOmValues] = useState(() => omReportInitialValues());
  const [omResult, setOmResult] = useState<OmReportResponse | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"content" | "om" | null>(null);

  const generateContent = useCallback(async () => {
    setError("");
    if (!projectId) {
      setError("마케팅 콘텐츠를 생성할 프로젝트를 선택하세요.");
      return;
    }
    // ★MarketingContentRequest.channel/asset_type/target_audience는 백엔드 기본값이 없는
    // 필수 필드다(위 초기값이 빈 문자열인 이유) — 422를 기다리지 않고 선제 안내한다.
    if (!contentValues.channel.trim() || !contentValues.assetType.trim() || !contentValues.targetAudience.trim()) {
      setError("채널·자산유형·타깃을 모두 입력하세요.");
      return;
    }
    setPending("content");
    try {
      const response = await apiClient.post<MarketingContentResponse>("/marketing/generate", {
        useMock: false,
        body: buildMarketingContentBody(contentValues, { projectId, projectName }),
      });
      setContentResult(response);
    } catch (err) {
      setError(extractApiErrorMessage(err, authErrorMessage));
    } finally {
      setPending(null);
    }
  }, [projectId, projectName, contentValues]);

  const generateOm = useCallback(async () => {
    setError("");
    if (!projectId) {
      setError("OM 리포트를 생성할 프로젝트를 선택하세요.");
      return;
    }
    // ★OMReportRequest.asset_type은 백엔드 기본값이 없는 필수 필드다.
    if (!omValues.assetType.trim()) {
      setError("자산유형을 입력하세요.");
      return;
    }
    setPending("om");
    try {
      const response = await apiClient.post<OmReportResponse>("/marketing/om-report", {
        useMock: false,
        body: buildOmReportBody(omValues, { projectId, projectName }),
      });
      setOmResult(response);
    } catch (err) {
      setError(extractApiErrorMessage(err, authErrorMessage));
    } finally {
      setPending(null);
    }
  }, [projectId, projectName, omValues]);

  async function handleContentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await generateContent();
  }

  async function handleOmSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await generateOm();
  }

  return (
    <AdvancedDrawer label="마케팅 콘텐츠·OM 리포트 생성">
      <div className="grid gap-4">
        <Select
          value={projectId}
          onValueChange={setProjectId}
          options={projects.map((p) => ({ label: p.name, value: p.id }))}
          className="h-11 rounded-[var(--radius-md)] border-[var(--line)] bg-[var(--surface)]"
        />

        {error ? (
          <WorkspaceQueryErrorCard
            title="마케팅/OM 생성 오류"
            description="입력값을 확인한 뒤 다시 시도하세요."
            message={error}
            actionLabel="다시 시도"
            onRetry={pending === "om" ? generateOm : generateContent}
          />
        ) : null}

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                채널별 마케팅 콘텐츠
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleContentSubmit}>
                <Input value={contentValues.channel} onChange={(e) => setContentValues((prev) => ({ ...prev, channel: e.target.value }))} placeholder="채널(예: web, instagram)" />
                <Input value={contentValues.assetType} onChange={(e) => setContentValues((prev) => ({ ...prev, assetType: e.target.value }))} placeholder="자산유형(예: residential)" />
                <Input value={contentValues.targetAudience} onChange={(e) => setContentValues((prev) => ({ ...prev, targetAudience: e.target.value }))} placeholder="타깃(예: MZ 세대)" />
                <Input value={contentValues.tone} onChange={(e) => setContentValues((prev) => ({ ...prev, tone: e.target.value }))} placeholder="톤(예: professional)" />
                <Input value={contentValues.highlights} onChange={(e) => setContentValues((prev) => ({ ...prev, highlights: e.target.value }))} placeholder="강조 포인트(콤마 구분, 예: 역세권, 신축)" />
                <Button type="submit" disabled={!canUseLiveApi || pending === "content"}>
                  {pending === "content" ? "생성 중..." : "콘텐츠 생성"}
                </Button>
              </form>
              {contentResult ? (
                <div className="mt-4 space-y-2 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4 text-sm">
                  <p className="font-semibold text-[var(--text-primary)]">{contentResult.headline}</p>
                  <p className="text-[var(--text-secondary)]">{contentResult.body}</p>
                  <p className="text-xs font-bold text-[var(--accent-strong)]">{contentResult.call_to_action}</p>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                OM(투자설명서) 리포트
              </p>
              <form className="mt-4 grid gap-3" onSubmit={handleOmSubmit}>
                <Input value={omValues.assetType} onChange={(e) => setOmValues((prev) => ({ ...prev, assetType: e.target.value }))} placeholder="자산유형(예: office)" />
                <Input value={omValues.investmentHighlights} onChange={(e) => setOmValues((prev) => ({ ...prev, investmentHighlights: e.target.value }))} placeholder="투자 하이라이트(콤마 구분)" />
                <Input value={omValues.targetAudience} onChange={(e) => setOmValues((prev) => ({ ...prev, targetAudience: e.target.value }))} placeholder="타깃(예: institutional)" />
                <Input value={omValues.riskFactors} onChange={(e) => setOmValues((prev) => ({ ...prev, riskFactors: e.target.value }))} placeholder="리스크 요인(콤마 구분)" />
                <Input value={omValues.outputFormat} onChange={(e) => setOmValues((prev) => ({ ...prev, outputFormat: e.target.value }))} placeholder="출력형식(예: markdown, pdf)" />
                <Button type="submit" disabled={!canUseLiveApi || pending === "om"}>
                  {pending === "om" ? "생성 중..." : "OM 리포트 생성"}
                </Button>
              </form>
              {omResult ? (
                <div className="mt-4 space-y-2 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4 text-sm">
                  <p className="font-semibold text-[var(--text-primary)]">{omResult.title}</p>
                  <p className="text-[var(--text-secondary)]">{omResult.executive_summary}</p>
                  {omResult.risk_factors.length > 0 ? (
                    <p className="text-xs text-[var(--text-tertiary)]">리스크: {omResult.risk_factors.join(", ")}</p>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </AdvancedDrawer>
  );
}
