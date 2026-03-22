"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";

// ── Types ─────────────────────────────────────────────────────────────────
type StageCount = { stage: string; count: number };
type CompanyCount = { company: string; count: number };
type DailyCount = { date: string; count: number };

type Stats = {
  total:           number;
  interviews:      number;
  offers:          number;
  rejected:        number;
  pending:         number;
  successRate:     number;
  avgResponseDays: number;
};

// ── Bar component ─────────────────────────────────────────────────────────
function HBar({ label, count, max, color }: { label: string; count: number; max: number; color: string }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-xs text-slate-400 w-24 text-right shrink-0">{label}</span>
      <div className="flex-1 h-4 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-xs text-slate-300 w-6 text-right shrink-0">{count}</span>
    </div>
  );
}

// ── Mini bar chart for daily activity ────────────────────────────────────
function MiniBar({ value, max, date }: { value: number; max: number; date: string }) {
  const h = max > 0 ? Math.max(4, Math.round((value / max) * 80)) : 4;
  return (
    <div className="flex flex-col items-center gap-1 group relative">
      <div
        className="w-6 bg-amber-400/60 group-hover:bg-amber-400 rounded-t transition-colors"
        style={{ height: `${h}px` }}
      />
      <span className="font-mono text-[10px] text-slate-600 group-hover:text-slate-400">
        {new Date(date).toLocaleDateString("en", { weekday: "short" })}
      </span>
      {value > 0 && (
        <span className="absolute bottom-8 bg-slate-700 text-white text-xs px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          {value}
        </span>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
export default function AnalyticsPage() {
  const { user } = useAuth();

  const [stats,      setStats   ] = useState<Stats | null>(null);
  const [stageCounts, setStageCounts] = useState<StageCount[]>([]);
  const [topCompanies, setTopCompanies] = useState<CompanyCount[]>([]);
  const [dailyCounts, setDailyCounts] = useState<DailyCount[]>([]);
  const [loading,    setLoading ] = useState(true);

  const load = useCallback(async () => {
    if (!user) return;

    const { data: apps } = await supabase
      .from("applications")
      .select("id, stage, applied_at, jobs(company)")
      .eq("user_id", user.id);

    if (!apps) { setLoading(false); return; }

    // Stage breakdown
    const stageMap: Record<string, number> = {};
    apps.forEach((a) => { stageMap[a.stage] = (stageMap[a.stage] || 0) + 1; });
    const stageArr = Object.entries(stageMap)
      .map(([stage, count]) => ({ stage, count }))
      .sort((a, b) => b.count - a.count);
    setStageCounts(stageArr);

    // Company breakdown
    const compMap: Record<string, number> = {};
    apps.forEach((a) => {
      const co = (a.jobs as any)?.company ?? "Unknown";
      compMap[co] = (compMap[co] || 0) + 1;
    });
    setTopCompanies(
      Object.entries(compMap)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([company, count]) => ({ company, count })),
    );

    // Daily counts — last 7 days
    const days: DailyCount[] = [];
    for (let i = 6; i >= 0; i--) {
      const d  = new Date();
      d.setDate(d.getDate() - i);
      const key  = d.toISOString().slice(0, 10);
      const count = apps.filter((a) => a.applied_at.slice(0, 10) === key).length;
      days.push({ date: key, count });
    }
    setDailyCounts(days);

    // Summary stats
    const total      = apps.length;
    const interviews = apps.filter((a) => ["INTERVIEW", "OFFER"].includes(a.stage)).length;
    const offers     = apps.filter((a) => a.stage === "OFFER").length;
    const rejected   = apps.filter((a) => a.stage === "REJECTED").length;
    const pending    = apps.filter((a) => ["APPLIED", "SCREENING"].includes(a.stage)).length;
    const successRate = total > 0 ? Math.round((interviews / total) * 100) : 0;
    setStats({ total, interviews, offers, rejected, pending, successRate, avgResponseDays: 5 });
    setLoading(false);
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const STAT_CARDS = stats
    ? [
        { label: "Total Applied",   value: stats.total.toString(),       color: "text-white",         sub: "all time" },
        { label: "Interviews",       value: stats.interviews.toString(),  color: "text-purple-400",    sub: "& offer stages" },
        { label: "Offers",           value: stats.offers.toString(),      color: "text-emerald-400",   sub: "🎉" },
        { label: "Rejected",         value: stats.rejected.toString(),    color: "text-red-400",       sub: "keep going" },
        { label: "Pending",          value: stats.pending.toString(),     color: "text-yellow-400",    sub: "waiting for response" },
        { label: "Interview Rate",   value: `${stats.successRate}%`,      color: "text-amber-400",     sub: "applications → interview" },
      ]
    : [];

  const STAGE_COLORS: Record<string, string> = {
    APPLIED:   "bg-blue-500",
    SCREENING: "bg-yellow-500",
    INTERVIEW: "bg-purple-500",
    OFFER:     "bg-emerald-500",
    REJECTED:  "bg-red-500",
  };

  const maxStage   = Math.max(...stageCounts.map((s) => s.count), 1);
  const maxCompany = Math.max(...topCompanies.map((c) => c.count), 1);
  const maxDaily   = Math.max(...dailyCounts.map((d) => d.count), 1);

  // ─────────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-1">Insights</p>
        <h1 className="font-display font-bold text-3xl text-white">Analytics</h1>
        <p className="text-slate-400 font-body text-sm mt-1">
          Track your job search performance and optimise your strategy.
        </p>
      </div>

      {loading ? (
        <div className="card text-center py-12">
          <p className="font-mono text-slate-500 animate-pulse text-sm">Loading analytics…</p>
        </div>
      ) : !stats || stats.total === 0 ? (
        <div className="card border-dashed text-center py-12">
          <p className="text-slate-500 font-body text-sm">
            No applications tracked yet. Start applying to see your stats here.
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {/* Stat cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {STAT_CARDS.map((card) => (
              <div key={card.label} className="card">
                <p className="font-mono text-xs text-slate-500 uppercase tracking-wider mb-2">{card.label}</p>
                <p className={`font-display font-bold text-3xl ${card.color} mb-0.5`}>{card.value}</p>
                <p className="font-body text-xs text-slate-600">{card.sub}</p>
              </div>
            ))}
          </div>

          {/* Two column layout */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Stage breakdown */}
            <div className="card space-y-3">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-wider mb-1">By Stage</p>
              {stageCounts.map((s) => (
                <HBar
                  key={s.stage}
                  label={s.stage}
                  count={s.count}
                  max={maxStage}
                  color={STAGE_COLORS[s.stage] || "bg-slate-500"}
                />
              ))}
            </div>

            {/* Top companies */}
            <div className="card space-y-3">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-wider mb-1">Top Companies</p>
              {topCompanies.map((c) => (
                <HBar
                  key={c.company}
                  label={c.company}
                  count={c.count}
                  max={maxCompany}
                  color="bg-amber-400/70"
                />
              ))}
            </div>
          </div>

          {/* Daily activity */}
          <div className="card">
            <p className="font-mono text-xs text-slate-400 uppercase tracking-wider mb-4">Applications — Last 7 Days</p>
            <div className="flex items-end gap-3 justify-around h-24">
              {dailyCounts.map((d) => (
                <MiniBar key={d.date} value={d.count} max={maxDaily} date={d.date} />
              ))}
            </div>
          </div>

          {/* Tips based on data */}
          <div className="card bg-amber-400/5 border-amber-400/20">
            <p className="font-mono text-xs text-amber-400 uppercase tracking-wider mb-3">💡 Insights</p>
            <ul className="space-y-2">
              {stats.successRate < 10 && (
                <li className="text-slate-300 text-sm">→ Your interview rate is below 10%. Consider using Resume Studio to tailor your resume for each application.</li>
              )}
              {stats.pending > 10 && (
                <li className="text-slate-300 text-sm">→ You have {stats.pending} pending applications. Send follow-up emails for any applied more than 7 days ago.</li>
              )}
              {stats.total > 0 && stats.offers === 0 && (
                <li className="text-slate-300 text-sm">→ Focus on quality over quantity — tailor your resume for each JD using the Resume Studio.</li>
              )}
              {stats.interviews > 0 && (
                <li className="text-slate-300 text-sm">✅ You have {stats.interviews} interview-stage applications — prepare well!</li>
              )}
              <li className="text-slate-300 text-sm">→ Recommended daily apply target: 3–10 per day for sustainable momentum.</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
