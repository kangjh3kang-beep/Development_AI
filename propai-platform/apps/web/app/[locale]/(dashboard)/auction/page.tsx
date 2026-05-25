import { AuctionWorkspaceClient } from "@/components/auction/AuctionWorkspaceClient";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { getDictionary } from "@/i18n/get-dictionary";
import { isValidLocale, type Locale } from "@/i18n/config";

type AuctionPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

export default async function AuctionPage({ params }: AuctionPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  const dictionary = await getDictionary(locale as Locale);
  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  return (
    <div className="grid gap-6">
            <ModulePlaceholder
        eyebrow={dictionary.modulePlaceholders["auction"].eyebrow}
        title={dictionary.modulePlaceholders["auction"].title}
        description={dictionary.modulePlaceholders["auction"].description}
        statusLabel={runtimeMode}
        localeLabel={locale}
        items={dictionary.modulePlaceholders["auction"].items}
      />
      <AuctionWorkspaceClient locale={locale as Locale} />
    </div>
  );
}
