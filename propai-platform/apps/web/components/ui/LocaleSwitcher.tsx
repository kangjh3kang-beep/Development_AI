"use client";

import { Select } from "@propai/ui";
import { startTransition } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAccessibility } from "@/hooks/useAccessibility";
import {
  localeCookieName,
  localeOptions,
  type Locale,
} from "@/i18n/config";

type LocaleSwitcherProps = {
  currentLocale: Locale;
  label: string;
};

export function LocaleSwitcher({
  currentLocale,
  label,
}: LocaleSwitcherProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { announceToScreenReader } = useAccessibility();

  const handleChange = (nextLocale: Locale) => {
    const segments = pathname.split("/").filter(Boolean);
    const nextLabel =
      localeOptions.find((option) => option.value === nextLocale)?.label ??
      nextLocale;

    document.cookie = `${localeCookieName}=${nextLocale}; path=/; samesite=lax`;
    announceToScreenReader(`${label} ${nextLabel}`);

    if (segments.length === 0) {
      startTransition(() => {
        router.replace(`/${nextLocale}`);
      });

      return;
    }

    segments[0] = nextLocale;

    startTransition(() => {
      router.replace(`/${segments.join("/")}`);
    });
  };

  return (
    <Select
      aria-label={label}
      defaultValue={currentLocale}
      label={label}
      name="locale-switcher"
      options={localeOptions.map((option) => ({
        label: option.label,
        value: option.value,
      }))}
      onValueChange={(value) => handleChange(value as Locale)}
    />
  );
}
