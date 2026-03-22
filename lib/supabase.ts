import { createBrowserClient } from "@supabase/ssr";

// ──────────────────────────────────────────────────────────────
// Supabase credentials — read from env vars with hardcoded fallbacks
// Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in .env.local
// ──────────────────────────────────────────────────────────────
const SUPABASE_URL =
  process.env.NEXT_PUBLIC_SUPABASE_URL ||
  "https://feqhdpxnzlctpwvvjxui.supabase.co";
const SUPABASE_ANON_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQxMDczMjUsImV4cCI6MjA4OTY4MzMyNX0.aa7t-5sLixSpAkJwSEL4Ki-Uae2PFNyH9GHpMdFarOA";

// Singleton client — uses cookies so middleware can read the session
export const supabase = createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ──────────────────────────────────────────────────────────────
// Auth helpers
// ──────────────────────────────────────────────────────────────

/** Sign up with email + password. Returns { data, error } */
export async function signUp(email: string, password: string) {
  return supabase.auth.signUp({ email, password });
}

/** Sign in with email + password. Returns { data, error } */
export async function signIn(email: string, password: string) {
  return supabase.auth.signInWithPassword({ email, password });
}

/** Sign out the current user */
export async function signOut() {
  return supabase.auth.signOut();
}

/** Get the currently authenticated user (null if not logged in) */
export async function getUser() {
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
}

/** Get the current session (includes JWT access_token) */
export async function getSession() {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session;
}

// ──────────────────────────────────────────────────────────────
// Resume helpers
// ──────────────────────────────────────────────────────────────

/**
 * Upload a resume file to the "resumes" storage bucket.
 * Returns the public URL on success.
 */
export async function uploadResume(file: File, userId: string) {
  const filePath = `${userId}/${Date.now()}_${file.name}`;

  console.log("Uploading to:", filePath);
  const { data, error: uploadError } = await supabase.storage
    .from("resumes")
    .upload(filePath, file, { upsert: true });

  if (uploadError) {
    console.error("Upload error:", uploadError);
    return { url: null, error: uploadError };
  }

  console.log("Upload successful:", data);
  const { data: publicUrlData } = supabase.storage.from("resumes").getPublicUrl(filePath);
  return { url: publicUrlData.publicUrl, error: null };
}

/**
 * Upsert resume metadata into the `resumes` table.
 */
export async function saveResumeMeta(
  userId: string,
  fileUrl: string,
  fileName: string
) {
  return supabase.from("resumes").upsert({
    user_id: userId,
    title: fileName,
    content: { file_url: fileUrl, file_name: fileName },
  });
}

/**
 * Fetch all resumes for the current user.
 */
export async function getResumes(userId: string) {
  return supabase
    .from("resumes")
    .select("*")
    .eq("user_id", userId)
    .order("updated_at", { ascending: false });
}

// ──────────────────────────────────────────────────────────────
// Jobs helpers
// ──────────────────────────────────────────────────────────────

export type Job = {
  id?: string;
  user_id: string;
  company: string;
  role: string;
  url?: string;
  status?: string;  // SAVED, APPLYING, CLOSED, etc.
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
};

/**
 * Create or update a job entry.
 */
export async function saveJob(job: Job) {
  return supabase.from("jobs").upsert({
    ...job,
    updated_at: new Date().toISOString(),
  });
}

/**
 * Fetch all jobs for a user.
 */
export async function getJobs(userId: string) {
  return supabase
    .from("jobs")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });
}

/**
 * Fetch a specific job by ID.
 */
export async function getJobById(jobId: string) {
  return supabase
    .from("jobs")
    .select("*")
    .eq("id", jobId)
    .single();
}

/**
 * Delete a job.
 */
export async function deleteJob(jobId: string) {
  return supabase
    .from("jobs")
    .delete()
    .eq("id", jobId);
}

// ──────────────────────────────────────────────────────────────
// Applications helpers
// ──────────────────────────────────────────────────────────────

export type Application = {
  id?: string;
  user_id: string;
  job_id: string;
  resume_id?: string;
  stage?: string;  // APPLIED, SCREENING, INTERVIEW, OFFER, REJECTED
  notes?: string;
  payload?: Record<string, any>;
  applied_at?: string;
  updated_at?: string;
};

/**
 * Create or update an application.
 */
export async function saveApplication(app: Application) {
  return supabase.from("applications").upsert({
    ...app,
    updated_at: new Date().toISOString(),
  });
}

/**
 * Fetch all applications for a user.
 */
export async function getApplications(userId: string) {
  return supabase
    .from("applications")
    .select("*, jobs(*), resumes(*)")
    .eq("user_id", userId)
    .order("applied_at", { ascending: false });
}

/**
 * Fetch applications for a specific job.
 */
export async function getApplicationsByJob(jobId: string) {
  return supabase
    .from("applications")
    .select("*, resumes(*)")
    .eq("job_id", jobId);
}

// ──────────────────────────────────────────────────────────────
// Resume Versions helpers
// ──────────────────────────────────────────────────────────────

export async function getResumeVersions(userId: string, resumeId?: string) {
  let q = supabase.from("resume_versions").select("*").eq("user_id", userId);
  if (resumeId) q = q.eq("resume_id", resumeId);
  return q.order("created_at", { ascending: false });
}

export async function saveResumeVersion(version: {
  user_id: string;
  resume_id?: string;
  job_id?: string;
  version_name: string;
  original_text?: string;
  tailored_text: string;
  tailored_content?: Record<string, unknown>;
  ats_score?: number;
  missing_skills?: string[];
}) {
  return supabase.from("resume_versions").insert([version]).select().single();
}

// ──────────────────────────────────────────────────────────────
// Cover Letters helpers
// ──────────────────────────────────────────────────────────────

export async function saveCoverLetter(letter: {
  user_id: string;
  job_id?: string;
  type: string;
  content: string;
  metadata?: Record<string, unknown>;
}) {
  return supabase.from("cover_letters").insert([letter]).select().single();
}

export async function getCoverLetters(userId: string) {
  return supabase
    .from("cover_letters")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });
}

// ──────────────────────────────────────────────────────────────
// Notifications helpers
// ──────────────────────────────────────────────────────────────

export async function createNotification(
  userId: string,
  type: string,
  title: string,
  message: string,
  metadata: Record<string, unknown> = {}
) {
  return supabase.from("notifications").insert([{ user_id: userId, type, title, message, metadata }]);
}

export async function getUnreadNotifications(userId: string) {
  return supabase
    .from("notifications")
    .select("*")
    .eq("user_id", userId)
    .eq("read", false)
    .order("created_at", { ascending: false });
}

export async function markNotificationRead(notificationId: string) {
  return supabase.from("notifications").update({ read: true }).eq("id", notificationId);
}

// ──────────────────────────────────────────────────────────────
// Analytics helpers
// ──────────────────────────────────────────────────────────────

export async function getApplicationStats(userId: string) {
  const { data, error } = await supabase
    .from("applications")
    .select("stage, applied_at")
    .eq("user_id", userId);

  if (error || !data) return { total: 0, byStage: {}, recentDays: [] };

  const byStage: Record<string, number> = {};
  data.forEach(({ stage }) => {
    const s = stage || "APPLIED";
    byStage[s] = (byStage[s] || 0) + 1;
  });

  // Last 7 days counts
  const recentDays: { date: string; count: number }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    recentDays.push({
      date: dateStr,
      count: data.filter((a) => a.applied_at?.slice(0, 10) === dateStr).length,
    });
  }

  return { total: data.length, byStage, recentDays };
}

// ──────────────────────────────────────────────────────────────
// Company Watchlist helpers
// ──────────────────────────────────────────────────────────────

export async function getWatchlist(userId: string) {
  return supabase
    .from("company_watchlist")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });
}

export async function addToWatchlist(userId: string, company: string, keywords: string[] = []) {
  return supabase
    .from("company_watchlist")
    .upsert([{ user_id: userId, company, keywords }], { onConflict: "user_id,company" });
}

export async function removeFromWatchlist(userId: string, company: string) {
  return supabase
    .from("company_watchlist")
    .delete()
    .eq("user_id", userId)
    .eq("company", company);
}
