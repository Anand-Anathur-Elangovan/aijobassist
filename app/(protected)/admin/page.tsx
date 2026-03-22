"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import { formatPrice } from "@/lib/billing";

// ── Super-admin whitelist ────────────────────────────────────────────────
const SUPER_ADMINS = [
  "kaviyasaravanan01@gmail.com",
  "anandanathurelangovan94@gmail.com",
];

// ── Types ────────────────────────────────────────────────────────────────
interface Stats {
  totalUsers: number;
  activeSubscriptions: number;
  trialUsers: number;
  paidUsers: number;
  totalRevenue: number;
  todaySignups: number;
  totalApplications: number;
  totalTasks: number;
  runningTasks: number;
  pendingTasks: number;
  failedTasks: number;
  todayUsage: number;
}

interface UserRow {
  user_id: string;
  full_name: string | null;
  phone: string | null;
  country: string | null;
  role: string;
  created_at: string;
  onboarding_done: boolean;
  email?: string;
  plan_slug?: string;
  sub_status?: string;
  billing_cycle?: string;
  trial_ends_at?: string;
}

interface TaskRow {
  id: string;
  user_id: string;
  type: string;
  status: string;
  progress: number | null;
  current_job: string | null;
  created_at: string;
  completed_at: string | null;
  error: string | null;
  output: Record<string, unknown> | null;
}

interface PaymentRow {
  id: string;
  user_id: string;
  amount: number;
  currency: string;
  status: string;
  razorpay_payment_id: string;
  created_at: string;
}

interface UsageRow {
  action_type: string;
  total_count: number;
}

type Tab = "overview" | "users" | "tasks" | "payments" | "usage";

export default function SuperAdminDashboard() {
  const { user } = useAuth();
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [stats, setStats] = useState<Stats | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [payments, setPayments] = useState<PaymentRow[]>([]);
  const [usageSummary, setUsageSummary] = useState<UsageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [userSearch, setUserSearch] = useState("");
  const [taskFilter, setTaskFilter] = useState<string>("ALL");

  // ── Auth check ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!user) return;
    if (SUPER_ADMINS.includes(user.email ?? "")) {
      setAuthorized(true);
    } else {
      // Also allow DB-level admin role
      supabase
        .from("user_profiles")
        .select("role")
        .eq("user_id", user.id)
        .single()
        .then(({ data }) => {
          setAuthorized(data?.role === "admin");
          if (data?.role !== "admin") setLoading(false);
        });
    }
  }, [user]);

  // ── Load all data ──────────────────────────────────────────────────────
  const loadAll = useCallback(async () => {
    if (!authorized) return;
    setLoading(true);
    await Promise.all([loadStats(), loadUsers(), loadTasks(), loadPayments(), loadUsage()]);
    setLoading(false);
  }, [authorized]);

  useEffect(() => {
    if (authorized) loadAll();
  }, [authorized, loadAll]);

  // ── Real-time task updates ─────────────────────────────────────────────
  useEffect(() => {
    if (!authorized) return;
    const channel = supabase
      .channel("admin-tasks-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks" }, (payload) => {
        const updated = payload.new as TaskRow;
        setTasks((prev) => {
          const idx = prev.findIndex((t) => t.id === updated.id);
          if (idx === -1) return [updated, ...prev];
          const next = [...prev];
          next[idx] = updated;
          return next;
        });
      })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [authorized]);

  async function loadStats() {
    const [
      { count: totalUsers },
      { count: activeSubs },
      { count: trialUsers },
      { count: totalApps },
      { count: totalTasks },
      { count: runningTasks },
      { count: pendingTasks },
      { count: failedTasks },
      { data: pmts },
    ] = await Promise.all([
      supabase.from("user_profiles").select("id", { count: "exact", head: true }),
      supabase.from("subscriptions").select("id", { count: "exact", head: true }).in("status", ["active", "past_due"]),
      supabase.from("subscriptions").select("id", { count: "exact", head: true }).eq("billing_cycle", "trial").eq("status", "active"),
      supabase.from("applications").select("id", { count: "exact", head: true }),
      supabase.from("tasks").select("id", { count: "exact", head: true }),
      supabase.from("tasks").select("id", { count: "exact", head: true }).eq("status", "RUNNING"),
      supabase.from("tasks").select("id", { count: "exact", head: true }).eq("status", "PENDING"),
      supabase.from("tasks").select("id", { count: "exact", head: true }).eq("status", "FAILED"),
      supabase.from("payments").select("amount").eq("status", "captured"),
    ]);

    const { data: paidSubs } = await supabase
      .from("subscriptions")
      .select("id")
      .in("status", ["active", "past_due"])
      .neq("billing_cycle", "trial");

    const today = new Date().toISOString().slice(0, 10);
    const [{ count: todaySignups }, { count: todayUsage }] = await Promise.all([
      supabase.from("user_profiles").select("id", { count: "exact", head: true }).gte("created_at", today),
      supabase.from("usage_events").select("id", { count: "exact", head: true }).gte("created_at", today),
    ]);

    const totalRevenue = (pmts ?? []).reduce((s: number, p: { amount: number }) => s + p.amount, 0);

    setStats({
      totalUsers: totalUsers ?? 0,
      activeSubscriptions: activeSubs ?? 0,
      trialUsers: trialUsers ?? 0,
      paidUsers: (paidSubs ?? []).length,
      totalRevenue,
      todaySignups: todaySignups ?? 0,
      totalApplications: totalApps ?? 0,
      totalTasks: totalTasks ?? 0,
      runningTasks: runningTasks ?? 0,
      pendingTasks: pendingTasks ?? 0,
      failedTasks: failedTasks ?? 0,
      todayUsage: todayUsage ?? 0,
    });
  }

  async function loadUsers() {
    const { data: profiles } = await supabase
      .from("user_profiles")
      .select("user_id, full_name, phone, country, role, created_at, onboarding_done")
      .order("created_at", { ascending: false })
      .limit(100);

    const enriched: UserRow[] = [];
    for (const p of profiles ?? []) {
      const { data: sub } = await supabase
        .from("subscriptions")
        .select("status, billing_cycle, trial_ends_at, plans(slug)")
        .eq("user_id", p.user_id)
        .in("status", ["active", "past_due"])
        .limit(1)
        .maybeSingle();

      // Try to get email from auth (may not work with anon key — fallback to name)
      enriched.push({
        ...p,
        email: p.full_name || p.user_id.slice(0, 8),
        plan_slug: (sub?.plans as unknown as { slug: string })?.slug ?? "free",
        sub_status: sub?.status ?? "none",
        billing_cycle: sub?.billing_cycle,
        trial_ends_at: sub?.trial_ends_at ?? undefined,
      });
    }
    setUsers(enriched);
  }

  async function loadTasks() {
    const { data } = await supabase
      .from("tasks")
      .select("id, user_id, type, status, progress, current_job, created_at, completed_at, error, output")
      .order("created_at", { ascending: false })
      .limit(200);
    setTasks((data as TaskRow[]) ?? []);
  }

  async function loadPayments() {
    const { data } = await supabase
      .from("payments")
      .select("id, user_id, amount, currency, status, razorpay_payment_id, created_at")
      .order("created_at", { ascending: false })
      .limit(100);
    setPayments((data as PaymentRow[]) ?? []);
  }

  async function loadUsage() {
    const { data } = await supabase
      .from("daily_usage")
      .select("action_type, count")
      .gte("usage_date", new Date().toISOString().slice(0, 10));

    const map: Record<string, number> = {};
    for (const r of data ?? []) {
      map[r.action_type] = (map[r.action_type] ?? 0) + r.count;
    }
    setUsageSummary(Object.entries(map).map(([action_type, total_count]) => ({ action_type, total_count })));
  }

  // ── Admin actions ──────────────────────────────────────────────────────
  async function promoteUser(userId: string) {
    await supabase.from("user_profiles").update({ role: "admin" }).eq("user_id", userId);
    loadUsers();
  }

  async function cancelTask(taskId: string) {
    await supabase.from("tasks").update({ status: "FAILED", error: "Cancelled by admin" }).eq("id", taskId);
    loadTasks();
  }

  // helpers
  const planBadge = (slug: string) => {
    const cls =
      slug === "premium" ? "bg-amber-400/10 text-amber-400" :
      slug === "normal"  ? "bg-blue-500/10 text-blue-400" :
      slug === "trial"   ? "bg-emerald-500/10 text-emerald-400" :
      "bg-slate-700/50 text-slate-400";
    return <span className={`px-2 py-0.5 rounded text-xs font-medium ${cls}`}>{slug}</span>;
  };

  const statusBadge = (status: string) => {
    const cls =
      status === "RUNNING" ? "bg-blue-500/10 text-blue-400" :
      status === "PENDING" ? "bg-amber-400/10 text-amber-400" :
      status === "DONE"    ? "bg-emerald-500/10 text-emerald-400" :
      status === "FAILED"  ? "bg-red-500/10 text-red-400" :
      "bg-slate-700/50 text-slate-400";
    return <span className={`px-2 py-0.5 rounded text-xs font-medium ${cls}`}>{status}</span>;
  };

  const timeAgo = (date: string) => {
    const diff = Date.now() - new Date(date).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  };

  // ── Render gates ───────────────────────────────────────────────────────
  if (authorized === null || loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (!authorized) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <h1 className="text-2xl font-display font-bold text-white mb-2">Access Denied</h1>
          <p className="text-slate-400">You don&apos;t have super-admin privileges.</p>
        </div>
      </div>
    );
  }

  const filteredUsers = userSearch
    ? users.filter(
        (u) =>
          (u.full_name ?? "").toLowerCase().includes(userSearch.toLowerCase()) ||
          u.user_id.toLowerCase().includes(userSearch.toLowerCase()) ||
          (u.email ?? "").toLowerCase().includes(userSearch.toLowerCase())
      )
    : users;

  const filteredTasks = taskFilter === "ALL" ? tasks : tasks.filter((t) => t.status === taskFilter);

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: "overview", label: "Overview", icon: "📊" },
    { id: "users", label: "Users", icon: "👥" },
    { id: "tasks", label: "Tasks", icon: "⚡" },
    { id: "payments", label: "Payments", icon: "💰" },
    { id: "usage", label: "Usage", icon: "📈" },
  ];

  const ACTION_LABELS: Record<string, string> = {
    auto_apply: "Auto Apply",
    semi_auto_apply: "Semi Auto",
    ai_tailor: "AI Tailor",
    gmail_send: "Gmail",
    cover_letter: "Cover Letter",
    jd_analysis: "JD Analysis",
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-display font-bold text-white">Super Admin Dashboard</h1>
          <p className="text-sm text-slate-500 font-mono mt-1">{user?.email}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadAll} className="btn-secondary text-xs px-3 py-1.5">
            🔄 Refresh All
          </button>
          <Link href="/admin/setup-guide" className="btn-primary text-xs px-3 py-1.5">
            📖 Agent Setup Guide
          </Link>
        </div>
      </div>

      {/* Tab nav */}
      <div className="flex gap-1 mb-8 overflow-x-auto pb-2">
        {TABS.map(({ id, label, icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all ${
              activeTab === id
                ? "bg-amber-400/10 text-amber-400 border border-amber-400/30"
                : "text-slate-400 hover:text-white hover:bg-slate-800"
            }`}
          >
            <span>{icon}</span> {label}
          </button>
        ))}
      </div>

      {/* ═══════════════════════ OVERVIEW TAB ═══════════════════════ */}
      {activeTab === "overview" && stats && (
        <div className="space-y-8">
          {/* Stat cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Total Users", value: stats.totalUsers, icon: "👥", color: "text-blue-400" },
              { label: "Active Subs", value: stats.activeSubscriptions, icon: "📋", color: "text-emerald-400" },
              { label: "Trial Users", value: stats.trialUsers, icon: "⏱️", color: "text-amber-400" },
              { label: "Paid Users", value: stats.paidUsers, icon: "💳", color: "text-violet-400" },
              { label: "Revenue", value: formatPrice(stats.totalRevenue), icon: "💰", color: "text-emerald-400" },
              { label: "Today Signups", value: stats.todaySignups, icon: "📈", color: "text-blue-400" },
              { label: "Applications", value: stats.totalApplications, icon: "📝", color: "text-slate-300" },
              { label: "Tasks Run", value: stats.totalTasks, icon: "⚡", color: "text-amber-400" },
            ].map(({ label, value, icon, color }) => (
              <div key={label} className="card">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">{icon}</span>
                  <span className="text-slate-500 text-xs font-mono uppercase tracking-wider">{label}</span>
                </div>
                <div className={`text-2xl font-display font-bold ${color}`}>{value}</div>
              </div>
            ))}
          </div>

          {/* Live status bars */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-400 text-sm">Running Tasks</span>
                <span className="font-mono text-lg text-blue-400 font-bold">{stats.runningTasks}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div className="bg-blue-500 h-2 rounded-full animate-pulse" style={{ width: `${Math.min(100, (stats.runningTasks / Math.max(1, stats.totalTasks)) * 100)}%` }} />
              </div>
            </div>
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-400 text-sm">Pending Tasks</span>
                <span className="font-mono text-lg text-amber-400 font-bold">{stats.pendingTasks}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div className="bg-amber-400 h-2 rounded-full" style={{ width: `${Math.min(100, (stats.pendingTasks / Math.max(1, stats.totalTasks)) * 100)}%` }} />
              </div>
            </div>
            <div className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-slate-400 text-sm">Failed Tasks</span>
                <span className="font-mono text-lg text-red-400 font-bold">{stats.failedTasks}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div className="bg-red-500 h-2 rounded-full" style={{ width: `${Math.min(100, (stats.failedTasks / Math.max(1, stats.totalTasks)) * 100)}%` }} />
              </div>
            </div>
          </div>

          {/* Today's usage by action */}
          <div className="card">
            <h3 className="text-white font-display font-semibold mb-4">Today&apos;s API Usage (all users)</h3>
            {usageSummary.length === 0 ? (
              <p className="text-slate-500 text-sm">No usage recorded today</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                {usageSummary.map((u) => (
                  <div key={u.action_type} className="bg-slate-800/50 rounded-lg p-3 text-center">
                    <p className="text-xs text-slate-400 mb-1">{ACTION_LABELS[u.action_type] ?? u.action_type}</p>
                    <p className="font-mono text-xl text-white font-bold">{u.total_count}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick user list */}
          <div className="card">
            <h3 className="text-white font-display font-semibold mb-4">Recent Users</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-800">
                    <th className="pb-2 font-medium">User</th>
                    <th className="pb-2 font-medium">Plan</th>
                    <th className="pb-2 font-medium">Role</th>
                    <th className="pb-2 font-medium">Joined</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {users.slice(0, 10).map((u) => (
                    <tr key={u.user_id} className="text-slate-300">
                      <td className="py-2.5 font-mono text-xs">{u.full_name || u.user_id.slice(0, 12)}</td>
                      <td className="py-2.5">{planBadge(u.plan_slug ?? "free")}</td>
                      <td className="py-2.5 text-xs">{u.role}</td>
                      <td className="py-2.5 text-xs text-slate-500">{timeAgo(u.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════ USERS TAB ═══════════════════════ */}
      {activeTab === "users" && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <input
              type="text"
              placeholder="Search users by name or ID…"
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              className="input flex-1 max-w-md"
            />
            <span className="text-slate-500 text-sm">{filteredUsers.length} users</span>
          </div>

          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-800">
                  <th className="pb-2 font-medium">Name</th>
                  <th className="pb-2 font-medium">User ID</th>
                  <th className="pb-2 font-medium">Plan</th>
                  <th className="pb-2 font-medium">Cycle</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Role</th>
                  <th className="pb-2 font-medium">Onboarded</th>
                  <th className="pb-2 font-medium">Joined</th>
                  <th className="pb-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredUsers.map((u) => (
                  <tr key={u.user_id} className="text-slate-300 hover:bg-slate-800/40">
                    <td className="py-2.5 font-medium">{u.full_name || "—"}</td>
                    <td className="py-2.5 font-mono text-xs text-slate-500">{u.user_id.slice(0, 12)}…</td>
                    <td className="py-2.5">{planBadge(u.plan_slug ?? "free")}</td>
                    <td className="py-2.5 text-xs">{u.billing_cycle ?? "—"}</td>
                    <td className="py-2.5 text-xs">{u.sub_status}</td>
                    <td className="py-2.5">
                      <span className={`text-xs ${u.role === "admin" ? "text-amber-400" : "text-slate-400"}`}>{u.role}</span>
                    </td>
                    <td className="py-2.5 text-xs">{u.onboarding_done ? "✅" : "❌"}</td>
                    <td className="py-2.5 text-xs text-slate-500">{new Date(u.created_at).toLocaleDateString()}</td>
                    <td className="py-2.5">
                      {u.role !== "admin" && (
                        <button
                          onClick={() => promoteUser(u.user_id)}
                          className="text-xs text-amber-400 hover:underline"
                        >
                          Make Admin
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ═══════════════════════ TASKS TAB ═══════════════════════ */}
      {activeTab === "tasks" && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            {["ALL", "RUNNING", "PENDING", "DONE", "FAILED"].map((f) => (
              <button
                key={f}
                onClick={() => setTaskFilter(f)}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-all ${
                  taskFilter === f
                    ? "bg-amber-400/10 text-amber-400 border border-amber-400/30"
                    : "text-slate-400 hover:text-white bg-slate-800/50"
                }`}
              >
                {f}
              </button>
            ))}
            <span className="ml-auto text-slate-500 text-sm">{filteredTasks.length} tasks</span>
          </div>

          <div className="space-y-3">
            {filteredTasks.map((t) => (
              <div key={t.id} className="card">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    {statusBadge(t.status)}
                    <span className="font-mono text-xs text-slate-400">{t.type}</span>
                    <span className="text-xs text-slate-600">id: {t.id.slice(0, 8)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">{timeAgo(t.created_at)}</span>
                    {(t.status === "RUNNING" || t.status === "PENDING") && (
                      <button
                        onClick={() => cancelTask(t.id)}
                        className="text-xs text-red-400 hover:underline"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>

                {/* Progress bar for running tasks */}
                {t.status === "RUNNING" && t.progress != null && (
                  <div className="mb-2">
                    <div className="flex justify-between text-xs text-slate-500 mb-1">
                      <span>{t.current_job ?? "Processing…"}</span>
                      <span>{t.progress}%</span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-1.5">
                      <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: `${t.progress}%` }} />
                    </div>
                  </div>
                )}

                {/* Error display */}
                {t.error && (
                  <p className="text-xs text-red-400 bg-red-500/5 px-3 py-1.5 rounded mt-1 break-all">{t.error}</p>
                )}

                {/* Output summary */}
                {t.output && (
                  <div className="text-xs text-slate-500 mt-1">
                    Applied: {String((t.output as Record<string, unknown>).applied_count ?? 0)} · {String((t.output as Record<string, unknown>).message ?? "")}
                  </div>
                )}

                <div className="text-xs text-slate-600 mt-1">
                  User: {t.user_id.slice(0, 12)}…
                  {t.completed_at && ` · Completed: ${new Date(t.completed_at).toLocaleString()}`}
                </div>
              </div>
            ))}
            {filteredTasks.length === 0 && (
              <p className="text-slate-500 text-center py-8">No tasks found</p>
            )}
          </div>
        </div>
      )}

      {/* ═══════════════════════ PAYMENTS TAB ═══════════════════════ */}
      {activeTab === "payments" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
            <div className="card">
              <p className="text-slate-500 text-xs font-mono uppercase mb-1">Total Revenue</p>
              <p className="text-2xl font-display font-bold text-emerald-400">{formatPrice(stats?.totalRevenue ?? 0)}</p>
            </div>
            <div className="card">
              <p className="text-slate-500 text-xs font-mono uppercase mb-1">Total Payments</p>
              <p className="text-2xl font-display font-bold text-white">{payments.length}</p>
            </div>
            <div className="card">
              <p className="text-slate-500 text-xs font-mono uppercase mb-1">Avg Order Value</p>
              <p className="text-2xl font-display font-bold text-amber-400">
                {payments.length > 0
                  ? formatPrice(Math.round(payments.reduce((s, p) => s + p.amount, 0) / payments.length))
                  : "₹0"}
              </p>
            </div>
          </div>

          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-800">
                  <th className="pb-2 font-medium">Razorpay ID</th>
                  <th className="pb-2 font-medium">User</th>
                  <th className="pb-2 font-medium">Amount</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {payments.map((p) => (
                  <tr key={p.id} className="text-slate-300">
                    <td className="py-2.5 font-mono text-xs">{p.razorpay_payment_id}</td>
                    <td className="py-2.5 font-mono text-xs text-slate-500">{p.user_id.slice(0, 12)}…</td>
                    <td className="py-2.5 font-medium text-emerald-400">{formatPrice(p.amount)}</td>
                    <td className="py-2.5">
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        p.status === "captured" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                      }`}>{p.status}</span>
                    </td>
                    <td className="py-2.5 text-xs text-slate-500">{new Date(p.created_at).toLocaleString()}</td>
                  </tr>
                ))}
                {payments.length === 0 && (
                  <tr><td colSpan={5} className="text-center py-8 text-slate-500">No payments yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ═══════════════════════ USAGE TAB ═══════════════════════ */}
      {activeTab === "usage" && (
        <div className="space-y-6">
          <div className="card">
            <h3 className="text-white font-display font-semibold mb-4">Today&apos;s Usage Across All Users</h3>
            <p className="text-slate-400 text-sm mb-4">Total API calls today: <span className="text-white font-bold">{stats?.todayUsage ?? 0}</span></p>
            {usageSummary.length === 0 ? (
              <p className="text-slate-500 text-sm">No usage recorded today</p>
            ) : (
              <div className="space-y-3">
                {usageSummary.map((u) => {
                  const max = Math.max(...usageSummary.map((x) => x.total_count), 1);
                  return (
                    <div key={u.action_type}>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-slate-300">{ACTION_LABELS[u.action_type] ?? u.action_type}</span>
                        <span className="text-white font-mono">{u.total_count}</span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-3">
                        <div
                          className="bg-amber-400 h-3 rounded-full transition-all"
                          style={{ width: `${(u.total_count / max) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="card">
            <h3 className="text-white font-display font-semibold mb-4">System Health</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-800/50 rounded-lg p-4 text-center">
                <p className="text-3xl font-bold text-blue-400">{stats?.runningTasks ?? 0}</p>
                <p className="text-xs text-slate-400 mt-1">Running Tasks</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-4 text-center">
                <p className="text-3xl font-bold text-amber-400">{stats?.pendingTasks ?? 0}</p>
                <p className="text-xs text-slate-400 mt-1">Pending Queue</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-4 text-center">
                <p className="text-3xl font-bold text-red-400">{stats?.failedTasks ?? 0}</p>
                <p className="text-xs text-slate-400 mt-1">Failed Tasks</p>
              </div>
              <div className="bg-slate-800/50 rounded-lg p-4 text-center">
                <p className="text-3xl font-bold text-emerald-400">{stats?.todayUsage ?? 0}</p>
                <p className="text-xs text-slate-400 mt-1">Today&apos;s API Calls</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
