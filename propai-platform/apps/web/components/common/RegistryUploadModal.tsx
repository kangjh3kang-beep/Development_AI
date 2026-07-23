"use client";

import { useCallback, useState } from "react";
import { AlertCircle, FileUp, CheckCircle2, Loader2, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";

type UploadResult = {
  ok: boolean;
  status: string;
  owner?: string;
  unique_no?: string;
  mortgage_summary?: string;
  message?: string;
  registry_text?: string;
};

export function RegistryUploadModal({
  isOpen,
  onClose,
  onParsed,
}: {
  isOpen: boolean;
  onClose: () => void;
  onParsed?: (data: UploadResult) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setResult(null);
    }
  };

  const handleUpload = useCallback(async () => {
    if (!file) return;
    setUploading(true);
    setResult(null);

    try {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = async () => {
        const base64Str = (reader.result as string).split(",")[1];
        const res = await apiClient.post<UploadResult>("/registry/get-one", {
          body: { pdf_input: base64Str },
          useMock: false,
        });
        setResult(res);
        if (onParsed && res.ok) {
          onParsed(res);
        }
      };
    } catch {
      setResult({
        ok: false,
        status: "error",
        message: "PDF 파싱 중 오류가 발생했습니다. 파일을 확인해 주세요.",
      });
    } finally {
      setUploading(false);
    }
  }, [file, onParsed]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-[var(--line)] pb-4">
          <div className="flex items-center gap-2">
            <FileUp className="size-5 text-[var(--accent-strong)]" />
            <h3 className="text-base font-bold text-[var(--text-primary)]">비상 등기부 PDF 직접 업로드</h3>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 hover:bg-[var(--surface-strong)]">
            <X className="size-5 text-[var(--text-secondary)]" />
          </button>
        </div>

        <p className="mt-3 text-xs text-[var(--text-secondary)]">
          대법원 인터넷등기소 또는 정부24에서 발급받은 등기부등본 PDF 파일을 첨부하시면 AI 권리분석 엔진이 자동으로 표제부·갑구·을구를 파싱합니다.
        </p>

        <div className="mt-4">
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-[var(--line)] bg-[var(--surface-strong)] p-6 transition-colors hover:border-[var(--accent-strong)]">
            <FileUp className="size-8 text-[var(--text-tertiary)]" />
            <span className="mt-2 text-xs font-semibold text-[var(--text-secondary)]">
              {file ? file.name : "클릭하거나 PDF 파일을 이곳에 드롭하세요"}
            </span>
            <input type="file" accept="application/pdf" className="hidden" onChange={handleFileChange} />
          </label>
        </div>

        {file && (
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent-strong)] py-2.5 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
          >
            {uploading ? <Loader2 className="size-4 animate-spin" /> : "등기부 PDF 분석 및 파싱 실행"}
          </button>
        )}

        {result && (
          <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-4 text-xs">
            {result.ok ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-emerald-400 font-bold">
                  <CheckCircle2 className="size-4" /> 등기부 파싱 완료
                </div>
                <p><span className="text-[var(--text-secondary)]">소유자:</span> <strong className="text-[var(--text-primary)]">{result.owner || "미확인"}</strong></p>
                <p><span className="text-[var(--text-secondary)]">고유번호:</span> {result.unique_no || "-"}</p>
                {result.mortgage_summary && (
                  <p><span className="text-[var(--text-secondary)]">권리 현황:</span> {result.mortgage_summary}</p>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-amber-400 font-bold">
                <AlertCircle className="size-4" /> {result.message || "파싱에 실패했습니다."}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
