"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { saveJobPreferences, getJobPreferences, JobPreferences } from "@/lib/supabase";

const JOB_TYPES = ["full-time", "part-time", "contract", "remote"] as const;

const INDUSTRIES = [
  "Technology", "Finance", "Healthcare", "Education",
  "Media & Marketing", "Engineering", "Legal", "Design",
  "Sales", "Operations", "Government", "Non-profit",
];

type SaveState = "idle" | "saving" | "saved" | "error";

function TagToggle({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 rounded-md font-body text-sm transition-all duration-150 border ${
        active
          ? "bg-amber-400/15 border-amber-400/40 text-amber-400"
          : "bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-white"
      }`}
    >
      {label}
    </button>
  );
}

export default function JobPreferencesPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [form, setForm] = useState<Omit<JobPreferences, "user_id">>({
    desired_title: "",
    locations: [],
    min_salary: null,
    job_type: "full-time",
    industries: [],
    open_to_relocation: false,
  });
  const [locationInput, setLocationInput] = useState("");

  const loadPrefs = useCallback(async () => {
    if (!user) return;
    const { data } = await getJobPreferences(user.id);
    if (data) {
      setForm({
        desired_title: data.desired_title ?? "",
        locations: data.locations ?? [],
        min_salary: data.min_salary ?? null,
        job_type: data.job_type ?? "full-time",
        industries: data.industries ?? [],
        open_to_relocation: data.open_to_relocation ?? false,
      });
    }
    setLoading(false);
  }, [user]);

  useEffect(() => {
    loadPrefs();
  }, [loadPrefs]);

  const addLocation = () => {
    const trimmed = locationInput.trim();
    if (!trimmed || form.locations.includes(trimmed)) return;
    setForm((f) => ({ ...f, locations: [...f.locations, trimmed] }));
    setLocationInput("");
  };

  const removeLocation = (loc: string) =>
    setForm((f) => ({ ...f, locations: f.locations.filter((l) => l !== loc) }));

  const toggleIndustry = (ind: string) =>
    setForm((f) => ({
      ...f,
      industries: f.industries.includes(ind)
        ? f.industries.filter((i) => i !== ind)
        : [...f.industries, ind],
    }));

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    setSaveState("saving");
    setErrorMsg(null);

    const { error } = await saveJobPreferences({ ...form, user_id: user.id });

    if (error) {
      setErrorMsg(error.message);
      setSaveState("error");
    } else {
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 3000);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-4 h-4 border border-slate-600 border-t-amber-400 rounded-full animate-spin" />
          <span className="font-body text-sm">Loading preferences…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-10 animate-fadeUp">
        <p className="font-mono text-xs text-slate-500 tracking-widest uppercase mb-2">
          Preferences
        </p>
        <h1 className="font-display font-bold text-4xl text-white mb-2">
          Job <span className="gradient-text">Preferences</span>
        </h1>
        <p className="text-slate-400 font-body">
          Tell us what your ideal role looks like. We&apos;ll match you accordingly.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-8">
        {/* Desired title */}
        <div className="card animate-fadeUp animate-fadeUp-delay-1">
          <label className="block font-mono text-xs text-slate-400 uppercase tracking-widest mb-3">
            Desired Job Title
          </label>
          <input
            className="input-base"
            type="text"
            placeholder="e.g. Senior Software Engineer"
            value={form.desired_title}
            onChange={(e) => setForm((f) => ({ ...f, desired_title: e.target.value }))}
            required
          />
        </div>

        {/* Job type */}
        <div className="card animate-fadeUp animate-fadeUp-delay-1">
          <p className="font-mono text-xs text-slate-400 uppercase tracking-widest mb-3">
            Employment Type
          </p>
          <div className="flex flex-wrap gap-2">
            {JOB_TYPES.map((type) => (
              <TagToggle
                key={type}
                label={type.charAt(0).toUpperCase() + type.slice(1)}
                active={form.job_type === type}
                onClick={() => setForm((f) => ({ ...f, job_type: type }))}
              />
            ))}
          </div>
        </div>

        {/* Minimum salary */}
        <div className="card animate-fadeUp animate-fadeUp-delay-2">
          <label className="block font-mono text-xs text-slate-400 uppercase tracking-widest mb-3">
            Minimum Annual Salary (USD)
          </label>
          <div className="relative">
            <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 font-body text-sm">
              $
            </span>
            <input
              className="input-base pl-8"
              type="number"
              min={0}
              step={5000}
              placeholder="e.g. 120000"
              value={form.min_salary ?? ""}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  min_salary: e.target.value ? parseInt(e.target.value) : null,
                }))
              }
            />
          </div>
          {form.min_salary && (
            <p className="mt-2 font-mono text-xs text-amber-400">
              ${form.min_salary.toLocaleString()} / year
            </p>
          )}
        </div>

        {/* Locations */}
        <div className="card animate-fadeUp animate-fadeUp-delay-2">
          <p className="font-mono text-xs text-slate-400 uppercase tracking-widest mb-3">
            Preferred Locations
          </p>
          <div className="flex gap-2 mb-3">
            <input
              className="input-base flex-1"
              type="text"
              placeholder="e.g. San Francisco, CA"
              value={locationInput}
              onChange={(e) => setLocationInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addLocation(); } }}
            />
            <button
              type="button"
              onClick={addLocation}
              className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-sm font-body hover:border-slate-500 transition-colors"
            >
              Add
            </button>
          </div>
          {form.locations.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {form.locations.map((loc) => (
                <span
                  key={loc}
                  className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-400/10 border border-amber-400/20 text-amber-400 font-body text-sm"
                >
                  {loc}
                  <button
                    type="button"
                    onClick={() => removeLocation(loc)}
                    className="text-amber-400/60 hover:text-amber-400 transition-colors leading-none"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Open to relocation */}
          <label className="flex items-center gap-3 mt-4 cursor-pointer group">
            <div
              className={`w-5 h-5 rounded border flex items-center justify-center transition-all ${
                form.open_to_relocation
                  ? "bg-amber-400 border-amber-400"
                  : "border-slate-600 group-hover:border-slate-400"
              }`}
              onClick={() =>
                setForm((f) => ({ ...f, open_to_relocation: !f.open_to_relocation }))
              }
            >
              {form.open_to_relocation && (
                <svg className="w-3 h-3 text-slate-950" fill="none" viewBox="0 0 12 12" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2 6l3 3 5-5" />
                </svg>
              )}
            </div>
            <input
              type="checkbox"
              className="sr-only"
              checked={form.open_to_relocation}
              onChange={(e) =>
                setForm((f) => ({ ...f, open_to_relocation: e.target.checked }))
              }
            />
            <span className="font-body text-sm text-slate-300">Open to relocation</span>
          </label>
        </div>

        {/* Industries */}
        <div className="card animate-fadeUp animate-fadeUp-delay-3">
          <p className="font-mono text-xs text-slate-400 uppercase tracking-widest mb-3">
            Industries of Interest
          </p>
          <div className="flex flex-wrap gap-2">
            {INDUSTRIES.map((ind) => (
              <TagToggle
                key={ind}
                label={ind}
                active={form.industries.includes(ind)}
                onClick={() => toggleIndustry(ind)}
              />
            ))}
          </div>
          {form.industries.length > 0 && (
            <p className="mt-3 font-mono text-xs text-slate-500">
              {form.industries.length} selected
            </p>
          )}
        </div>

        {/* Errors */}
        {errorMsg && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-red-400 font-body text-sm">
            {errorMsg}
          </div>
        )}

        {/* Submit */}
        <div className="flex items-center gap-4 animate-fadeUp animate-fadeUp-delay-4">
          <button
            type="submit"
            disabled={saveState === "saving"}
            className="btn-primary flex-1 sm:flex-none sm:min-w-[180px]"
          >
            {saveState === "saving" ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-slate-900 border-t-transparent rounded-full animate-spin" />
                Saving…
              </span>
            ) : saveState === "saved" ? (
              "✓ Saved!"
            ) : (
              "Save Preferences →"
            )}
          </button>

          {saveState === "saved" && (
            <span className="font-body text-sm text-emerald-400 animate-fadeUp">
              Preferences saved to Supabase
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
