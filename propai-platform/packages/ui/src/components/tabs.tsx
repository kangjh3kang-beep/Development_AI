"use client";

import {
  createContext,
  forwardRef,
  useContext,
  useState,
  type HTMLAttributes,
  type PropsWithChildren,
} from "react";
import { cn } from "../lib/cn";

interface TabsContextValue {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("Tabs 컴포넌트 내부에서 사용해야 합니다.");
  return ctx;
}

export type TabsProps = PropsWithChildren<
  HTMLAttributes<HTMLDivElement> & {
    defaultValue: string;
    onValueChange?: (value: string) => void;
  }
>;

export const Tabs = forwardRef<HTMLDivElement, TabsProps>(
  ({ children, className, defaultValue, onValueChange, ...props }, ref) => {
    const [activeTab, setActiveTab] = useState(defaultValue);

    const handleChange = (tab: string) => {
      setActiveTab(tab);
      onValueChange?.(tab);
    };

    return (
      <TabsContext.Provider value={{ activeTab, setActiveTab: handleChange }}>
        <div ref={ref} className={cn("w-full", className)} {...props}>
          {children}
        </div>
      </TabsContext.Provider>
    );
  },
);
Tabs.displayName = "Tabs";

export type TabsListProps = HTMLAttributes<HTMLDivElement>;

export const TabsList = forwardRef<HTMLDivElement, TabsListProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        role="tablist"
        className={cn(
          "inline-flex items-center gap-1 rounded-lg bg-[var(--surface-soft)] p-1",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);
TabsList.displayName = "TabsList";

export type TabsTriggerProps = HTMLAttributes<HTMLButtonElement> & {
  value: string;
};

export const TabsTrigger = forwardRef<HTMLButtonElement, TabsTriggerProps>(
  ({ children, className, value, ...props }, ref) => {
    const { activeTab, setActiveTab } = useTabsContext();
    const isActive = activeTab === value;

    return (
      <button
        ref={ref}
        role="tab"
        type="button"
        aria-selected={isActive}
        data-state={isActive ? "active" : "inactive"}
        className={cn(
          "inline-flex items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition",
          isActive
            ? "bg-[#ffffff] text-[var(--foreground)] shadow-sm"
            : "text-[var(--muted)] hover:text-[var(--foreground)]",
          className,
        )}
        onClick={() => setActiveTab(value)}
        {...props}
      >
        {children}
      </button>
    );
  },
);
TabsTrigger.displayName = "TabsTrigger";

export type TabsContentProps = HTMLAttributes<HTMLDivElement> & {
  value: string;
};

export const TabsContent = forwardRef<HTMLDivElement, TabsContentProps>(
  ({ children, className, value, ...props }, ref) => {
    const { activeTab } = useTabsContext();
    if (activeTab !== value) return null;

    return (
      <div
        ref={ref}
        role="tabpanel"
        className={cn("mt-2", className)}
        {...props}
      >
        {children}
      </div>
    );
  },
);
TabsContent.displayName = "TabsContent";
