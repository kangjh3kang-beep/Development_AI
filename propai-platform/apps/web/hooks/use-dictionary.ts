"use client";

import { useEffect, useState } from "react";
import type { Locale } from "@/i18n/config";
import type { CommonDictionary } from "@/i18n/get-dictionary";

export function useDictionary(locale: Locale) {
  const [dictionary, setDictionary] = useState<CommonDictionary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);

    async function load() {
      try {
        // In a real Next.js app, we might fetch this from a JSON endpoint or an API
        // For this architecture, we can fetch the public locale file directly
        const response = await fetch(`/locales/${locale}/common.json`);
        if (!response.ok) {
          throw new Error(`Failed to load dictionary: ${response.statusText}`);
        }
        const data = await response.json();
        if (isMounted) {
          setDictionary(data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err : new Error("Unknown error"));
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    load();

    return () => {
      isMounted = false;
    };
  }, [locale]);

  return { dictionary, isLoading, error };
}
