import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AccessibilityProvider } from "@/components/ui/AccessibilityProvider";
import { HtmlLangSetter } from "@/components/layout/HtmlLangSetter";
import { getDictionary } from "@/i18n/get-dictionary";
import { AppProviders } from "@/lib/providers";
import { isValidLocale, locales, type Locale } from "@/i18n/config";

export const dynamicParams = true;

type LocaleLayoutProps = Readonly<{
  children: React.ReactNode;
  params: Promise<{
    locale: string;
  }>;
}>;

type MetadataProps = {
  params: Promise<{
    locale: string;
  }>;
};

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: MetadataProps): Promise<Metadata> {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return {};
  }

  const dictionary = await getDictionary(locale);

  return {
    title: {
      default: dictionary.meta.title,
      template: `%s | ${dictionary.meta.siteName}`,
    },
    description: dictionary.meta.description,
  };
}

export default async function LocaleLayout({
  children,
  params,
}: LocaleLayoutProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    notFound();
  }

  const dictionary = await getDictionary(locale as Locale);

  return (
    <AccessibilityProvider
      locale={locale as Locale}
      announcerLabel={dictionary.a11y.screenReaderRegion}
    >
      <HtmlLangSetter locale={locale as Locale} />
      <AppProviders locale={locale as Locale}>
        <a href="#main-content" className="skip-link">
          {dictionary.a11y.skipToContent}
        </a>
        <div id="main-content" tabIndex={-1}>
          {children}
        </div>
      </AppProviders>
    </AccessibilityProvider>
  );
}
