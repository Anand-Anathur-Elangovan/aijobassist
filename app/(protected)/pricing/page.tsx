"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import {
  getPlans,
  getUserSubscription,
  formatPrice,
  ACTION_LABELS,
  type Plan,
  type Subscription,
} from "@/lib/billing";

declare global {
  interface Window {
    Razorpay: new (options: Record<string, unknown>) => { open: () => void };
  }
}

export default function PricingPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [currentSub, setCurrentSub] = useState<Subscription | null>(null);
  const [billingCycle, setBillingCycle] = useState<"monthly" | "weekly">("monthly");
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState<string | null>(null);
  const [limits, setLimits] = useState<Record<string, Record<string, number>>>({});

  useEffect(() => {
    loadData();
  }, [user]);

  async function loadData() {
    const allPlans = await getPlans();
    setPlans(allPlans.filter((p) => p.slug !== "trial"));

    if (user) {
      const sub = await getUserSubscription(user.id);
      setCurrentSub(sub);
    }

    // Load limits for each plan
    const limMap: Record<string, Record<string, number>> = {};
    for (const plan of allPlans) {
      const { data } = await supabase
        .from("plan_limits")
        .select("action_type, daily_limit")
        .eq("plan_id", plan.id);
      limMap[plan.slug] = {};
      (data ?? []).forEach((l: { action_type: string; daily_limit: number }) => {
        limMap[plan.slug][l.action_type] = l.daily_limit;
      });
    }
    setLimits(limMap);
    setLoading(false);
  }

  async function handleSubscribe(planSlug: string) {
    if (!user) {
      router.push("/login");
      return;
    }

    if (planSlug === "free") return;

    setPurchasing(planSlug);
    try {
      const session = await supabase.auth.getSession();
      const token = session.data.session?.access_token;

      const res = await fetch("/api/billing/create-order", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ plan_slug: planSlug, billing_cycle: billingCycle }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error);

      // Open Razorpay checkout
      const options = {
        key: data.key_id,
        amount: data.amount,
        currency: data.currency,
        name: "VantaHire",
        description: `${data.plan_name} Plan - ${billingCycle}`,
        order_id: data.order_id,
        handler: async (response: { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }) => {
          // Verify payment
          const verifyRes = await fetch("/api/billing/verify-payment", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              ...response,
              plan_slug: planSlug,
              billing_cycle: billingCycle,
            }),
          });
          const verifyData = await verifyRes.json();
          if (verifyData.success) {
            router.push("/billing?success=true");
          }
        },
        prefill: {
          email: user.email,
        },
        theme: {
          color: "#fbbf24",
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err) {
      console.error("Subscribe error:", err);
    } finally {
      setPurchasing(null);
    }
  }

  const PLAN_ICONS: Record<string, string> = {
    free: "🆓",
    normal: "⚡",
    premium: "👑",
  };

  const PLAN_HIGHLIGHTS: Record<string, string> = {
    free: "Get started with basic tools",
    normal: "Most Popular",
    premium: "Maximum power for serious job seekers",
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 py-16 px-6">
      {/* Razorpay script */}
      <script src="https://checkout.razorpay.com/v1/checkout.js" async />

      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-display font-bold text-white mb-4">
            Choose Your <span className="text-amber-400">Plan</span>
          </h1>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto">
            Automate your job search with AI-powered resume tailoring, auto-apply, and email monitoring.
          </p>

          {/* Billing toggle */}
          <div className="mt-8 inline-flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1">
            <button
              onClick={() => setBillingCycle("monthly")}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                billingCycle === "monthly"
                  ? "bg-amber-400 text-slate-950"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setBillingCycle("weekly")}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                billingCycle === "weekly"
                  ? "bg-amber-400 text-slate-950"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Weekly
            </button>
          </div>
        </div>

        {/* Plan cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {plans.map((plan) => {
            const isCurrent = currentSub?.plans && (currentSub.plans as unknown as Plan).slug === plan.slug;
            const isPopular = plan.slug === "normal";
            const price = billingCycle === "weekly" ? plan.price_weekly : plan.price_monthly;
            const planLimits = limits[plan.slug] ?? {};

            return (
              <div
                key={plan.id}
                className={`relative rounded-xl border p-8 flex flex-col transition-all ${
                  isPopular
                    ? "border-amber-400/50 bg-slate-900/80 shadow-lg shadow-amber-400/5 scale-[1.02]"
                    : "border-slate-800 bg-slate-900/50"
                } ${isCurrent ? "ring-2 ring-amber-400" : ""}`}
              >
                {isPopular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-amber-400 text-slate-950 text-xs font-bold rounded-full">
                    MOST POPULAR
                  </div>
                )}

                {isCurrent && (
                  <div className="absolute -top-3 right-4 px-3 py-1 bg-emerald-500 text-white text-xs font-bold rounded-full">
                    CURRENT
                  </div>
                )}

                <div className="text-3xl mb-3">{PLAN_ICONS[plan.slug] ?? "📦"}</div>
                <h3 className="text-xl font-display font-bold text-white">{plan.name}</h3>
                <p className="text-slate-400 text-sm mt-1 mb-4">{PLAN_HIGHLIGHTS[plan.slug] ?? plan.description}</p>

                <div className="mb-6">
                  {price > 0 ? (
                    <>
                      <span className="text-3xl font-display font-bold text-white">
                        {formatPrice(price)}
                      </span>
                      <span className="text-slate-400 text-sm">/{billingCycle === "weekly" ? "week" : "month"}</span>
                    </>
                  ) : (
                    <span className="text-3xl font-display font-bold text-white">Free</span>
                  )}
                </div>

                {/* Limits */}
                <div className="space-y-3 flex-1 mb-6">
                  {Object.entries(ACTION_LABELS).map(([key, label]) => {
                    const limit = planLimits[key];
                    return (
                      <div key={key} className="flex items-center justify-between text-sm">
                        <span className="text-slate-300">{label}</span>
                        <span className={`font-mono ${limit === 0 ? "text-red-400" : limit > 50 ? "text-emerald-400" : "text-amber-400"}`}>
                          {limit === 0 ? "—" : limit === 999 ? "∞" : `${limit}/day`}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Features */}
                <div className="space-y-2 mb-6 border-t border-slate-800 pt-4">
                  {Object.entries(plan.features as Record<string, boolean>).map(([key, val]) => {
                    if (key === "trial_days") return null;
                    const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
                    return (
                      <div key={key} className="flex items-center gap-2 text-sm">
                        <span className={val ? "text-emerald-400" : "text-red-400"}>
                          {val ? "✓" : "✕"}
                        </span>
                        <span className={val ? "text-slate-300" : "text-slate-500"}>{label}</span>
                      </div>
                    );
                  })}
                </div>

                <button
                  onClick={() => handleSubscribe(plan.slug)}
                  disabled={isCurrent || purchasing === plan.slug || plan.slug === "free"}
                  className={`w-full py-3 rounded-lg font-semibold text-sm transition-all ${
                    isPopular
                      ? "bg-amber-400 text-slate-950 hover:bg-amber-300"
                      : plan.slug === "premium"
                      ? "bg-white text-slate-950 hover:bg-slate-100"
                      : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                  } disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {isCurrent
                    ? "Current Plan"
                    : purchasing === plan.slug
                    ? "Processing..."
                    : plan.slug === "free"
                    ? "Free Forever"
                    : `Upgrade to ${plan.name}`}
                </button>
              </div>
            );
          })}
        </div>

        {/* FAQ */}
        <div className="mt-20 max-w-3xl mx-auto">
          <h2 className="text-2xl font-display font-bold text-white text-center mb-8">
            Frequently Asked Questions
          </h2>
          <div className="space-y-4">
            {[
              { q: "What happens after my free trial?", a: "After 10 days, you'll automatically move to the Free plan. No charges unless you upgrade." },
              { q: "Can I cancel anytime?", a: "Yes! Cancel from your billing page. You'll keep access until the end of your billing period." },
              { q: "What payment methods are accepted?", a: "We accept UPI, credit/debit cards, net banking, and wallets via Razorpay." },
              { q: "What does Auto Apply do?", a: "Auto Apply uses AI to automatically submit job applications on LinkedIn and Naukri with tailored resumes." },
              { q: "Is my data secure?", a: "Yes. All data is encrypted, stored on Supabase with row-level security. We never share your information." },
            ].map(({ q, a }) => (
              <details key={q} className="group card cursor-pointer">
                <summary className="font-semibold text-white list-none flex items-center justify-between">
                  {q}
                  <span className="text-amber-400 group-open:rotate-45 transition-transform">+</span>
                </summary>
                <p className="text-slate-400 text-sm mt-3">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
