"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import Link from "next/link";

// ── Types ─────────────────────────────────────────────────────────────────
const STAGES = ["APPLIED", "SCREENING", "INTERVIEW", "OFFER", "REJECTED"] as const;
type Stage = (typeof STAGES)[number];

type ApplicationRow = {
  id:         string;
  stage:      Stage;
  notes:      string | null;
  applied_at: string;
  updated_at: string;
  ats_score:  number | null;
  follow_up_at: string | null;
  jobs: {
    company:  string;
    role:     string;
    url:      string | null;
    metadata: Record<string, unknown>;
  } | null;
  email_threads?: { classification: string; received_at: string; subject: string }[];
};

const STAGE_COLORS: Record<Stage, string> = {
  APPLIED:   "bg-blue-500/15 text-blue-400 border-blue-500/30",
  SCREENING: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  INTERVIEW: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  OFFER:     "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  REJECTED:  "bg-red-500/15 text-red-400 border-red-500/30",
};

function daysSince(iso: string) {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

// ─────────────────────────────────────────────────────────────────────────
export default function ApplicationsPage() {
  const { user } = useAuth();

  const [apps,           setApps          ] = useState<ApplicationRow[]>([]);
  const [loading,        setLoading       ] = useState(true);
  const [filter,         setFilter        ] = useState<Stage | "ALL">("ALL");
  const [updating,       setUpdating      ] = useState<string | null>(null);
  const [editNotes,      setEditNotes     ] = useState<{ id: string; text: string } | null>(null);
  const [gmailChecking,  setGmailChecking ] = useState(false);
  const [gmailMsg,       setGmailMsg      ] = useState<{ ok: boolean; text: string } | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    const { data } = await supabase
      .from("applications")
      .select("*, jobs(company, role, url, metadata), email_threads(classification, received_at, subject)")
      .eq("user_id", user.id)
      .order("applied_at", { ascending: false });
    if (data) setApps(data as ApplicationRow[]);
    setLoading(false);
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const updateStage = async (id: string, stage: Stage) => {
    setUpdating(id);
    await supabase.from("applications").update({ stage, updated_at: new Date().toISOString() }).eq("id", id);
    setApps((prev) => prev.map((a) => a.id === id ? { ...a, stage } : a));
    setUpdating(null);
  };

  const saveNotes = async () => {
    if (!editNotes) return;
    await supabase.from("applications").update({ notes: editNotes.text }).eq("id", editNotes.id);
    setApps((prev) => prev.map((a) => a.id === editNotes.id ? { ...a, notes: editNotes.text } : a));
    setEditNotes(null);
  };

  const deleteApp = async (id: string) => {
    if (!confirm("Remove this application from tracking?")) return;
    await supabase.from("applications").delete().eq("id", id);
    setApps((prev) => prev.filter((a) => a.id !== id));
  };

  const checkGmailNow = async () => {
    setGmailChecking(true);
    setGmailMsg(null);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { setGmailMsg({ ok: false, text: "Not logged in" }); return; }
      const res = await fetch("/api/gmail/trigger", {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      const json = await res.json();
      if (res.ok) {
        setGmailMsg({ ok: true, text: json.already_running ? json.message : `✓ ${json.message}` });
        // Reload apps after a short delay so new stages show up
        if (!json.already_running) setTimeout(() => load(), 5000);
      } else {
        setGmailMsg({ ok: false, text: json.error ?? "Failed to trigger" });
      }
    } catch (e) {
      setGmailMsg({ ok: false, text: String(e) });
    } finally {
      setGmailChecking(false);
    }
  };

  const filtered = filter === "ALL" ? apps : apps.filter((a) => a.stage === filter);

  // Stage counts for summary
  const counts = STAGES.reduce<Record<Stage, number>>((acc, s) => {
    acc[s] = apps.filter((a) => a.stage === s).length;
    return acc;
  }, {} as Record<Stage, number>);

  // ─────────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-6xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-1">Tracking</p>
          <h1 className="font-display font-bold text-3xl text-white">Applications</h1>
          <p className="text-slate-400 font-body text-sm mt-1">
            Track every application, update status, and manage follow-ups.
          </p>
        </div>
        {/* Gmail Check Now */}
        <div className="flex flex-col items-end gap-2">
          <button
            onClick={checkGmailNow}
            disabled={gmailChecking}
            className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-700 text-white font-mono text-xs px-4 py-2 rounded-lg transition-colors"
          >
            {gmailChecking
              ? <span className="inline-block w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" />
              : "📧"}
            Check Gmail Now
          </button>
          {gmailMsg && (
            <p className={`text-xs font-mono ${gmailMsg.ok ? "text-emerald-400" : "text-red-400"}`}>
              {gmailMsg.text}
            </p>
          )}
          <Link href="/settings" className="text-xs text-slate-500 hover:text-slate-300 font-mono">
            ⚙ Gmail settings
          </Link>
        </div>
      </div>

      {/* Stage summary bar */}
      <div className="grid grid-cols-5 gap-2 mb-8">
        {STAGES.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(filter === s ? "ALL" : s)}
            className={`card py-3 text-center transition-all ${
              filter === s ? "border-amber-400/40 bg-amber-400/5" : "hover:bg-slate-900"
            }`}
          >
            <p className="font-display font-bold text-xl text-white">{counts[s]}</p>
            <p className={`font-mono text-xs mt-0.5 ${STAGE_COLORS[s].split(" ")[1]}`}>{s}</p>
          </button>
        ))}
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={() => setFilter("ALL")}
          className={`px-3 py-1 rounded-full text-xs font-mono border transition-colors ${
            filter === "ALL" ? "bg-slate-700 text-white border-slate-500" : "text-slate-500 border-slate-700 hover:text-white"
          }`}
        >
          All ({apps.length})
        </button>
        {STAGES.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(filter === s ? "ALL" : s)}
            className={`px-3 py-1 rounded-full text-xs font-mono border transition-colors ${
              filter === s
                ? `${STAGE_COLORS[s]} border`
                : "text-slate-500 border-slate-700 hover:text-white"
            }`}
          >
            {s} ({counts[s]})
          </button>
        ))}
      </div>

      {/* Table */}
      {loading ? (
        <div className="card text-center py-12">
          <p className="font-mono text-slate-500 text-sm animate-pulse">Loading applications…</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card border-dashed text-center py-12">
          <p className="text-slate-500 font-body text-sm">
            {apps.length === 0
              ? "No applications tracked yet. Start applying from the Job Search page."
              : `No applications with status "${filter}".`}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((app) => {
            const days         = daysSince(app.applied_at);
            const needFollowUp = app.follow_up_at
              ? new Date(app.follow_up_at) <= new Date() && app.stage === "APPLIED"
              : days >= 7 && app.stage === "APPLIED";

            // Latest email thread
            const latestEmail = (app.email_threads ?? []).sort(
              (a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime()
            )[0];
            const emailBadge: Record<string, { label: string; cls: string }> = {
              ACKNOWLEDGMENT:   { label: "✉️ Acknowledged",   cls: "bg-blue-500/15 text-blue-400 border-blue-400/30" },
              INTERVIEW_INVITE: { label: "🎉 Interview!",      cls: "bg-purple-500/15 text-purple-400 border-purple-400/30" },
              REJECTION:        { label: "❌ Rejected",        cls: "bg-red-500/15 text-red-400 border-red-400/30" },
              SCHEDULE_REQUEST: { label: "📅 Scheduling",      cls: "bg-yellow-500/15 text-yellow-400 border-yellow-400/30" },
              OFFER:            { label: "🏆 Offer!",           cls: "bg-emerald-500/15 text-emerald-400 border-emerald-400/30" },
              FOLLOWUP_SENT:    { label: "📤 Follow-up sent",  cls: "bg-slate-500/15 text-slate-400 border-slate-600" },
            };

            return (
              <div key={app.id} className={`card transition-all ${needFollowUp ? "border-amber-400/20" : ""}`}>
                <div className="flex flex-wrap items-start gap-4">
                  {/* Company / Role */}
                  <div className="flex-1 min-w-[200px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-body font-semibold text-white">
                        {app.jobs?.company ?? "—"}
                      </p>
                      {app.jobs?.url && (
                        <a href={app.jobs.url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-blue-400 hover:underline">↗</a>
                      )}
                      {needFollowUp && (
                        <span className="text-xs font-mono bg-amber-400/10 text-amber-400 border border-amber-400/30 px-2 py-0.5 rounded-full">
                          ⏰ Follow up
                        </span>
                      )}
                      {latestEmail && emailBadge[latestEmail.classification] && (
                        <span className={`text-xs font-mono border px-2 py-0.5 rounded-full ${emailBadge[latestEmail.classification].cls}`}>
                          {emailBadge[latestEmail.classification].label}
                        </span>
                      )}
                    </div>
                    <p className="text-slate-400 text-sm">{app.jobs?.role ?? "—"}</p>
                    <p className="font-mono text-xs text-slate-600 mt-0.5">
                      Applied {days === 0 ? "today" : `${days}d ago`}
                      {app.ats_score != null && <span className="ml-3 text-emerald-500">ATS {app.ats_score}%</span>}
                      {app.follow_up_at && app.stage === "APPLIED" && (
                        <span className="ml-3 text-amber-600">
                          Follow-up {new Date(app.follow_up_at) <= new Date() ? "overdue" : `in ${Math.ceil((new Date(app.follow_up_at).getTime() - Date.now()) / 86_400_000)}d`}
                        </span>
                      )}
                    </p>
                  </div>

                  {/* Stage selector */}
                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <select
                      value={app.stage}
                      disabled={updating === app.id}
                      onChange={(e) => updateStage(app.id, e.target.value as Stage)}
                      className={`text-xs font-mono px-2 py-1 rounded border bg-slate-900 cursor-pointer disabled:opacity-50 ${STAGE_COLORS[app.stage]}`}
                    >
                      {STAGES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>

                    <div className="flex gap-1">
                      <button
                        onClick={() => setEditNotes({ id: app.id, text: app.notes || "" })}
                        className="text-xs text-slate-500 hover:text-white border border-slate-700 px-2 py-0.5 rounded"
                        title="Add note"
                      >
                        📝
                      </button>
                      <button
                        onClick={() => deleteApp(app.id)}
                        className="text-xs text-slate-500 hover:text-red-400 border border-slate-700 px-2 py-0.5 rounded"
                        title="Remove"
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                </div>

                {/* Notes */}
                {app.notes && (
                  <p className="mt-2 text-slate-400 text-xs border-t border-slate-800 pt-2">
                    📌 {app.notes}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Notes edit modal */}
      {editNotes && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4">
          <div className="card w-full max-w-md space-y-4">
            <p className="font-display font-semibold text-white">Add / Edit Note</p>
            <textarea
              rows={4}
              value={editNotes.text}
              onChange={(e) => setEditNotes({ ...editNotes, text: e.target.value })}
              className="w-full bg-slate-900 border border-slate-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-400"
              placeholder="e.g. Applied via referral, interview scheduled for Mon 10am…"
            />
            <div className="flex justify-end gap-2">
              <button onClick={() => setEditNotes(null)} className="px-4 py-2 text-sm text-slate-400 hover:text-white">Cancel</button>
              <button onClick={saveNotes} className="bg-amber-400 text-slate-950 font-bold px-5 py-2 rounded-lg text-sm">Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
