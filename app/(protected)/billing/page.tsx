"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import {
  getSubscriptionWithPlan,
  getDailyUsageSummary,
  getPaymentHistory,
  getRemainingTrialDays,
  formatPrice,
  ACTION_LABELS,
  getPlanBadgeColor,
  type Plan,
  type Subscription,
  type UsageSummary,
} from "@/lib/billing";
import { supabase } from "@/lib/supabase";

export default function BillingPage() {
  const { user } = useAuth();
  const searchParams = useSearchParams();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [isTrialExpired, setIsTrialExpired] = useState(false);
  const [usage, setUsage] = useState<UsageSummary[]>([]);
  const [payments, setPayments] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  useEffect(() => {
    if (searchParams.get("success") === "true") {
      setShowSuccess(true);
      setTimeout(() => setShowSuccess(false), 5000);
    }
  }, [searchParams]);

  useEffect(() => {
    if (user) loadData();
  }, [user]);

  async function loadData() {
    if (!user) return;
    const { subscription, plan: p, isTrialExpired: expired } = await getSubscriptionWithPlan(user.id);
    setSub(subscription);
    setPlan(p);
    setIsTrialExpired(expired);

    const usageSummary = await getDailyUsageSummary(user.id);
    setUsage(usageSummary);

    const paymentHist = await getPaymentHistory(user.id);
    setPayments(paymentHist);

    setLoading(false);
  }

  async function handleCancel() {
    if (!confirm("Are you sure you want to cancel your subscription?")) return;
    setCancelling(true);
    const session = await supabase.auth.getSession();
    await fetch("/api/billing/subscription", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.data.session?.access_token}`,
      },
      body: JSON.stringify({ action: "cancel" }),
    });
    await loadData();
    setCancelling(false);
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const planSlug = plan?.slug ?? "free";
  const trialDays = sub?.trial_ends_at ? getRemainingTrialDays(sub.trial_ends_at) : 0;
  const isPaid = planSlug === "normal" || planSlug === "premium";

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 space-y-8">
      {/* Success banner */}
      {showSuccess && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4 text-emerald-400 text-sm flex items-center gap-2 animate-fadeUp">
          ✓ Payment successful! Your plan has been upgraded.
        </div>
      )}

      {/* Current plan card */}
      <div className="card">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-display font-bold text-white">Current Plan</h2>
          <span className={`px-3 py-1 rounded-full text-xs font-bold ${getPlanBadgeColor(planSlug)}`}>
            {plan?.name ?? "Free"}
          </span>
        </div>

        {planSlug === "trial" && !isTrialExpired && (
          <div className="bg-amber-400/10 border border-amber-400/20 rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between">
              <span className="text-amber-400 font-medium">Free Trial Active</span>
              <span className="text-white font-mono">{trialDays} days remaining</span>
            </div>
            <div className="mt-2 h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-amber-400 rounded-full transition-all"
                style={{ width: `${Math.max(5, (trialDays / 10) * 100)}%` }}
              />
            </div>
          </div>
        )}

        {isTrialExpired && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-4">
            <p className="text-red-400 font-medium">Your trial has expired.</p>
            <p className="text-slate-400 text-sm mt-1">
              Upgrade to continue using all features.
            </p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-500">Status</span>
            <p className="text-white font-medium capitalize">{sub?.status ?? "active"}</p>
          </div>
          <div>
            <span className="text-slate-500">Billing Cycle</span>
            <p className="text-white font-medium capitalize">{sub?.billing_cycle ?? "—"}</p>
          </div>
          <div>
            <span className="text-slate-500">Period Ends</span>
            <p className="text-white font-medium">
              {sub?.current_period_end ? new Date(sub.current_period_end).toLocaleDateString() : "—"}
            </p>
          </div>
          <div>
            <span className="text-slate-500">Monthly Price</span>
            <p className="text-white font-medium">
              {plan && plan.price_monthly > 0 ? formatPrice(plan.price_monthly) : "Free"}
            </p>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <Link
            href="/pricing"
            className="btn-primary text-sm"
          >
            {isPaid ? "Change Plan" : "Upgrade"}
          </Link>
          {isPaid && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="px-4 py-2 rounded-lg border border-red-500/30 text-red-400 text-sm hover:bg-red-500/10 transition-all disabled:opacity-50"
            >
              {cancelling ? "Cancelling..." : "Cancel Subscription"}
            </button>
          )}
        </div>
      </div>

      {/* Usage today */}
      <div className="card">
        <h2 className="text-xl font-display font-bold text-white mb-6">Today&apos;s Usage</h2>
        <div className="space-y-4">
          {usage.map((u) => {
            const pct = u.limit > 0 ? Math.min(100, (u.used / u.limit) * 100) : 0;
            const isClose = pct > 80;
            return (
              <div key={u.action_type}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-300">{ACTION_LABELS[u.action_type] ?? u.action_type}</span>
                  <span className={`text-sm font-mono ${isClose ? "text-red-400" : "text-slate-400"}`}>
                    {u.used} / {u.limit === 999 ? "∞" : u.limit}
                  </span>
                </div>
                <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      isClose ? "bg-red-500" : pct > 50 ? "bg-amber-400" : "bg-emerald-500"
                    }`}
                    style={{ width: `${Math.max(2, pct)}%` }}
                  />
                </div>
              </div>
            );
          })}
          {usage.length === 0 && <p className="text-slate-500 text-sm">No usage data yet today.</p>}
        </div>
      </div>

      {/* Payment history */}
      <div className="card">
        <h2 className="text-xl font-display font-bold text-white mb-6">Payment History</h2>
        {payments.length === 0 ? (
          <p className="text-slate-500 text-sm">No payments yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-800">
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Amount</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {payments.map((p: Record<string, unknown>) => (
                  <tr key={p.id as string} className="text-slate-300">
                    <td className="py-3">{new Date(p.created_at as string).toLocaleDateString()}</td>
                    <td className="py-3 font-mono">{formatPrice(p.amount as number)}</td>
                    <td className="py-3">
                      <span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 rounded text-xs">
                        {p.status as string}
                      </span>
                    </td>
                    <td className="py-3 font-mono text-xs text-slate-500">
                      {(p.razorpay_payment_id as string)?.slice(0, 16)}...
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
