"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getResumes, getJobPreferences } from "@/lib/supabase";

type ResumeRow = { id: string; file_name: string; updated_at: string };
type PrefsRow = { desired_title: string; job_type: string };

export default function DashboardPage() {
  const { user } = useAuth();
  const [resumes, setResumes] = useState<ResumeRow[]>([]);
  const [prefs, setPrefs] = useState<PrefsRow | null>(null);
  const [loadingData, setLoadingData] = useState(true);

  useEffect(() => {
    if (!user) return;
    Promise.all([
      getResumes(user.id),
      getJobPreferences(user.id),
    ]).then(([resumeRes, prefsRes]) => {
      if (resumeRes.data) setResumes(resumeRes.data as ResumeRow[]);
      if (prefsRes.data) setPrefs(prefsRes.data as PrefsRow);
    }).finally(() => setLoadingData(false));
  }, [user]);

  const lastSeen = user?.last_sign_in_at
    ? new Date(user.last_sign_in_at).toLocaleDateString("en-US", {
        month: "short", day: "numeric", year: "numeric",
      })
    : "—";

  const STAT_CARDS = [
    {
      label: "Resumes Uploaded",
      value: loadingData ? "…" : resumes.length.toString(),
      sub: "stored in Supabase",
      color: "text-amber-400",
    },
    {
      label: "Preferences Set",
      value: loadingData ? "…" : prefs ? "Yes" : "No",
      sub: prefs ? prefs.desired_title : "not configured",
      color: prefs ? "text-emerald-400" : "text-slate-500",
    },
    {
      label: "Last Login",
      value: lastSeen,
      sub: "session active",
      color: "text-sky-400",
    },
  ];

  const QUICK_ACTIONS = [
    {
      href: "/upload-resume",
      icon: "📄",
      title: "Upload Resume",
      desc: "Add or update your latest CV",
    },
    {
      href: "/job-preferences",
      icon: "🎯",
      title: "Job Preferences",
      desc: "Set your title, salary & location",
    },
  ];

  return (
    <div className="max-w-6xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-12 animate-fadeUp">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-2">
          Overview
        </p>
        <h1 className="font-display font-bold text-4xl text-white leading-tight">
          Good to see you,{" "}
          <span className="gradient-text">
            {user?.email?.split("@")[0] ?? "there"}
          </span>
        </h1>
        <p className="text-slate-400 font-body mt-2">
          Here&apos;s a summary of your VantaHire profile.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-12">
        {STAT_CARDS.map((card, i) => (
          <div
            key={card.label}
            className="card animate-fadeUp"
            style={{ animationDelay: `${i * 0.07}s` }}
          >
            <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-3">
              {card.label}
            </p>
            <p className={`font-display font-bold text-3xl ${card.color} mb-1`}>
              {card.value}
            </p>
            <p className="font-body text-sm text-slate-500">{card.sub}</p>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {QUICK_ACTIONS.map(({ href, icon, title, desc }) => (
            <Link
              key={href}
              href={href}
              className="card group flex items-start gap-4 hover:border-amber-400/30 hover:bg-slate-900 transition-all duration-200"
            >
              <span className="text-2xl mt-0.5">{icon}</span>
              <div>
                <p className="font-body font-semibold text-white group-hover:text-amber-400 transition-colors">
                  {title}
                </p>
                <p className="font-body text-sm text-slate-400 mt-0.5">{desc}</p>
              </div>
              <span className="ml-auto text-slate-600 group-hover:text-amber-400 transition-colors text-lg">
                →
              </span>
            </Link>
          ))}
        </div>
      </div>

      {/* Recent resumes */}
      <div className="animate-fadeUp animate-fadeUp-delay-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-semibold text-lg text-white">
            Recent Resumes
          </h2>
          <Link
            href="/upload-resume"
            className="font-body text-sm text-amber-400 hover:text-amber-300 transition-colors"
          >
            + Add new
          </Link>
        </div>

        {loadingData ? (
          <div className="card flex items-center gap-3 text-slate-500">
            <div className="w-4 h-4 border border-slate-600 border-t-amber-400 rounded-full animate-spin" />
            <span className="font-body text-sm">Loading resumes…</span>
          </div>
        ) : resumes.length === 0 ? (
          <div className="card border-dashed text-center py-10">
            <p className="text-slate-500 font-body text-sm">
              No resumes yet.{" "}
              <Link href="/upload-resume" className="text-amber-400 hover:underline">
                Upload your first one →
              </Link>
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {resumes.map((r) => (
              <div
                key={r.id}
                className="card py-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <span className="text-amber-400 text-lg">📄</span>
                  <span className="font-body text-sm text-white">{r.file_name}</span>
                </div>
                <span className="font-mono text-xs text-slate-500">
                  {new Date(r.updated_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Session debug */}
      <details className="mt-16 group">
        <summary className="font-mono text-xs text-slate-700 cursor-pointer hover:text-slate-500 transition-colors select-none">
          ▶ Debug: current session
        </summary>
        <pre className="mt-3 p-4 rounded-lg bg-slate-900 border border-slate-800 font-mono text-xs text-slate-400 overflow-auto">
          {JSON.stringify(
            {
              id: user?.id,
              email: user?.email,
              role: user?.role,
              last_sign_in_at: user?.last_sign_in_at,
            },
            null,
            2
          )}
        </pre>
      </details>
    </div>
  );
}
