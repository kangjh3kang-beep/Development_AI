import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type {
  ComplianceCheckResponse,
  DesignPayload,
} from "@/components/cad/types";

const DEBOUNCE_MS = 500;

const EMPTY_RESULT = { data: null, isLoading: false, error: null } as const;

/**
 * 디자인 변경 시 debounce(500ms) 후 POST /building-compliance/check 호출.
 * 로딩 / 에러 / 데이터 상태 반환.
 */
export function useComplianceCheck(projectId: string, design: DesignPayload) {
  const hasPoints = design.points.length > 0;
  const [data, setData] = useState<ComplianceCheckResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!hasPoints) return;

    const timer = setTimeout(() => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsLoading(true);

      apiClient
        .post<ComplianceCheckResponse>("/building-compliance/check", {
          body: { project_id: projectId, design },
          signal: controller.signal,
        })
        .then((result) => {
          if (!controller.signal.aborted) {
            setData(result);
            setError(null);
          }
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          const message =
            err instanceof Error ? err.message : "법규 검증에 실패했습니다.";
          if (!controller.signal.aborted) {
            setError(message);
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setIsLoading(false);
          }
        });
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [projectId, design, hasPoints]);

  return useMemo(() => {
    if (!hasPoints) return EMPTY_RESULT;
    return { data, isLoading, error };
  }, [hasPoints, data, isLoading, error]);
}
