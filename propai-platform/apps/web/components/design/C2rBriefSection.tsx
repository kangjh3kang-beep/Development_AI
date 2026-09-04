"use client";

/**
 * C2rBriefSection — "C2R(좌표→렌더) 부지 렌더 브리프·이미지 렌더" 접힘 섹션(배선 캠페인 3차).
 *
 * 배경: 배선설계도 P2 트리아지 ② 프론트 배선 후보 중 c2r(apps/api/app/routers/c2r.py,
 * POST /api/v1/c2r/brief·/render)은 부지 좌표(주소/PNU) → 구조화 렌더 브리프(인벨로프·
 * Think-Before 게이팅) → provider 이미지 렌더까지 완성된 2단계 파이프라인인데 화면이
 * 없어 아무도 호출하지 못했다. 부지 렌더 성격상 설계 스튜디오 진입 전 단계인 이 페이지
 * (DesignGenPanel 바로 아래)에 붙인다.
 *
 * ★2단계 흐름: ① /brief로 브리프를 만들면 render.status가 'pending_provider'(진행 가능)
 * 또는 'blocked_by_think_before'(명료화 필요)로 온다. ② pending_provider일 때만 이전
 * 단계의 brief 객체를 그대로 /render에 되돌려 보내 이미지를 생성한다(별도 body 조립
 * 순수함수 없음 — 브리프 자체가 입력이므로 lib에는 buildC2rBriefBody만 둔다).
 *
 * ★정직 강등 원칙(무날조): provider 키 미설정(provider_unconfigured)·호출 실패(render_error)·
 * 미지원 provider는 가짜 이미지를 만들지 않고 백엔드가 반환한 사유를 그대로 노출한다.
 * 성공(rendered)일 때만 image.b64_json/url을 실제 렌더로 표시한다.
 *
 * SSOT 커밋 없음: 렌더 브리프/이미지는 프로젝트 물리량이 아닌 참고 자료이므로
 * useProjectContextStore에 되먹임하지 않는다. 기본 접힘(AdvancedDrawer).
 */

import { useCallback, useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { apiClient } from "@/lib/api-client";
import { c2rBriefInitialValues, buildC2rBriefBody } from "@/lib/workspace-extended-panels";
import { extractApiErrorMessage } from "@/lib/esg-extended-panels";

type ThinkBefore = {
  ambiguous: boolean;
  open_questions: string[];
  missing_criteria: string[];
  proceed: boolean;
};

type RenderStatus = {
  status: string;
  reason?: string | null;
  note?: string | null;
};

type BriefResponse = {
  parcel: Record<string, unknown>;
  envelope: Record<string, unknown>;
  brief: Record<string, unknown>;
  think_before: ThinkBefore;
  render: RenderStatus;
  error?: string;
};

type RenderResponse = {
  status: string;
  provider: string;
  model?: string;
  reason?: string;
  image: { b64_json: string | null; url: string | null } | null;
  render_guard?: string;
  render_guard_warning?: { status: string; reason: string };
};

const PROVIDERS: { label: string; value: string }[] = [
  { label: "OpenAI(gpt-image-1)", value: "openai" },
  { label: "Google Gemini", value: "gemini" },
];

export function C2rBriefSection({
  pnu,
  address,
}: {
  pnu: string | null | undefined;
  address: string | null | undefined;
}) {
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const authErrorMessage = "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.";

  const [values, setValues] = useState(() =>
    c2rBriefInitialValues({ pnu: pnu ?? null, address: address ?? null }),
  );
  const [provider, setProvider] = useState("openai");
  const [briefResult, setBriefResult] = useState<BriefResponse | null>(null);
  const [renderResult, setRenderResult] = useState<RenderResponse | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"brief" | "render" | null>(null);

  const createBrief = useCallback(async () => {
    setError("");
    setRenderResult(null);
    if (!values.pnu.trim() && !values.address.trim()) {
      setError("PNU 또는 주소를 입력하세요.");
      return;
    }
    setPending("brief");
    try {
      const response = await apiClient.post<BriefResponse>("/c2r/brief", {
        useMock: false,
        body: buildC2rBriefBody(values),
      });
      setBriefResult(response);
    } catch (err) {
      setError(extractApiErrorMessage(err, authErrorMessage));
    } finally {
      setPending(null);
    }
  }, [values]);

  const renderImage = useCallback(async () => {
    setError("");
    if (!briefResult?.brief) return;
    setPending("render");
    try {
      const response = await apiClient.post<RenderResponse>("/c2r/render", {
        useMock: false,
        body: { brief: briefResult.brief, provider },
      });
      setRenderResult(response);
    } catch (err) {
      setError(extractApiErrorMessage(err, authErrorMessage));
    } finally {
      setPending(null);
    }
  }, [briefResult, provider]);

  async function handleBriefSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await createBrief();
  }

  const canRender = briefResult?.render?.status === "pending_provider";
  const imageSrc =
    renderResult?.status === "rendered" && renderResult.image
      ? renderResult.image.url ??
        (renderResult.image.b64_json ? `data:image/png;base64,${renderResult.image.b64_json}` : null)
      : null;

  return (
    <AdvancedDrawer label="C2R 부지 렌더 브리프·이미지 렌더">
      <Card>
        <CardContent className="p-6">
          <p className="label-caps text-[var(--text-tertiary)]">
            좌표 → 렌더 브리프
          </p>
          <form className="mt-4 grid gap-3" onSubmit={handleBriefSubmit}>
            <div className="grid gap-3 md:grid-cols-2">
              <Input
                value={values.pnu}
                onChange={(e) => setValues((prev) => ({ ...prev, pnu: e.target.value }))}
                placeholder="PNU(필지고유번호)"
              />
              <Input
                value={values.address}
                onChange={(e) => setValues((prev) => ({ ...prev, address: e.target.value }))}
                placeholder="주소(PNU 미지정 시)"
              />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Input
                value={values.buildingUse}
                onChange={(e) => setValues((prev) => ({ ...prev, buildingUse: e.target.value }))}
                placeholder="용도(선택, 예: 오피스텔)"
              />
              <Input
                value={values.scale}
                onChange={(e) => setValues((prev) => ({ ...prev, scale: e.target.value }))}
                placeholder="규모(선택)"
              />
            </div>
            <label className="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={values.useLlm}
                onChange={(e) => setValues((prev) => ({ ...prev, useLlm: e.target.checked }))}
                className="h-4 w-4 accent-[var(--accent-strong)]"
              />
              LLM 자연어 보강(브리프 서술 보강, 렌더는 별도)
            </label>
            <Button type="submit" disabled={!canUseLiveApi || pending === "brief"}>
              {pending === "brief" ? "브리프 생성 중..." : "브리프 생성"}
            </Button>
          </form>

          {error ? (
            <div className="mt-4">
              <WorkspaceQueryErrorCard
                title="C2R 오류"
                description="입력값을 확인한 뒤 다시 시도하세요."
                message={error}
                actionLabel="다시 시도"
                onRetry={pending === "render" ? renderImage : createBrief}
              />
            </div>
          ) : null}

          {briefResult ? (
            <div className="mt-6 space-y-4">
              {briefResult.render.status === "blocked_by_think_before" ? (
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                  <p className="font-semibold text-[var(--text-primary)]">
                    명료화가 필요해 렌더가 보류되었습니다(Think-Before).
                  </p>
                  {briefResult.think_before.open_questions.length > 0 ? (
                    <ul className="mt-2 list-disc pl-5 text-xs">
                      {briefResult.think_before.open_questions.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : (
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm text-[var(--text-secondary)]">
                  브리프 생성 완료 — 렌더 진행 가능(provider 이미지 렌더는 아래에서 실행).
                </div>
              )}

              {canRender ? (
                <div className="grid gap-3">
                  <div className="flex flex-wrap gap-2">
                    {PROVIDERS.map((p) => (
                      <button
                        key={p.value}
                        type="button"
                        onClick={() => setProvider(p.value)}
                        className={`rounded-lg border px-3 py-2 text-xs font-bold ${
                          provider === p.value
                            ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"
                            : "border-[var(--line)] text-[var(--text-tertiary)]"
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                  <Button onClick={renderImage} disabled={!canUseLiveApi || pending === "render"}>
                    {pending === "render" ? "렌더 중..." : "이미지 렌더 실행"}
                  </Button>
                </div>
              ) : null}

              {renderResult ? (
                renderResult.status === "rendered" && imageSrc ? (
                  <div className="grid gap-2">
                    {/* eslint-disable-next-line @next/next/no-img-element -- provider 응답(b64/URL) 원본을 그대로 표시(가짜 이미지 없음) */}
                    <img
                      src={imageSrc}
                      alt="C2R 렌더 결과"
                      className="w-full rounded-[var(--radius-xl)] border border-[var(--line)]"
                    />
                    <p className="text-xs text-[var(--text-tertiary)]">
                      provider: {renderResult.provider}
                      {renderResult.model ? ` · model: ${renderResult.model}` : ""}
                    </p>
                  </div>
                ) : (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
                    <p className="font-semibold text-[var(--text-primary)]">
                      {renderResult.status === "provider_unconfigured"
                        ? "이미지 provider가 설정되지 않았습니다(관리자 키 미설정)."
                        : renderResult.status === "unsupported_provider"
                          ? "지원하지 않는 provider입니다."
                          : "렌더에 실패했습니다."}
                    </p>
                    {renderResult.reason ? (
                      <p className="mt-1 text-xs text-[var(--text-tertiary)]">{renderResult.reason}</p>
                    ) : null}
                  </div>
                )
              ) : null}
            </div>
          ) : !error ? (
            <div className="mt-6 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              PNU 또는 주소를 입력해 브리프를 생성하면 렌더 가능 여부와 결과가 표시됩니다.
            </div>
          ) : null}
        </CardContent>
      </Card>
    </AdvancedDrawer>
  );
}
