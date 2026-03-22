"use client";

import { useEffect, useState, createContext, useContext, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  getSubscriptionWithPlan,
  getDailyUsageSummary,
  type Plan,
  type Subscription,
  type UsageSummary,
} from "@/lib/billing";
import Link from "next/link";

// ── Subscription Context ──
interface SubscriptionState {
  plan: Plan | null;
  subscription: Subscription | null;
  isTrialExpired: boolean;
  usage: UsageSummary[];
  loading: boolean;
  refresh: () => Promise<void>;
  canUse: (actionType: string) => boolean;
  getRemaining: (actionType: string) => number;
}

const SubscriptionContext = createContext<SubscriptionState>({
  plan: null,
  subscription: null,
  isTrialExpired: false,
  usage: [],
  loading: true,
  refresh: async () => {},
  canUse: () => true,
  getRemaining: () => 0,
});

const SUPER_ADMINS = [
  "kaviyasaravanan01@gmail.com",
  "anandanathurelangovan94@gmail.com",
];

export function SubscriptionProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const isSuperAdmin = !!(user?.email && SUPER_ADMINS.includes(user.email));
  const [plan, setPlan] = useState<Plan | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [isTrialExpired, setIsTrialExpired] = useState(false);
  const [usage, setUsage] = useState<UsageSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!user) {
      setLoading(false);
      return;
    }

    try {
      const { subscription: sub, plan: p, isTrialExpired: expired } = await getSubscriptionWithPlan(user.id);
      setPlan(p);
      setSubscription(sub);
      setIsTrialExpired(expired);

      const usageSummary = await getDailyUsageSummary(user.id);
      setUsage(usageSummary);
    } catch {
      // silently fail
    }
    setLoading(false);
  }, [user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function canUse(actionType: string): boolean {
    if (isSuperAdmin) return true;
    const u = usage.find((x) => x.action_type === actionType);
    if (!u) return true; // no limit defined
    return u.remaining > 0;
  }

  function getRemaining(actionType: string): number {
    if (isSuperAdmin) return 999;
    const u = usage.find((x) => x.action_type === actionType);
    return u?.remaining ?? 0;
  }

  return (
    <SubscriptionContext.Provider
      value={{ plan, subscription, isTrialExpired: isSuperAdmin ? false : isTrialExpired, usage, loading, refresh, canUse, getRemaining }}
    >
      {children}
    </SubscriptionContext.Provider>
  );
}

export const useSubscription = () => useContext(SubscriptionContext);

// ── Feature Gate Component ──
export function FeatureGate({
  feature,
  actionType,
  children,
  fallback,
}: {
  feature?: string;
  actionType?: string;
  children: React.ReactNode;
  fallback?: React.ReactNode;
}) {
  const { plan, isTrialExpired, canUse } = useSubscription();

  // Check feature availability
  if (feature && plan) {
    const features = plan.features as Record<string, boolean>;
    if (!features[feature]) {
      return (
        fallback ?? (
          <UpgradePrompt message={`${feature.replace(/_/g, " ")} is not available on the ${plan.name} plan.`} />
        )
      );
    }
  }

  // Check quota
  if (actionType && !canUse(actionType)) {
    return (
      fallback ?? (
        <QuotaExceeded actionType={actionType} />
      )
    );
  }

  // Check trial expiry
  if (isTrialExpired && feature) {
    return fallback ?? <UpgradePrompt message="Your free trial has expired." />;
  }

  return <>{children}</>;
}

// ── Upgrade Prompt ──
export function UpgradePrompt({ message }: { message: string }) {
  return (
    <div className="card border-amber-400/20 bg-amber-400/5 text-center py-8">
      <div className="text-3xl mb-3">🔒</div>
      <h3 className="text-lg font-display font-bold text-white mb-2">Upgrade Required</h3>
      <p className="text-slate-400 text-sm mb-4">{message}</p>
      <Link
        href="/pricing"
        className="inline-block px-6 py-2.5 bg-amber-400 text-slate-950 font-semibold rounded-lg hover:bg-amber-300 transition-all"
      >
        View Plans
      </Link>
    </div>
  );
}

// ── Quota Exceeded ──
export function QuotaExceeded({ actionType }: { actionType: string }) {
  const labels: Record<string, string> = {
    auto_apply: "Auto Apply",
    semi_auto: "Semi-Auto Apply",
    ai_tailor: "AI Resume Tailoring",
    gmail_scan: "Gmail Monitoring",
    cover_letter: "Cover Letter Generation",
    jd_analysis: "JD Analysis",
  };

  return (
    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-center">
      <p className="text-red-400 font-medium mb-1">Daily Limit Reached</p>
      <p className="text-slate-400 text-sm mb-3">
        You&apos;ve used all your {labels[actionType] ?? actionType} quota for today.
      </p>
      <Link
        href="/pricing"
        className="text-amber-400 text-sm hover:underline"
      >
        Upgrade for more →
      </Link>
    </div>
  );
}

// ── Usage Badge (for NavBar or dashboard) ──
export function UsageBadge({ actionType, label }: { actionType: string; label: string }) {
  const { usage } = useSubscription();
  const u = usage.find((x) => x.action_type === actionType);
  if (!u) return null;

  const pct = u.limit > 0 ? (u.used / u.limit) * 100 : 0;
  const isLow = pct > 80;

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-slate-400">{label}:</span>
      <span className={`font-mono ${isLow ? "text-red-400" : "text-slate-300"}`}>
        {u.remaining}/{u.limit === 999 ? "∞" : u.limit}
      </span>
    </div>
  );
}

// ── Trial Banner ──
export function TrialBanner() {
  const { plan, subscription, isTrialExpired } = useSubscription();

  if (!plan || plan.slug !== "trial" || isTrialExpired) return null;

  const trialEnd = subscription?.trial_ends_at;
  if (!trialEnd) return null;

  const daysLeft = Math.max(0, Math.ceil((new Date(trialEnd).getTime() - Date.now()) / (1000 * 60 * 60 * 24)));

  return (
    <div className="bg-amber-400/10 border-b border-amber-400/20 px-6 py-2 text-center text-sm">
      <span className="text-amber-400 font-medium">🎉 Free Trial</span>
      <span className="text-slate-300 ml-2">
        {daysLeft} day{daysLeft !== 1 ? "s" : ""} remaining •
      </span>
      <Link href="/pricing" className="text-amber-400 ml-1 hover:underline">
        Upgrade now
      </Link>
    </div>
  );
}
