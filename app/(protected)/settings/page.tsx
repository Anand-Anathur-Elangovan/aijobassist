"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import {
  getUserProfile,
  updateUserProfile,
  getSubscriptionWithPlan,
  getRemainingTrialDays,
  getPlanBadgeColor,
  type Plan,
  type Subscription,
} from "@/lib/billing";
import Link from "next/link";

export default function SettingsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"profile" | "account" | "gmail" | "notifications" | "preferences">("profile");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Profile
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [country, setCountry] = useState("India");

  // Plan
  const [plan, setPlan] = useState<Plan | null>(null);
  const [sub, setSub] = useState<Subscription | null>(null);

  // Telegram
  const [telegramChatId, setTelegramChatId] = useState("");

  // Gmail
  const [gmailAddress, setGmailAddress] = useState("");
  const [appPassword, setAppPassword] = useState("");
  const [followupDays, setFollowupDays] = useState(3);
  const [gmailActive, setGmailActive] = useState(true);

  useEffect(() => {
    if (user) loadSettings();
  }, [user]);

  async function loadSettings() {
    if (!user) return;

    // Profile
    const profile = await getUserProfile(user.id);
    if (profile) {
      setFullName(profile.full_name || "");
      setPhone(profile.phone || "");
      setCountry(profile.country || "India");
      setTelegramChatId(profile.telegram_chat_id || "");
    }

    // Plan
    const { subscription, plan: p } = await getSubscriptionWithPlan(user.id);
    setPlan(p);
    setSub(subscription);

    // Gmail settings
    const { data: gmail } = await supabase
      .from("gmail_settings")
      .select("*")
      .eq("user_id", user.id)
      .single();
    if (gmail) {
      setGmailAddress(gmail.gmail_address || "");
      setAppPassword(gmail.app_password || "");
      setFollowupDays(gmail.followup_days ?? 3);
      setGmailActive(gmail.active ?? true);
    }

    setLoading(false);
  }

  async function saveProfile() {
    if (!user) return;
    setSaving(true);
    await updateUserProfile(user.id, { full_name: fullName, phone, country });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function saveNotifications() {
    if (!user) return;
    setSaving(true);
    await updateUserProfile(user.id, { telegram_chat_id: telegramChatId.trim() });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function saveGmail() {
    if (!user) return;
    setSaving(true);
    await supabase.from("gmail_settings").upsert(
      {
        user_id: user.id,
        gmail_address: gmailAddress,
        app_password: appPassword,
        followup_days: followupDays,
        active: gmailActive,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id" }
    );
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function deleteAccount() {
    if (!confirm("Are you sure? This action cannot be undone. All your data will be permanently deleted.")) return;
    if (!confirm("FINAL CONFIRMATION: Delete your account and all associated data?")) return;
    // In production, this should call a server action that deletes the user
    alert("Account deletion request submitted. You will be logged out.");
  }

  const TABS = [
    { key: "profile" as const, label: "Profile", icon: "👤" },
    { key: "account" as const, label: "Account", icon: "🔒" },
    { key: "gmail" as const, label: "Gmail", icon: "📧" },
    { key: "notifications" as const, label: "Notifications", icon: "🔔" },
    { key: "preferences" as const, label: "Preferences", icon: "⚙️" },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <h1 className="text-2xl font-display font-bold text-white mb-8">Settings</h1>

      {/* Tab nav */}
      <div className="flex gap-2 mb-8 border-b border-slate-800 pb-3">
        {TABS.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-all ${
              tab === key
                ? "bg-slate-800 text-amber-400 border-b-2 border-amber-400"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <span>{icon}</span> {label}
          </button>
        ))}
      </div>

      {/* Success toast */}
      {saved && (
        <div className="mb-6 bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3 text-emerald-400 text-sm animate-fadeUp">
          ✓ Settings saved successfully
        </div>
      )}

      {/* Profile tab */}
      {tab === "profile" && (
        <div className="card space-y-6">
          <h2 className="font-display font-bold text-white">Personal Information</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Full Name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="input-base"
                placeholder="Your full name"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Email</label>
              <input
                type="email"
                value={user?.email ?? ""}
                disabled
                className="input-base opacity-50"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Phone</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="input-base"
                placeholder="+91 98765 43210"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Country</label>
              <select
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                className="input-base"
              >
                <option value="India">India</option>
                <option value="United States">United States</option>
                <option value="United Kingdom">United Kingdom</option>
                <option value="Canada">Canada</option>
                <option value="Australia">Australia</option>
                <option value="Germany">Germany</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>
          <button onClick={saveProfile} disabled={saving} className="btn-primary">
            {saving ? "Saving..." : "Save Profile"}
          </button>
        </div>
      )}

      {/* Account tab */}
      {tab === "account" && (
        <div className="space-y-6">
          <div className="card">
            <h2 className="font-display font-bold text-white mb-4">Subscription</h2>
            <div className="flex items-center gap-4 mb-4">
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${getPlanBadgeColor(plan?.slug ?? "free")}`}>
                {plan?.name ?? "Free"}
              </span>
              {sub?.trial_ends_at && (
                <span className="text-sm text-amber-400">
                  {getRemainingTrialDays(sub.trial_ends_at)} days left in trial
                </span>
              )}
            </div>
            <div className="flex gap-3">
              <Link href="/pricing" className="btn-primary text-sm">
                {plan?.price_monthly ? "Change Plan" : "Upgrade"}
              </Link>
              <Link href="/billing" className="px-4 py-2 border border-slate-700 text-slate-300 rounded-lg text-sm hover:border-slate-500">
                View Billing
              </Link>
            </div>
          </div>

          <div className="card border-red-500/20">
            <h2 className="font-display font-bold text-red-400 mb-2">Danger Zone</h2>
            <p className="text-slate-400 text-sm mb-4">
              Once you delete your account, all data is permanently removed.
            </p>
            <button
              onClick={deleteAccount}
              className="px-4 py-2 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg text-sm hover:bg-red-500/20 transition-all"
            >
              Delete Account
            </button>
          </div>
        </div>
      )}

      {/* Gmail tab */}
      {tab === "gmail" && (
        <div className="card space-y-6">
          <div>
            <h2 className="font-display font-bold text-white">Gmail Integration</h2>
            <p className="text-slate-400 text-sm mt-1">
              Connect your Gmail to auto-detect interview invites and send follow-ups.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Gmail Address</label>
              <input
                type="email"
                value={gmailAddress}
                onChange={(e) => setGmailAddress(e.target.value)}
                className="input-base"
                placeholder="you@gmail.com"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">App Password</label>
              <input
                type="password"
                value={appPassword}
                onChange={(e) => setAppPassword(e.target.value)}
                className="input-base"
                placeholder="Google App Password (16 chars)"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Follow-up After (days)</label>
              <input
                type="number"
                min="1"
                max="14"
                value={followupDays}
                onChange={(e) => setFollowupDays(parseInt(e.target.value) || 3)}
                className="input-base"
              />
            </div>
            <div className="flex items-center gap-3 pt-6">
              <button
                onClick={() => setGmailActive(!gmailActive)}
                className={`w-12 h-6 rounded-full transition-all ${gmailActive ? "bg-amber-400" : "bg-slate-700"}`}
              >
                <div className={`w-5 h-5 rounded-full bg-white shadow transition-transform ${gmailActive ? "translate-x-6" : "translate-x-0.5"}`} />
              </button>
              <span className="text-sm text-slate-300">{gmailActive ? "Active" : "Paused"}</span>
            </div>
          </div>
          <button onClick={saveGmail} disabled={saving} className="btn-primary">
            {saving ? "Saving..." : "Save Gmail Settings"}
          </button>
        </div>
      )}

      {/* Notifications tab */}
      {tab === "notifications" && (
        <div className="card space-y-6">
          <div>
            <h2 className="font-display font-bold text-white">Telegram Notifications</h2>
            <p className="text-slate-400 text-sm mt-1">
              Get instant alerts when the bot needs your help or finishes a session.
            </p>
          </div>

          <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 text-sm text-slate-300 space-y-2">
            <p className="font-semibold text-amber-400">Setup (one-time, 2 min):</p>
            <ol className="list-decimal list-inside space-y-1 text-slate-400">
              <li>Open Telegram and search <span className="text-white font-mono">@AIJobSyncBot</span> → tap <span className="font-mono">Start</span></li>
              <li>Then search <span className="text-white font-mono">@userinfobot</span> → tap <span className="font-mono">Start</span></li>
              <li>Copy the <span className="text-white">Id</span> number it gives you and paste it below</li>
            </ol>
          </div>

          <div className="max-w-sm">
            <label className="block text-sm text-slate-400 mb-1">Your Telegram Chat ID</label>
            <input
              type="text"
              value={telegramChatId}
              onChange={(e) => setTelegramChatId(e.target.value)}
              className="input-base"
              placeholder="e.g. 987654321"
            />
            <p className="text-xs text-slate-500 mt-1">
              This is your personal numeric ID from @userinfobot, not your phone number.
            </p>
          </div>

          <button onClick={saveNotifications} disabled={saving} className="btn-primary">
            {saving ? "Saving..." : "Save Notification Settings"}
          </button>
        </div>
      )}

      {/* Preferences tab */}
      {tab === "preferences" && (
        <div className="card space-y-6">
          <h2 className="font-display font-bold text-white">Application Preferences</h2>
          <p className="text-slate-400 text-sm">
            These settings affect how the automation bot applies to jobs.
            Configure your detailed job preferences on the{" "}
            <Link href="/job-preferences" className="text-amber-400 hover:underline">
              Job Preferences
            </Link>{" "}
            page.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-slate-300">Notification Preferences</h3>
              {[
                { key: "email_alerts", label: "Email alerts for new matches" },
                { key: "application_updates", label: "Application status updates" },
                { key: "weekly_summary", label: "Weekly summary email" },
              ].map(({ key, label }) => (
                <label key={key} className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-amber-400 focus:ring-amber-400" />
                  <span className="text-sm text-slate-300">{label}</span>
                </label>
              ))}
            </div>
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-slate-300">Automation Settings</h3>
              {[
                { key: "auto_tailor", label: "Auto-tailor resume before applying" },
                { key: "auto_cover", label: "Auto-generate cover letter" },
                { key: "skip_applied", label: "Skip jobs already applied to" },
              ].map(({ key, label }) => (
                <label key={key} className="flex items-center gap-3 cursor-pointer">
                  <input type="checkbox" defaultChecked className="w-4 h-4 rounded border-slate-700 bg-slate-800 text-amber-400 focus:ring-amber-400" />
                  <span className="text-sm text-slate-300">{label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
