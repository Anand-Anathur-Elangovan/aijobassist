// ──────────────────────────────────────────────────────────────
// lib/billing.ts — Subscription, quota & Razorpay helpers
// ──────────────────────────────────────────────────────────────

import { supabase } from "./supabase";

// ── Types ──
export interface Plan {
  id: string;
  slug: string;
  name: string;
  description: string;
  price_monthly: number;
  price_weekly: number;
  is_active: boolean;
  sort_order: number;
  features: Record<string, boolean | number>;
}

export interface PlanLimit {
  action_type: string;
  daily_limit: number;
}

export interface Subscription {
  id: string;
  user_id: string;
  plan_id: string;
  status: string;
  billing_cycle: string;
  razorpay_subscription_id?: string;
  trial_ends_at?: string;
  current_period_start: string;
  current_period_end?: string;
  cancelled_at?: string;
  created_at: string;
  plans?: Plan;
}

export interface QuotaCheck {
  allowed: boolean;
  used: number;
  limit: number;
  remaining: number;
}

export interface UsageSummary {
  action_type: string;
  used: number;
  limit: number;
  remaining: number;
}

// ── Plans ──

export async function getPlans(): Promise<Plan[]> {
  const { data } = await supabase
    .from("plans")
    .select("*")
    .eq("is_active", true)
    .order("sort_order");
  return (data ?? []) as Plan[];
}

export async function getPlanLimits(planId: string): Promise<PlanLimit[]> {
  const { data } = await supabase
    .from("plan_limits")
    .select("action_type, daily_limit")
    .eq("plan_id", planId);
  return (data ?? []) as PlanLimit[];
}

// ── Subscriptions ──

export async function getUserSubscription(userId: string): Promise<Subscription | null> {
  const { data } = await supabase
    .from("subscriptions")
    .select("*")
    .eq("user_id", userId)
    .in("status", ["active", "past_due"])
    .order("created_at", { ascending: false })
    .limit(1)
    .single();
  if (!data) return null;

  // Fetch the plan separately (avoids PostgREST embedded resource 406)
  const { data: plan } = await supabase
    .from("plans")
    .select("*")
    .eq("id", data.plan_id)
    .single();

  return { ...data, plans: plan } as Subscription;
}

export async function getSubscriptionWithPlan(userId: string) {
  const sub = await getUserSubscription(userId);
  if (!sub) {
    // Default to free plan info
    const { data: freePlan } = await supabase
      .from("plans")
      .select("*")
      .eq("slug", "free")
      .single();
    return { subscription: null, plan: freePlan as Plan | null, isTrialExpired: false };
  }

  const plan = sub.plans as unknown as Plan;
  const isTrialExpired = plan?.slug === "trial" &&
    sub.trial_ends_at != null &&
    new Date(sub.trial_ends_at) < new Date();

  return { subscription: sub, plan, isTrialExpired };
}

// ── Quota ──

export async function checkQuota(userId: string, actionType: string): Promise<QuotaCheck> {
  const { data, error } = await supabase.rpc("check_quota", {
    p_user_id: userId,
    p_action_type: actionType,
  });
  if (error || !data) return { allowed: false, used: 0, limit: 0, remaining: 0 };
  return data as QuotaCheck;
}

export async function incrementUsage(userId: string, actionType: string): Promise<number> {
  const { data } = await supabase.rpc("increment_usage", {
    p_user_id: userId,
    p_action_type: actionType,
  });
  return (data as number) ?? 0;
}

export async function getDailyUsageSummary(userId: string): Promise<UsageSummary[]> {
  const sub = await getUserSubscription(userId);

  // Get plan limits
  let planId: string | undefined;
  if (sub) {
    const plan = sub.plans as unknown as Plan;
    const isTrialExpired = plan?.slug === "trial" &&
      sub.trial_ends_at != null &&
      new Date(sub.trial_ends_at) < new Date();
    planId = isTrialExpired ? undefined : sub.plan_id;
  }

  if (!planId) {
    const { data: freePlan } = await supabase
      .from("plans")
      .select("id")
      .eq("slug", "free")
      .single();
    planId = freePlan?.id;
  }

  if (!planId) return [];

  const { data: limits } = await supabase
    .from("plan_limits")
    .select("action_type, daily_limit")
    .eq("plan_id", planId);

  const { data: usage } = await supabase
    .from("daily_usage")
    .select("action_type, count")
    .eq("user_id", userId)
    .eq("usage_date", new Date().toISOString().slice(0, 10));

  const usageMap: Record<string, number> = {};
  (usage ?? []).forEach((u: { action_type: string; count: number }) => {
    usageMap[u.action_type] = u.count;
  });

  return (limits ?? []).map((l: { action_type: string; daily_limit: number }) => ({
    action_type: l.action_type,
    used: usageMap[l.action_type] ?? 0,
    limit: l.daily_limit,
    remaining: Math.max(0, l.daily_limit - (usageMap[l.action_type] ?? 0)),
  }));
}

// ── Payments ──

export async function getPaymentHistory(userId: string) {
  const { data } = await supabase
    .from("payments")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });
  return data ?? [];
}

// ── Profile ──

export async function getUserProfile(userId: string) {
  const { data } = await supabase
    .from("user_profiles")
    .select("*")
    .eq("user_id", userId)
    .single();
  return data;
}

export async function updateUserProfile(userId: string, updates: Record<string, unknown>) {
  return supabase
    .from("user_profiles")
    .upsert({ user_id: userId, ...updates, updated_at: new Date().toISOString() }, { onConflict: "user_id" });
}

// ── Plan label helpers ──

export const ACTION_LABELS: Record<string, string> = {
  auto_apply: "Auto Apply",
  semi_auto: "Semi-Auto Apply",
  ai_tailor: "AI Resume Tailoring",
  gmail_scan: "Gmail Monitoring",
  cover_letter: "Cover Letter Generation",
  jd_analysis: "JD Analysis",
};

export function formatPrice(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN")}`;
}

export function getPlanBadgeColor(slug: string): string {
  switch (slug) {
    case "premium": return "bg-amber-400 text-slate-950";
    case "normal":  return "bg-blue-500 text-white";
    case "trial":   return "bg-emerald-500 text-white";
    default:        return "bg-slate-700 text-slate-300";
  }
}

export function getRemainingTrialDays(trialEndsAt: string | undefined): number {
  if (!trialEndsAt) return 0;
  const diff = new Date(trialEndsAt).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}
