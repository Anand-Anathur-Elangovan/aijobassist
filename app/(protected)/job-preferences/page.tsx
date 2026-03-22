"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { saveJob, getJobs, deleteJob, Job } from "@/lib/supabase";

type SaveState = "idle" | "saving" | "saved" | "error";

export default function JobsPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);

  const [form, setForm] = useState({
    company: "",
    role: "",
    url: "",
    status: "SAVED",
  });

  const loadJobs = useCallback(async () => {
    if (!user) return;
    const { data } = await getJobs(user.id);
    if (data) setJobs(data as Job[]);
    setLoading(false);
  }, [user]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !form.company || !form.role) {
      setErrorMsg("Company and role are required");
      return;
    }

    setSaveState("saving");
    setErrorMsg(null);

    const { error } = await saveJob({
      user_id: user.id,
      company: form.company,
      role: form.role,
      url: form.url || undefined,
      status: form.status,
      metadata: {},
    });

    if (error) {
      setErrorMsg(error.message);
      setSaveState("error");
    } else {
      setSaveState("saved");
      setForm({ company: "", role: "", url: "", status: "SAVED" });
      setTimeout(() => setSaveState("idle"), 3000);
      loadJobs();
    }
  };

  const handleDelete = async (jobId: string) => {
    const { error } = await deleteJob(jobId);
    if (!error) loadJobs();
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-4 h-4 border border-slate-600 border-t-amber-400 rounded-full animate-spin" />
          <span className="font-body text-sm">Loading jobs…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-10 animate-fadeUp">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-2">
          Jobs
        </p>
        <h1 className="font-display font-bold text-4xl text-white mb-2">
          Track <span className="gradient-text">Opportunities</span>
        </h1>
        <p className="text-slate-400 font-body">
          Save and manage job postings you&apos;re interested in.
        </p>
      </div>

      {/* Add Job Form */}
      <form onSubmit={handleSave} className="card mb-8 animate-fadeUp">
        <h2 className="font-mono text-sm text-amber-400 uppercase tracking-widest mb-6">
          Add New Job
        </h2>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <input
            type="text"
            placeholder="Company"
            className="input-base"
            value={form.company}
            onChange={(e) => setForm({ ...form, company: e.target.value })}
            required
          />
          <input
            type="text"
            placeholder="Job Title"
            className="input-base"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
            required
          />
        </div>

        <input
          type="url"
          placeholder="Job URL (optional)"
          className="input-base mb-4 w-full"
          value={form.url}
          onChange={(e) => setForm({ ...form, url: e.target.value })}
        />

        <select
          className="input-base mb-4 w-full"
          value={form.status}
          onChange={(e) => setForm({ ...form, status: e.target.value })}
        >
          <option value="SAVED">SAVED</option>
          <option value="APPLYING">APPLYING</option>
          <option value="APPLIED">APPLIED</option>
          <option value="CLOSED">CLOSED</option>
        </select>

        {errorMsg && <p className="text-red-400 text-sm mb-4">{errorMsg}</p>}

        <button
          type="submit"
          disabled={saveState === "saving"}
          className="w-full bg-amber-400 text-slate-900 font-bold py-2.5 rounded-lg hover:bg-amber-300 transition-colors disabled:opacity-50"
        >
          {saveState === "saving" ? "Saving..." : saveState === "saved" ? "✓ Saved" : "Add Job"}
        </button>
      </form>

      {/* Jobs List */}
      <div className="space-y-4">
        <h2 className="font-mono text-sm text-slate-400 uppercase tracking-widest mb-4">
          Your Jobs ({jobs.length})
        </h2>

        {jobs.length === 0 ? (
          <div className="card text-center py-8">
            <p className="text-slate-400">No jobs saved yet. Add one above!</p>
          </div>
        ) : (
          jobs.map((job) => (
            <div key={job.id} className="card hover:border-amber-400/30 transition-colors">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-bold text-lg text-white">{job.role}</h3>
                  <p className="text-amber-400 font-semibold">{job.company}</p>
                  {job.url && (
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-slate-400 hover:text-amber-400 transition-colors mt-1 inline-block"
                    >
                      View posting →
                    </a>
                  )}
                  <div className="mt-2 flex gap-2">
                    <span className="px-2.5 py-0.5 rounded text-xs font-mono bg-amber-400/15 text-amber-400">
                      {job.status}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => job.id && handleDelete(job.id)}
                  className="text-slate-500 hover:text-red-400 transition-colors ml-4"
                >
                  ✕
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
