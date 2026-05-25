"use client";

import { useState } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";

interface Props {
  projectId: string;
}

export function VersionHistoryView({ projectId }: Props) {
  const { commits, commitVersion, fetchCommitLog } = useFeasibilityV2Store();
  const [message, setMessage] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const handleCommit = async () => {
    if (!message.trim()) return;
    setIsSaving(true);
    await commitVersion(message);
    setMessage("");
    await fetchCommitLog(projectId);
    setIsSaving(false);
  };

  return (
    <div className="space-y-6">
      {/* 새 커밋 */}
      <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <CardContent className="p-6">
          <h4 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
            버전 저장
          </h4>
          <div className="flex gap-3">
            <Input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="변경 내용을 입력하세요..."
              className="flex-1"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCommit();
              }}
            />
            <Button onClick={handleCommit} disabled={isSaving || !message.trim()}>
              {isSaving ? "저장 중..." : "커밋"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* 커밋 이력 */}
      <Card className="rounded-[var(--radius-xl)] border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <CardContent className="p-6">
          <h4 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">
            커밋 이력
          </h4>
          {commits.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              아직 커밋이 없습니다.
            </p>
          ) : (
            <div className="space-y-3">
              {commits.map((commit, idx) => (
                <div
                  key={commit.sha}
                  className="relative flex gap-4 pb-3"
                >
                  {/* 타임라인 도트 */}
                  <div className="flex flex-col items-center">
                    <div className={`h-3 w-3 rounded-full ${idx === 0 ? "bg-blue-500" : "bg-slate-300 dark:bg-slate-600"}`} />
                    {idx < commits.length - 1 && (
                      <div className="w-px flex-1 bg-slate-200 dark:bg-slate-700" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {commit.message}
                    </p>
                    <div className="mt-1 flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
                      <code className="font-mono">{commit.sha.slice(0, 8)}</code>
                      <span>{new Date(commit.timestamp).toLocaleString("ko-KR")}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
