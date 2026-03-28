"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { supabase } from "@/lib/supabase";
import { getUserProfile, updateUserProfile } from "@/lib/billing";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
}

const TYPE_ICONS: Record<string, string> = {
  new_job: "💼",
  application_complete: "✅",
  follow_up: "📩",
  resume_ready: "📄",
  interview: "🎤",
  general: "🔔",
};

export default function NotificationsPage() {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [loading, setLoading] = useState(true);

  // Telegram setup
  const [telegramChatId, setTelegramChatId] = useState("");
  const [savedChatId, setSavedChatId] = useState("");
  const [savingTg, setSavingTg] = useState(false);
  const [tgSaved, setTgSaved] = useState(false);

  useEffect(() => {
    if (user) {
      loadNotifications();
      loadTelegramSettings();
    }
  }, [user]);

  async function loadTelegramSettings() {
    if (!user) return;
    const profile = await getUserProfile(user.id);
    const chatId = profile?.telegram_chat_id ?? "";
    setTelegramChatId(chatId);
    setSavedChatId(chatId);
  }

  async function loadNotifications() {
    if (!user) return;
    const { data } = await supabase
      .from("notifications")
      .select("*")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .limit(100);
    setNotifications((data as Notification[]) ?? []);
    setLoading(false);
  }

  async function saveTelegram() {
    if (!user) return;
    setSavingTg(true);
    await updateUserProfile(user.id, { telegram_chat_id: telegramChatId.trim() });
    setSavedChatId(telegramChatId.trim());
    setSavingTg(false);
    setTgSaved(true);
    setTimeout(() => setTgSaved(false), 2500);
  }

  async function markRead(id: string) {
    await supabase.from("notifications").update({ read: true }).eq("id", id);
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
  }

  async function markAllRead() {
    if (!user) return;
    await supabase
      .from("notifications")
      .update({ read: true })
      .eq("user_id", user.id)
      .eq("read", false);
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }

  async function clearAll() {
    if (!user || !confirm("Delete all notifications?")) return;
    await supabase.from("notifications").delete().eq("user_id", user.id);
    setNotifications([]);
  }

  const filtered = filter === "unread" ? notifications.filter((n) => !n.read) : notifications;
  const unreadCount = notifications.filter((n) => !n.read).length;
  const isConnected = savedChatId.length > 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">

      {/* ── Telegram Setup Card ─────────────────────────────────── */}
      <div className={`rounded-xl border p-6 space-y-4 ${isConnected ? "border-green-500/30 bg-green-500/5" : "border-amber-400/30 bg-amber-400/5"}`}>
        <div className="flex items-center gap-3">
          <span className="text-2xl">✈️</span>
          <div>
            <h2 className="font-display font-bold text-white">
              Telegram Notifications
              {isConnected && (
                <span className="ml-2 text-xs font-normal bg-green-500/20 text-green-400 border border-green-500/30 px-2 py-0.5 rounded-full">
                  Connected
                </span>
              )}
            </h2>
            <p className="text-slate-400 text-sm">
              Get instant alerts on your phone when the bot needs help or finishes a run.
            </p>
          </div>
        </div>

        {/* Steps */}
        <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-4 space-y-3">
          <p className="text-amber-400 text-sm font-semibold">How to connect (2 min):</p>
          <div className="space-y-2 text-sm text-slate-300">
            <div className="flex gap-3">
              <span className="w-5 h-5 rounded-full bg-amber-400 text-slate-950 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
              <p>
                Open Telegram → search{" "}
                <span className="font-mono bg-slate-800 px-1.5 py-0.5 rounded text-amber-300">@AIJobSyncBot</span>
                {" "}→ tap <strong>Start</strong>
                <span className="text-slate-500 ml-1">(this is the bot that sends you alerts)</span>
              </p>
            </div>
            <div className="flex gap-3">
              <span className="w-5 h-5 rounded-full bg-amber-400 text-slate-950 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
              <p>
                Search{" "}
                <span className="font-mono bg-slate-800 px-1.5 py-0.5 rounded text-amber-300">@userinfobot</span>
                {" "}→ tap <strong>Start</strong>
                <span className="text-slate-500 ml-1">(it will show your numeric Chat ID)</span>
              </p>
            </div>
            <div className="flex gap-3">
              <span className="w-5 h-5 rounded-full bg-amber-400 text-slate-950 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
              <p>Copy the <strong>Id</strong> number and paste it below, then click Save.</p>
            </div>
            <div className="flex gap-3">
              <span className="w-5 h-5 rounded-full bg-slate-600 text-slate-300 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">✓</span>
              <p className="text-slate-400">
                Done! The bot will now message you on Telegram whenever it gets stuck on an external application or finishes a session.
              </p>
            </div>
          </div>
        </div>

        {/* Input + Save */}
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-sm text-slate-400 mb-1">Your Telegram Chat ID</label>
            <input
              type="text"
              value={telegramChatId}
              onChange={(e) => setTelegramChatId(e.target.value)}
              className="input-base w-full"
              placeholder="e.g. 987654321"
            />
          </div>
          <button
            onClick={saveTelegram}
            disabled={savingTg || telegramChatId.trim() === savedChatId}
            className="btn-primary shrink-0"
          >
            {savingTg ? "Saving…" : tgSaved ? "Saved ✓" : "Save"}
          </button>
        </div>

        {isConnected && (
          <p className="text-green-400 text-xs">
            Connected to Chat ID: <span className="font-mono">{savedChatId}</span>
          </p>
        )}
      </div>

      {/* ── In-app Notifications ───────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-display font-bold text-white">In-App Notifications</h1>
            {unreadCount > 0 && (
              <p className="text-amber-400 text-sm mt-0.5">{unreadCount} unread</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={markAllRead}
              disabled={unreadCount === 0}
              className="text-sm text-slate-400 hover:text-white transition-colors disabled:opacity-40"
            >
              Mark all read
            </button>
            <button
              onClick={clearAll}
              disabled={notifications.length === 0}
              className="text-sm text-red-400 hover:text-red-300 transition-colors disabled:opacity-40"
            >
              Clear all
            </button>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2 mb-4">
          {(["all", "unread"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                filter === f
                  ? "bg-amber-400/10 text-amber-400 border border-amber-400/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {f === "all" ? `All (${notifications.length})` : `Unread (${unreadCount})`}
            </button>
          ))}
        </div>

        {/* Notifications list */}
        <div className="space-y-2">
          {filtered.length === 0 ? (
            <div className="text-center py-16">
              <div className="text-4xl mb-3">🔔</div>
              <p className="text-slate-400">No notifications yet</p>
            </div>
          ) : (
            filtered.map((n) => (
              <button
                key={n.id}
                onClick={() => !n.read && markRead(n.id)}
                className={`w-full text-left card flex items-start gap-4 transition-all ${
                  !n.read ? "border-amber-400/20 bg-amber-400/5" : "opacity-70"
                }`}
              >
                <div className="text-2xl shrink-0 mt-0.5">
                  {TYPE_ICONS[n.type] ?? "🔔"}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className={`text-sm font-semibold ${!n.read ? "text-white" : "text-slate-400"}`}>
                      {n.title}
                    </h3>
                    <span className="text-xs text-slate-500 shrink-0">
                      {timeAgo(n.created_at)}
                    </span>
                  </div>
                  <p className="text-slate-400 text-sm mt-0.5 truncate">{n.message}</p>
                </div>
                {!n.read && (
                  <div className="w-2 h-2 rounded-full bg-amber-400 shrink-0 mt-2" />
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}
