import { isValidLocale } from "@/i18n/config";
import { LifecycleNavigator } from "@/components/projects/LifecycleNavigator";
import React from "react";

export const dynamicParams = true;

type ProjectLayoutProps = {
  children: React.ReactNode;
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function ProjectLayout({
  children,
  params,
}: ProjectLayoutProps) {
  const { locale, id } = await params;

  if (!isValidLocale(locale)) {
    return children;
  }

  return (
    <div className="flex flex-col gap-8">
      <LifecycleNavigator locale={locale} projectId={id} />
      <div className="min-w-0 transition-all duration-500 animate-in fade-in slide-in-from-bottom-4">
        {children}
      </div>
    </div>
  );
}
