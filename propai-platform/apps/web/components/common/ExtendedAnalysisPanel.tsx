"use client";

/**
 * ExtendedAnalysisPanel — "완성 서비스·UI 부재" 백엔드 라우터 공용 소형 패널.
 *
 * 왜 필요한가(쉬운 설명): 배선설계도 P2 트리아지가 찾아낸 다수의 백엔드 라우터가
 * 이미 완성돼 있는데 화면이 없어 아무도 못 쓰고 있었다. 각 라우터마다 따로 폼을
 * 만들면 코드가 N배 중복되므로, 이 패널 하나가 "필드 목록 + 바디 조립함수 + 결과
 * 렌더 함수"를 설정(config)으로 받아 동작한다(입력 폼 → 실행 버튼 → 결과 렌더 →
 * 에러 상태 → 로딩, 전부 공용).
 *
 * ★배선 캠페인 2차(2026-07-11): 1차(ESG 클러스터 5건)에서 components/projects/
 * ExtendedEsgPanel.tsx로 도입됐던 이 컴포넌트를 ESG 전용 폴더에서 공용 폴더로
 * 이동·리네임했다 — permit-cases/cost-intelligence/underwriting/safety/construction/
 * cad-correction 등 ESG 외 클러스터에서도 그대로 재사용하기 위함(동작 불변, 이름만 일반화).
 *
 * 계약: buildBody는 각 lib/*-extended-panels.ts의 순수함수를 그대로 넘긴다(로직 중복 금지).
 * 에러는 WorkspaceQueryErrorCard(공용)로 정직하게 노출한다(응답에 없는 값 표시 금지).
 */

import { useCallback, useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { NumberInput } from "@/components/common/NumberInput";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { extractApiErrorMessage, validatePositiveFields } from "@/lib/esg-extended-panels";

export type ExtendedAnalysisFieldType = "number" | "text" | "boolean";

export interface ExtendedAnalysisFormField {
  /** 폼 값 객체의 키(예: "totalElectricityMwh"). */
  key: string;
  label: string;
  type: ExtendedAnalysisFieldType;
  /** number 타입 전용 — 소수 허용 여부(기본 true). */
  allowDecimal?: boolean;
  placeholder?: string;
}

export type ExtendedAnalysisFormValues = Record<string, string | boolean>;

export interface ExtendedAnalysisPanelProps<
  V extends ExtendedAnalysisFormValues = ExtendedAnalysisFormValues,
> {
  title: string;
  fields: ExtendedAnalysisFormField[];
  initialValues: V;
  /** lib/*-extended-panels.ts의 순수 바디 조립함수(이미 project_id 등 컨텍스트 바인딩됨). */
  buildBody: (values: V) => unknown;
  /** apiClient가 프리픽스(/api/v1)를 붙이는 경로(예: "/re100/track"). */
  endpoint: string;
  submitLabel: string;
  resultTitle: string;
  renderResult: (result: unknown) => React.ReactNode;
  canUseLiveApi: boolean;
  authErrorMessage: string;
  placeholderMessage: string;
  /** ★QA F3: 백엔드 Pydantic gt=0 필수 필드(전력사용량·초기공사비·GFA·자산가치·연면적 등) —
   *  비어있거나 0 이하면 제출을 막고 해당 필드 옆에 안내한다(422 일반 에러 대신 정직 선제 안내).
   *  미지정 시 전부 통과(검증 없음 — 선택 필드만 있는 라우터는 생략 가능). */
  requiredPositiveFields?: string[];
}

export function ExtendedAnalysisPanel<
  V extends ExtendedAnalysisFormValues = ExtendedAnalysisFormValues,
>({
  title,
  fields,
  initialValues,
  buildBody,
  endpoint,
  submitLabel,
  resultTitle,
  renderResult,
  canUseLiveApi,
  authErrorMessage,
  placeholderMessage,
  requiredPositiveFields,
}: ExtendedAnalysisPanelProps<V>) {
  const [values, setValues] = useState<V>(initialValues);
  const [result, setResult] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const setField = useCallback((key: string, value: string | boolean) => {
    setValues((prev) => ({ ...prev, [key]: value }) as V);
    // 사용자가 값을 고치기 시작하면 해당 필드의 이전 검증 에러는 지운다(재제출 전까지 유지되는
    // 낡은 안내 방지) — 다른 필드 에러는 그대로 둔다.
    setFieldErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  const submit = useCallback(async () => {
    setError("");

    // ★QA F3: 제출 전 gt=0 필수 필드를 먼저 검증한다 — 비어있으면 백엔드 422를 기다리지
    // 않고 즉시 해당 필드 옆에 안내하고 네트워크 호출 자체를 생략한다.
    if (requiredPositiveFields && requiredPositiveFields.length > 0) {
      const errors = validatePositiveFields(values, requiredPositiveFields);
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors);
        return;
      }
    }
    setFieldErrors({});

    setIsSubmitting(true);
    try {
      const body = buildBody(values);
      const response = await apiClient.post<unknown>(endpoint, {
        useMock: false,
        body: body as Record<string, unknown>,
      });
      setResult(response);
    } catch (err) {
      setError(extractApiErrorMessage(err, authErrorMessage));
    } finally {
      setIsSubmitting(false);
    }
  }, [buildBody, endpoint, values, authErrorMessage, requiredPositiveFields]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submit();
  }

  return (
    <Card>
      <CardContent className="p-6">
        <p className="label-caps text-[var(--text-tertiary)]">
          {title}
        </p>
        <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
          {fields.map((field) =>
            field.type === "boolean" ? (
              <label
                key={field.key}
                className="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]"
              >
                <input
                  type="checkbox"
                  checked={!!values[field.key]}
                  onChange={(e) => setField(field.key, e.target.checked)}
                  className="h-4 w-4 accent-[var(--accent-strong)]"
                />
                {field.label}
              </label>
            ) : (
              <div key={field.key} className="grid gap-1.5">
                <label className="text-[11px] font-medium text-[var(--text-tertiary)]">
                  {field.label}
                </label>
                {field.type === "number" ? (
                  <NumberInput
                    allowDecimal={field.allowDecimal !== false}
                    value={
                      values[field.key] === "" || values[field.key] == null
                        ? null
                        : Number(values[field.key])
                    }
                    onChange={(n) =>
                      setField(field.key, n != null ? String(n) : "")
                    }
                    placeholder={field.placeholder ?? field.label}
                    className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                  />
                ) : (
                  <Input
                    value={String(values[field.key] ?? "")}
                    onChange={(e) => setField(field.key, e.target.value)}
                    placeholder={field.placeholder ?? field.label}
                  />
                )}
                {fieldErrors[field.key] ? (
                  <p className="text-[11px] font-medium text-[var(--status-error)]">
                    {fieldErrors[field.key]}
                  </p>
                ) : null}
              </div>
            ),
          )}
          <Button type="submit" disabled={!canUseLiveApi || isSubmitting}>
            {isSubmitting ? `${submitLabel}...` : submitLabel}
          </Button>
        </form>

        {error ? (
          <div className="mt-4">
            <WorkspaceQueryErrorCard
              title={`${title} 오류`}
              description="입력값을 확인한 뒤 다시 시도하세요."
              message={error}
              actionLabel="다시 시도"
              onRetry={submit}
            />
          </div>
        ) : null}

        <div className="mt-6">
          <p className="label-caps text-[var(--text-tertiary)]">
            {resultTitle}
          </p>
          {result ? (
            <div className="mt-4 space-y-4">{renderResult(result)}</div>
          ) : !error ? (
            <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {placeholderMessage}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
