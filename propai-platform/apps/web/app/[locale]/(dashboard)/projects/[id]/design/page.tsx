"use client";

import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { DesignStudio } from "@/components/design/DesignStudio";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";

export default function DesignPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);

  if (isLoading || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent" />
      </div>
    );
  }

  if (!isValidLocale(locale)) {
    return null;
  }

  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  const t = dictionary.modulePlaceholders["design"];

  return (
    <div className="flex flex-col gap-12 pb-20">
      {/* ① 컨텍스트 헤더 */}
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <ModulePlaceholder
          eyebrow={t.eyebrow}
          title={t.title}
          description={t.description}
          statusLabel={runtimeMode}
          localeLabel={locale}
          items={t.items}
        />
      </motion.div>

      {/* ② 위젯 */}
      <DesignStudio projectId={id} />

      {/* ③ 다음 단계 CTA */}
      <NextStageCta locale={locale} currentStage="design" />
    </div>
  );
}
