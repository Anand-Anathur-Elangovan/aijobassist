"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getResumes, getJobs } from "@/lib/supabase";
import { supabase } from "@/lib/supabase";
import { useSubscription } from "@/components/SubscriptionGuard";
import LogPanel from "@/components/LogPanel";
import type { LogEntry } from "@/lib/types";

type ResumeRow = { id: string; title: string; created_at: string; parsed_text?: string };
type JobRow = { id: string; company: string; role: string; status: string };
type TaskRow = {
  id: string;
  type: string;
  status: string;
  created_at: string;
  progress?: number;
  current_job?: string;
  logs?: LogEntry[];
  paused?: boolean;
  stop_requested?: boolean;
  custom_prompt_override?: string;
  output?: {
    applied_count?: number;
    message?: string;
    report?: Array<{
      company: string;
      job_title: string;
      url: string;
      score?: number | null;
      status: string;
      skip_reason?: string;
    }>;
  } | null;
};

type EmploymentEntry = {
  company: string;
  position: string;
  city: string;
  start_month: string;
  start_year: string;
  end_month: string;
  end_year: string;
  is_current: boolean;
  description: string;
};

type EducationEntry = {
  school: string;
  city: string;
  degree: string;
  major: string;
  start_month: string;
  start_year: string;
  end_month: string;
  end_year: string;
  gpa: string;
};

type ProjectEntry = {
  name: string;
  url: string;
  technologies: string;
  description: string;
};

const EMPTY_EMPLOYMENT: EmploymentEntry = {
  company: "", position: "", city: "", start_month: "", start_year: "",
  end_month: "", end_year: "", is_current: false, description: "",
};
const EMPTY_EDUCATION: EducationEntry = {
  school: "", city: "", degree: "", major: "", start_month: "", start_year: "",
  end_month: "", end_year: "", gpa: "",
};
const EMPTY_PROJECT: ProjectEntry = {
  name: "", url: "", technologies: "", description: "",
};

const MONTHS = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const YEARS = Array.from({ length: 30 }, (_, i) => String(new Date().getFullYear() - i));

export default function DashboardPage() {
  const { user } = useAuth();
  const { plan, subscription, usage, getRemaining } = useSubscription();
  const [resumes, setResumes] = useState<ResumeRow[]>([]);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [appsCount, setAppsCount] = useState(0);
  const [loadingData, setLoadingData] = useState(true);
  const [taskLoading, setTaskLoading] = useState(false);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneCountry, setPhoneCountry] = useState("India (+91)");
  const [phoneCountryCode, setPhoneCountryCode] = useState("in");
  const [yearsExp, setYearsExp] = useState("2");
  const [skillRating, setSkillRating] = useState("8");
  const [keywords, setKeywords] = useState("Software Engineer");
  const [keywords2, setKeywords2] = useState("");
  const [keywords3, setKeywords3] = useState("");
  const [locationList, setLocationList] = useState<string[]>([]);
  const [locationInput, setLocationInput] = useState("");
  const [remoteEnabled, setRemoteEnabled] = useState(false);
  const [maxApply, setMaxApply] = useState("5");
  const [noticePeriod, setNoticePeriod] = useState("30");
  const [salaryExpectation, setSalaryExpectation] = useState("");
  const [currentCtc, setCurrentCtc] = useState("");
  // Profile fields for form filling
  const [currentCity, setCurrentCity] = useState("");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [portfolioUrl, setPortfolioUrl] = useState("");
  const [highestEducation, setHighestEducation] = useState("");
  // EEO / Diversity fields
  const [workAuthorization, setWorkAuthorization] = useState("");
  const [nationality, setNationality] = useState("");
  const [countryOfOrigin, setCountryOfOrigin] = useState("");
  const [gender, setGender] = useState("");
  const [disabilityStatus, setDisabilityStatus] = useState("");
  const [veteranStatus, setVeteranStatus] = useState("");
  const [ethnicity, setEthnicity] = useState("");
  // Employment, Education & Projects — persisted to user_profiles.job_preferences
  const [employments, setEmployments] = useState<EmploymentEntry[]>([]);
  const [educations, setEducations] = useState<EducationEntry[]>([]);
  const [projects, setProjects] = useState<ProjectEntry[]>([]);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [platform, setPlatform] = useState<"linkedin" | "naukri">("linkedin");
  const [semiAuto, setSemiAuto] = useState(false);
  const [applyMode, setApplyMode] = useState<"auto" | "tailor" | "url">("auto");
  const [manualUrls, setManualUrls] = useState("");
  const [urlTailor, setUrlTailor] = useState(true);
  const [resumeAutoLoaded, setResumeAutoLoaded] = useState(false);
  // Tailor & Apply extra state
  const [tailorPrompt, setTailorPrompt] = useState("");
  const [favCompanies, setFavCompanies] = useState<string[]>([]);
  const [favCompanyInput, setFavCompanyInput] = useState("");
  // Naukri-specific apply type preference
  const [naukriApplyTypes, setNaukriApplyTypes] = useState<"both" | "direct_only" | "company_site_only">("both");
  // LinkedIn apply type preference
  const [linkedinApplyTypes, setLinkedinApplyTypes] = useState<"easy_apply_only" | "external_only" | "both">("easy_apply_only");
  // LinkedIn search filters
  const [linkedinDatePosted, setLinkedinDatePosted] = useState<"any" | "past24h" | "pastWeek" | "pastMonth">("any");
  const [linkedinExpLevel, setLinkedinExpLevel] = useState<"all" | "internship" | "entry" | "associate" | "mid" | "director" | "executive">("all");
  const [linkedinJobType, setLinkedinJobType] = useState<"all" | "fullTime" | "partTime" | "contract" | "temporary" | "internship">("all");
  // Naukri search filters
  const [naukriDatePosted, setNaukriDatePosted] = useState<"any" | "1" | "3" | "7" | "15" | "30">("any");
  const [naukriWorkMode, setNaukriWorkMode] = useState<"any" | "remote" | "hybrid" | "office">("any");
  const [naukriJobType, setNaukriJobType] = useState<"all" | "fullTime" | "partTime" | "contract" | "temporary">("all");
  // Smart Match — AI resume vs JD scoring gate
  const [smartMatch, setSmartMatch] = useState(false);
  const [matchThreshold, setMatchThreshold] = useState(70);
  // Tailor target — minimum ATS score to aim for when tailoring
  const [tailorTargetScore, setTailorTargetScore] = useState(90);
  // Auto Cover Letter — generate AI cover letter per application
  const [autoCoverLetter, setAutoCoverLetter] = useState(true);
  // Smart Apply Scheduler — only apply within a time window
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleStartHour, setScheduleStartHour] = useState(9);
  const [scheduleEndHour, setScheduleEndHour] = useState(23);
  // Platform login credentials (optional — stored client-side only, passed to bot)
  const [linkedinEmail, setLinkedinEmail] = useState("");
  const [linkedinPassword, setLinkedinPassword] = useState("");
  const [linkedinCookie, setLinkedinCookie] = useState("");
  const [showLinkedinPwd, setShowLinkedinPwd] = useState(false);
  const [showLinkedinCookie, setShowLinkedinCookie] = useState(false);
  // Gmail follow-up settings
  const [gmailAddress, setGmailAddress] = useState("");
  const [gmailAppPassword, setGmailAppPassword] = useState("");
  const [showGmailPwd, setShowGmailPwd] = useState(false);
  const [followupDays, setFollowupDays] = useState("3");
  const [gmailSaving, setGmailSaving] = useState(false);
  const [tailorResult, setTailorResult] = useState<{
    score_before: number;
    score_after: number;
    tailored_text: string;
    tailored_summary: string;
    tailored_bullets: string[];
    ats_score: number;
    improvements: string[];
    missing_skills: string[];
    added_keywords: string[];
  } | null>(null);
  const [tailorLoading, setTailorLoading] = useState(false);
  const [suggestingKeywords, setSuggestingKeywords] = useState(false);
  const [suggestedKeywords, setSuggestedKeywords] = useState<string[]>([]);
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [editedResume, setEditedResume] = useState("");

  // Live run monitor state
  const [liveTask, setLiveTask] = useState<TaskRow | null>(null);
  const [livePrompt, setLivePrompt] = useState("");
  const [livePromptSaving, setLivePromptSaving] = useState(false);
  // Job history reset
  const [resetHistoryLoading, setResetHistoryLoading] = useState(false);
  const [resetSmartMatchLoading, setResetSmartMatchLoading] = useState(false);

  // ── Cloud execution state ──────────────────────────────────
  const [execMode, setExecMode] = useState<"local" | "cloud">("local");
  const [railwayConfigured, setRailwayConfigured] = useState(false);
  const [railwayQuota, setRailwayQuota] = useState<{ used: number; limit: number; remaining: number }>({ used: 0, limit: 5, remaining: 5 });
  const [railwaySessionId, setRailwaySessionId] = useState<string | null>(null);
  const [railwayTaskId, setRailwayTaskId] = useState<string | null>(null);
  const [liveScreenshot, setLiveScreenshot] = useState<string | null>(null);
  const [railwayStatus, setRailwayStatus] = useState<"idle" | "running" | "done">("idle");
  const [railwayProgress, setRailwayProgress] = useState(0);
  const [railwayCurrentJob, setRailwayCurrentJob] = useState<string | null>(null);
  const [railwayLogs, setRailwayLogs] = useState<Array<{ message: string; level?: string; ts?: string }>>([]);
  const [railwayStopping, setRailwayStopping] = useState(false);
  const [showScreenshot, setShowScreenshot] = useState(true);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const cloudPollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cloudStoppedRef = useRef(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const fetchTasks = async () => {
    const { data } = await supabase.from("tasks").select("*").order("created_at", { ascending: false });
    if (data) {
      const rows = data as TaskRow[];
      setTasks(rows);
      // Keep liveTask in sync if it's in the list
      const running = rows.find((t) => t.status === "RUNNING");
      if (running) setLiveTask(running);
    }
  };

  useEffect(() => {
    if (!user) return;
    Promise.all([
      getResumes(user.id),
      getJobs(user.id),
      supabase.from("applications").select("id", { count: "exact", head: true }).eq("user_id", user.id),
    ]).then(([resumeRes, jobsRes, appsRes]) => {
      if (resumeRes.data) {
        setResumes(resumeRes.data as ResumeRow[]);
        // Pre-load parsed_text of the latest resume for the tailor preview
        const latest = (resumeRes.data as ResumeRow[])[0];
        if (latest?.parsed_text) {
          setResumeText(latest.parsed_text);
          setResumeAutoLoaded(true);
        }
      }
      if (jobsRes.data) setJobs(jobsRes.data as JobRow[]);
      setAppsCount(appsRes.count ?? 0);
    }).finally(() => setLoadingData(false));

    // Load gmail/follow-up settings
    supabase.from("gmail_settings").select("*").eq("user_id", user.id).maybeSingle().then(({ data }) => {
      if (data) {
        setGmailAddress(data.gmail_address || "");
        setGmailAppPassword(data.app_password || "");
        setFollowupDays(String(data.followup_days ?? 3));
      }
    });

    // Load saved profile fields from user_profiles.job_preferences
    supabase.from("user_profiles").select("job_preferences").eq("user_id", user.id).maybeSingle().then(({ data }) => {
      if (data?.job_preferences) {
        const p = data.job_preferences as Record<string, unknown>;
        // Profile fields
        if (p.current_city) setCurrentCity(p.current_city as string);
        if (p.first_name) setFirstName(p.first_name as string);
        if (p.last_name) setLastName(p.last_name as string);
        if (p.linkedin_url) setLinkedinUrl(p.linkedin_url as string);
        if (p.github_url) setGithubUrl(p.github_url as string);
        if (p.portfolio_url) setPortfolioUrl(p.portfolio_url as string);
        if (p.highest_education) setHighestEducation(p.highest_education as string);
        // EEO / Diversity
        if (p.work_authorization) setWorkAuthorization(p.work_authorization as string);
        if (p.nationality) setNationality(p.nationality as string);
        if (p.country_of_origin) setCountryOfOrigin(p.country_of_origin as string);
        if (p.gender) setGender(p.gender as string);
        if (p.disability_status) setDisabilityStatus(p.disability_status as string);
        if (p.veteran_status) setVeteranStatus(p.veteran_status as string);
        if (p.ethnicity) setEthnicity(p.ethnicity as string);
        if (p.phone) setPhone(p.phone as string);
        if (p.phone_country) setPhoneCountry(p.phone_country as string);
        if (p.phone_country_code) setPhoneCountryCode(p.phone_country_code as string);
        if (p.years_experience) setYearsExp(String(p.years_experience));
        if (p.notice_period) setNoticePeriod(String(p.notice_period));
        if (p.salary_expectation) setSalaryExpectation(String(p.salary_expectation));
        if (p.current_ctc) setCurrentCtc(String(p.current_ctc));
        if (Array.isArray(p.employments)) setEmployments(p.employments as EmploymentEntry[]);
        if (Array.isArray(p.educations)) setEducations(p.educations as EducationEntry[]);
        if (Array.isArray(p.projects)) setProjects(p.projects as ProjectEntry[]);
        // Search & automation settings
        if (p.keywords) setKeywords(p.keywords as string);
        if (p.keywords2 !== undefined) setKeywords2(p.keywords2 as string);
        if (p.keywords3 !== undefined) setKeywords3(p.keywords3 as string);
        if (Array.isArray(p.location_list)) setLocationList(p.location_list as string[]);
        if (p.remote_enabled !== undefined) setRemoteEnabled(p.remote_enabled as boolean);
        if (p.max_apply) setMaxApply(String(p.max_apply));
        if (p.skill_rating) setSkillRating(String(p.skill_rating));
        if (p.platform) setPlatform(p.platform as "linkedin" | "naukri");
        if (p.semi_auto !== undefined) setSemiAuto(p.semi_auto as boolean);
        if (p.apply_mode) setApplyMode(p.apply_mode as "auto" | "tailor" | "url");
        if (p.auto_cover_letter !== undefined) setAutoCoverLetter(p.auto_cover_letter as boolean);
        if (p.smart_match !== undefined) setSmartMatch(p.smart_match as boolean);
        if (p.match_threshold) setMatchThreshold(p.match_threshold as number);
        if (p.tailor_target_score) setTailorTargetScore(p.tailor_target_score as number);
        if (p.schedule_enabled !== undefined) setScheduleEnabled(p.schedule_enabled as boolean);
        if (p.schedule_start_hour !== undefined) setScheduleStartHour(p.schedule_start_hour as number);
        if (p.schedule_end_hour !== undefined) setScheduleEndHour(p.schedule_end_hour as number);
        if (p.tailor_prompt !== undefined) setTailorPrompt(p.tailor_prompt as string);
        if (Array.isArray(p.fav_companies)) setFavCompanies(p.fav_companies as string[]);
        // Platform filters
        if (p.linkedin_date_posted) setLinkedinDatePosted(p.linkedin_date_posted as "any" | "past24h" | "pastWeek" | "pastMonth");
        if (p.linkedin_exp_level) setLinkedinExpLevel(p.linkedin_exp_level as "all" | "internship" | "entry" | "associate" | "mid" | "director" | "executive");
        if (p.linkedin_job_type) setLinkedinJobType(p.linkedin_job_type as "all" | "fullTime" | "partTime" | "contract" | "temporary" | "internship");
        if (p.naukri_date_posted) setNaukriDatePosted(p.naukri_date_posted as "any" | "1" | "3" | "7" | "15" | "30");
        if (p.naukri_work_mode) setNaukriWorkMode(p.naukri_work_mode as "any" | "remote" | "hybrid" | "office");
        if (p.naukri_job_type) setNaukriJobType(p.naukri_job_type as "all" | "fullTime" | "partTime" | "contract" | "temporary");
        if (p.naukri_apply_types) setNaukriApplyTypes(p.naukri_apply_types as "both" | "direct_only" | "company_site_only");
        if (p.linkedin_apply_types) setLinkedinApplyTypes(p.linkedin_apply_types as "easy_apply_only" | "external_only" | "both");
        // Credentials
        if (p.linkedin_email) setLinkedinEmail(p.linkedin_email as string);
        if (p.linkedin_password) setLinkedinPassword(p.linkedin_password as string);
        if (p.linkedin_cookie) setLinkedinCookie(p.linkedin_cookie as string);
      }
      setProfileLoaded(true);
    });

    fetchTasks();

    // Supabase Realtime — subscribe to task row changes for this user
    const channel = supabase
      .channel("tasks-live")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "tasks", filter: `user_id=eq.${user.id}` },
        (payload) => {
          const updated = payload.new as TaskRow;
          setTasks((prev) => {
            const idx = prev.findIndex((t) => t.id === updated.id);
            if (idx === -1) return [updated, ...prev];
            const next = [...prev];
            next[idx] = updated;
            return next;
          });
          if (updated.status === "RUNNING") setLiveTask(updated);
          if (updated.status === "DONE" || updated.status === "FAILED") {
            setLiveTask((cur) => (cur?.id === updated.id ? updated : cur));
          }
        }
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [user]);

  const resetJobHistory = async (targetPlatform?: "linkedin" | "naukri") => {
    setResetHistoryLoading(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { alert("Not logged in"); return; }
      const url = `/api/job-history/reset${targetPlatform ? `?platform=${targetPlatform}` : ""}`;
      const res = await fetch(url, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      const json = await res.json();
      if (res.ok) {
        alert(json.message || "History reset successfully.");
      } else {
        alert("Reset failed: " + (json.error || res.statusText));
      }
    } catch (e) {
      alert("Reset failed: " + String(e));
    } finally {
      setResetHistoryLoading(false);
    }
  };

  const resetSmartMatchHistory = async () => {
    setResetSmartMatchLoading(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { alert("Not logged in"); return; }
      const res = await fetch("/api/job-history/reset?type=smart_match", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      const json = await res.json();
      if (res.ok) {
        alert(json.message || "Smart Match history cleared — those jobs will be re-evaluated on next run.");
      } else {
        alert("Reset failed: " + (json.error || res.statusText));
      }
    } catch (e) {
      alert("Reset failed: " + String(e));
    } finally {
      setResetSmartMatchLoading(false);
    }
  };

  const suggestKeywordsFromResume = async () => {
    setSuggestingKeywords(true);
    setSuggestedKeywords([]);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token;
      if (!token) throw new Error("Not authenticated");
      const res = await fetch("/api/ai/suggest-keywords", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to suggest keywords");
      setSuggestedKeywords(data.keywords ?? []);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to generate keywords");
    } finally {
      setSuggestingKeywords(false);
    }
  };

  const saveProfile = async (silent = false) => {
    const { data: userData } = await supabase.auth.getUser();
    const u = userData.user;
    if (!u) { if (!silent) alert("Not logged in"); return; }
    if (!silent) setProfileSaving(true);
    const prefs = {
      // Profile fields
      current_city: currentCity.trim(),
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      linkedin_url: linkedinUrl.trim(),
      github_url: githubUrl.trim(),
      portfolio_url: portfolioUrl.trim(),
      highest_education: highestEducation.trim(),
      phone: phone.trim(),
      phone_country: phoneCountry,
      phone_country_code: phoneCountryCode,
      years_experience: Number(yearsExp) || 0,
      notice_period: Number(noticePeriod) || 0,
      salary_expectation: salaryExpectation ? Number(salaryExpectation) : null,
      current_ctc: currentCtc ? Number(currentCtc) : null,
      employments: employments.filter(e => e.company.trim() || e.position.trim()),
      educations: educations.filter(e => e.school.trim() || e.degree.trim()),
      projects: projects.filter(p => p.name.trim()),
      // EEO / Diversity fields
      work_authorization: workAuthorization,
      nationality: nationality.trim(),
      country_of_origin: countryOfOrigin.trim(),
      gender,
      disability_status: disabilityStatus,
      veteran_status: veteranStatus,
      ethnicity,
      // Search & automation settings (persist across refresh)
      keywords: keywords.trim(),
      keywords2: keywords2.trim(),
      keywords3: keywords3.trim(),
      location_list: locationList,
      remote_enabled: remoteEnabled,
      max_apply: Number(maxApply) || 5,
      skill_rating: Number(skillRating) || 8,
      platform,
      semi_auto: semiAuto,
      apply_mode: applyMode === "url" ? "auto" : applyMode,  // persist underlying mode, not URL tab
      auto_cover_letter: autoCoverLetter,
      smart_match: smartMatch,
      match_threshold: matchThreshold,
      tailor_target_score: tailorTargetScore,
      schedule_enabled: scheduleEnabled,
      schedule_start_hour: scheduleStartHour,
      schedule_end_hour: scheduleEndHour,
      tailor_prompt: tailorPrompt,
      fav_companies: favCompanies,
      // Platform-specific filters
      linkedin_date_posted: linkedinDatePosted,
      linkedin_exp_level: linkedinExpLevel,
      linkedin_job_type: linkedinJobType,
      naukri_date_posted: naukriDatePosted,
      naukri_work_mode: naukriWorkMode,
      naukri_job_type: naukriJobType,
      naukri_apply_types: naukriApplyTypes,
      linkedin_apply_types: linkedinApplyTypes,
      // Credentials — persisted so Railway cloud launch can use them
      ...(linkedinEmail.trim() && { linkedin_email: linkedinEmail.trim() }),
      ...(linkedinPassword.trim() && { linkedin_password: linkedinPassword.trim() }),
      ...(linkedinCookie.trim() && { linkedin_cookie: linkedinCookie.trim() }),
    };
    const { error } = await supabase.from("user_profiles").upsert(
      { user_id: u.id, job_preferences: prefs, updated_at: new Date().toISOString() },
      { onConflict: "user_id" }
    );
    if (!silent) {
      setProfileSaving(false);
      if (error) alert("Save failed: " + error.message);
      else alert("Profile saved ✓");
    }
  };

  const createTask = async () => {
    const { data: userData } = await supabase.auth.getUser();
    const u = userData.user;
    if (!u) { alert("User not logged in"); return; }

    // ── Credential validation for auto/tailor modes ──────────
    if (applyMode !== "url" && !semiAuto) {
      const hasCreds = linkedinCookie.trim() || (linkedinEmail.trim() && linkedinPassword.trim());
      if (!hasCreds) {
        alert(`Please enter your ${platform === "linkedin" ? "LinkedIn" : "Naukri"} credentials before starting Auto Apply.\n\nFor cloud runs, use the li_at cookie (recommended). Otherwise enter your email and password.\n\nYour credentials are only used to log in during the automation run.`);
        return;
      }
    }

    // Auto-save profile before creating task
    await saveProfile(true);

    setTaskLoading(true);

    // ── URL Apply mode: validate and create URL_APPLY task ──────────
    if (applyMode === "url") {
      const urls = manualUrls
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line && (line.includes("linkedin.com") || line.includes("naukri.com")));
      if (urls.length === 0) {
        alert("Please enter at least one valid LinkedIn or Naukri job URL (one per line).");
        setTaskLoading(false);
        return;
      }
      const { error } = await supabase.from("tasks").insert([{
        user_id: u.id,
        type: "URL_APPLY",
        status: "PENDING",
        input: {
          manual_urls: urls,
          tailor_resume: urlTailor,
          ...(urlTailor && tailorPrompt.trim() && { tailor_custom_prompt: tailorPrompt.trim() }),
          ...(urlTailor && { tailor_target_score: tailorTargetScore }),
          ...(smartMatch && { smart_match: true, match_threshold: matchThreshold }),
          // Profile / form-fill fields
          phone,
          phone_country: phoneCountry,
          phone_country_code: phoneCountryCode,
          years_experience: Number(yearsExp),
          skill_rating: Number(skillRating),
          notice_period: Number(noticePeriod),
          ...(currentCity.trim() && { current_city: currentCity.trim() }),
          ...(firstName.trim() && { first_name: firstName.trim() }),
          ...(lastName.trim() && { last_name: lastName.trim() }),
          ...(linkedinUrl.trim() && { linkedin_url: linkedinUrl.trim() }),
          ...(githubUrl.trim() && { github_url: githubUrl.trim() }),
          ...(portfolioUrl.trim() && { portfolio_url: portfolioUrl.trim() }),
          ...(highestEducation.trim() && { highest_education: highestEducation.trim() }),
          ...(employments.length > 0 && { employments }),
          ...(educations.length > 0 && { educations }),
          ...(projects.length > 0 && { projects }),
          // EEO / Diversity
          ...(workAuthorization && { work_authorization: workAuthorization }),
          ...(nationality.trim() && { nationality: nationality.trim() }),
          ...(countryOfOrigin.trim() && { country_of_origin: countryOfOrigin.trim() }),
          ...(gender && { gender }),
          ...(disabilityStatus && { disability_status: disabilityStatus }),
          ...(veteranStatus && { veteran_status: veteranStatus }),
          ...(ethnicity && { ethnicity }),
          full_name: (firstName.trim() && lastName.trim()) ? `${firstName.trim()} ${lastName.trim()}` : (u.user_metadata?.full_name || u.email?.split("@")[0] || ""),
          email: u.email || "",
          ...(linkedinEmail && { linkedin_email: linkedinEmail }),
          ...(linkedinPassword && { linkedin_password: linkedinPassword }),
          ...(linkedinCookie && { linkedin_cookie: linkedinCookie }),
          linkedin_apply_types: linkedinApplyTypes,
          semi_auto: semiAuto,
          auto_cover_letter: autoCoverLetter,
          ...(scheduleEnabled && { schedule_start_hour: scheduleStartHour, schedule_end_hour: scheduleEndHour }),
        },
      }]);
      if (error) {
        console.error(error);
        alert("Error creating task: " + error.message);
      } else {
        fetchTasks();
      }
      setTaskLoading(false);
      return;
    }

    const taskType = applyMode === "tailor" ? "TAILOR_AND_APPLY" : "AUTO_APPLY";
    const isCloud = execMode === "cloud" && railwayConfigured;
    const { data: newTask, error } = await supabase.from("tasks").insert([{
      user_id: u.id,
      type: taskType,
      status: "PENDING",
      ...(isCloud && { execution_mode: "railway" }),
      input: {
        platform,
        semi_auto: semiAuto,
        phone,
        phone_country: phoneCountry,
        phone_country_code: phoneCountryCode,
        years_experience: Number(yearsExp),
        skill_rating: Number(skillRating),
        keywords,
        ...(keywords2.trim() && { keywords2: keywords2.trim() }),
        ...(keywords3.trim() && { keywords3: keywords3.trim() }),
        location: [...(remoteEnabled ? ["Remote"] : []), ...locationList].join(",") || "",
        max_apply: Number(maxApply),
        notice_period: Number(noticePeriod),
        salary_expectation: salaryExpectation ? Number(salaryExpectation) : undefined,
        ...(currentCtc && { current_ctc: Number(currentCtc) }),
        followup_days: Number(followupDays),
        // Profile fields for AI form filling
        ...(currentCity.trim() && { current_city: currentCity.trim() }),
        ...(firstName.trim() && { first_name: firstName.trim() }),
        ...(lastName.trim() && { last_name: lastName.trim() }),
        ...(linkedinUrl.trim() && { linkedin_url: linkedinUrl.trim() }),
        ...(githubUrl.trim() && { github_url: githubUrl.trim() }),
        ...(portfolioUrl.trim() && { portfolio_url: portfolioUrl.trim() }),
        ...(highestEducation.trim() && { highest_education: highestEducation.trim() }),
        // Employment, Education & Projects
        ...(employments.length > 0 && { employments }),
        ...(educations.length > 0 && { educations }),
        ...(projects.length > 0 && { projects }),
        // EEO / Diversity
        ...(workAuthorization && { work_authorization: workAuthorization }),
        ...(nationality.trim() && { nationality: nationality.trim() }),
        ...(countryOfOrigin.trim() && { country_of_origin: countryOfOrigin.trim() }),
        ...(gender && { gender }),
        ...(disabilityStatus && { disability_status: disabilityStatus }),
        ...(veteranStatus && { veteran_status: veteranStatus }),
        ...(ethnicity && { ethnicity }),
        full_name: (firstName.trim() && lastName.trim()) ? `${firstName.trim()} ${lastName.trim()}` : (u.user_metadata?.full_name || u.email?.split("@")[0] || ""),
        email: u.email || "",
        ...(linkedinEmail && { linkedin_email: linkedinEmail }),
        ...(linkedinPassword && { linkedin_password: linkedinPassword }),
        ...(linkedinCookie && { linkedin_cookie: linkedinCookie }),
        ...(gmailAddress && { gmail_address: gmailAddress }),
        ...(gmailAppPassword && { gmail_app_password: gmailAppPassword }),
        ...(applyMode === "tailor" && {
          tailor_resume: true,
          tailor_custom_prompt: tailorPrompt,
          tailor_target_score: tailorTargetScore,
        }),
        ...(favCompanies.length > 0 && { favorite_companies: favCompanies }),
        ...(platform === "naukri" && {
          apply_types: naukriApplyTypes,
          ...(naukriDatePosted !== "any" && { freshness_days: Number(naukriDatePosted) }),
          ...(naukriWorkMode !== "any" ? { work_mode: naukriWorkMode } : remoteEnabled ? { work_mode: "remote" } : {}),
          ...(naukriJobType !== "all" && { naukri_job_type: naukriJobType }),
        }),
        ...(platform === "linkedin" && {
          linkedin_date_posted: linkedinDatePosted,
          linkedin_remote: remoteEnabled,
          linkedin_apply_types: linkedinApplyTypes,
          ...(linkedinExpLevel !== "all" && { linkedin_exp_level: linkedinExpLevel }),
          ...(linkedinJobType !== "all" && { linkedin_job_type: linkedinJobType }),
        }),
        ...(smartMatch && { smart_match: true, match_threshold: matchThreshold }),
        auto_cover_letter: autoCoverLetter,
        ...(scheduleEnabled && {
          schedule_start_hour: scheduleStartHour,
          schedule_end_hour:   scheduleEndHour,
        }),
      },
    }]).select("id").single();

    if (error || !newTask) {
      console.error(error);
      alert("Error creating task: " + (error?.message ?? "Unknown"));
    } else {
      fetchTasks();

      // ── If cloud mode, trigger Railway ──────────────────────
      if (isCloud) {
        const session = await supabase.auth.getSession();
        const token = session.data.session?.access_token;
        if (token) {
          const res = await fetch("/api/railway/trigger", {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body: JSON.stringify({ task_id: newTask.id, task_type: taskType, task_input: {} }),
          });
          if (res.ok) {
            const triggerData = await res.json();
            setRailwaySessionId(triggerData.session_id);
            setRailwayTaskId(newTask.id);
            setRailwayStatus("running");
            setRailwayLogs([]);
            setLiveScreenshot(null);
            setRailwayProgress(0);
            setRailwayCurrentJob(null);
            startCloudPoll(triggerData.session_id, newTask.id);
            fetchRailwayInfo();
          } else {
            const err = await res.json().catch(() => ({}));
            alert(`Failed to start cloud job: ${err.error ?? res.statusText}`);
          }
        }
      }
    }
    setTaskLoading(false);
  };

  const saveGmailSettings = async () => {
    const { data: userData } = await supabase.auth.getUser();
    const u = userData.user;
    if (!u) { alert("Not logged in"); return; }
    if (!gmailAddress.trim()) { alert("Enter your Gmail address first."); return; }
    setGmailSaving(true);
    const { error } = await supabase.from("gmail_settings").upsert({
      user_id: u.id,
      gmail_address: gmailAddress.trim(),
      app_password: gmailAppPassword.trim(),
      followup_days: Number(followupDays),
    }, { onConflict: "user_id" });
    setGmailSaving(false);
    if (error) alert("Error saving: " + error.message);
    else alert("Gmail settings saved ✓");
  };

  const runTailorPreview = async () => {
    if (!resumeText.trim() || !jdText.trim()) {
      alert("Paste your resume text and job description to preview tailoring.");
      return;
    }
    setTailorLoading(true);
    setTailorResult(null);
    try {
      const res = await fetch("/api/ai/tailor-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resumeText,
          jd_text: jdText,
          custom_prompt: tailorPrompt,
          action: "tailor",
        }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setTailorResult(data);
      setEditedResume(data.tailored_text);
    } catch (e) {
      alert("Tailoring failed: " + (e as Error).message);
    } finally {
      setTailorLoading(false);
    }
  };

  // ── Live run controls ──────────────────────────────────────
  const togglePause = async () => {
    if (!liveTask) return;
    await supabase.from("tasks").update({ paused: !liveTask.paused }).eq("id", liveTask.id);
  };

  const requestStop = async () => {
    if (!liveTask) return;
    if (!confirm("Stop the run after the current application?")) return;
    await supabase.from("tasks").update({ stop_requested: true }).eq("id", liveTask.id);
  };

  const sendLivePrompt = async () => {
    if (!liveTask || !livePrompt.trim()) return;
    setLivePromptSaving(true);
    await supabase
      .from("tasks")
      .update({ custom_prompt_override: livePrompt.trim() })
      .eq("id", liveTask.id);
    setLivePromptSaving(false);
    setLivePrompt("");
  };

  // ── Cloud / Railway helpers ────────────────────────────────
  useEffect(() => {
    if (!user) return;
    fetchRailwayInfo();
  }, [user]);

  async function fetchRailwayInfo() {
    if (!user) return;
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (!token) return;

    const { data: profile } = await supabase
      .from("user_profiles")
      .select("railway_configured, preferred_execution_mode")
      .eq("user_id", user.id)
      .single();

    if (profile) {
      if (profile.preferred_execution_mode === "railway") setExecMode("cloud");
      if (profile.railway_configured) {
        setRailwayConfigured(true);
      } else {
        try {
          const ping = await fetch("/api/railway/status?ping=true", {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (ping.ok) {
            const pj = await ping.json();
            if (pj.reachable) {
              setRailwayConfigured(true);
              await supabase.from("user_profiles").update({ railway_configured: true }).eq("user_id", user.id);
            }
          }
        } catch { /* Railway unreachable */ }
      }
    }

    const today = new Date().toISOString().split("T")[0];
    const { data: usageRow } = await supabase
      .from("railway_daily_usage")
      .select("minutes_used")
      .eq("user_id", user.id)
      .eq("usage_date", today)
      .maybeSingle();
    const used = Number(usageRow?.minutes_used ?? 0);
    const { data: sub } = await supabase
      .from("subscriptions")
      .select("plan_id")
      .eq("user_id", user.id)
      .in("status", ["active", "past_due"])
      .maybeSingle();
    let limit = 5;
    if (sub?.plan_id) {
      const { data: pl } = await supabase
        .from("plan_limits")
        .select("daily_limit")
        .eq("plan_id", sub.plan_id)
        .eq("action_type", "railway_minutes")
        .maybeSingle();
      if (pl) limit = pl.daily_limit;
    }
    setRailwayQuota({ used, limit, remaining: Math.max(0, limit - used) });
  }

  function stopCloudPoll() {
    cloudStoppedRef.current = true;
    if (cloudPollRef.current) { clearTimeout(cloudPollRef.current); cloudPollRef.current = null; }
  }

  function startCloudPoll(sessionId: string, taskId: string) {
    stopCloudPoll();
    cloudStoppedRef.current = false;
    let lastLogCount = 0;

    async function pollCloud() {
      if (cloudStoppedRef.current) return;

      const { data: sess } = await supabase
        .from("railway_sessions")
        .select("status, latest_screenshot")
        .eq("id", sessionId)
        .single();

      if (sess?.latest_screenshot) {
        setLiveScreenshot(`data:image/jpeg;base64,${sess.latest_screenshot}`);
      }

      const { data: task } = await supabase
        .from("tasks")
        .select("status, progress, current_job, logs, output")
        .eq("id", taskId)
        .single();

      if (task) {
        const logs = Array.isArray(task.logs) ? task.logs : [];
        if (logs.length > lastLogCount) {
          const newEntries = logs.slice(lastLogCount).map((e: unknown) =>
            typeof e === "string" ? { message: e, level: "info", ts: new Date().toISOString() }
              : (e as { message?: string; msg?: string; level?: string; ts?: string })
          );
          const normalised = newEntries.map((e) => ({ ...e, message: (e as { message?: string; msg?: string }).message ?? (e as { msg?: string }).msg ?? "" }));
          setRailwayLogs((prev) => [...prev, ...normalised]);
          lastLogCount = logs.length;
        }
        if ((task.progress ?? 0) !== undefined) setRailwayProgress(task.progress ?? 0);
        if (task.current_job) setRailwayCurrentJob(task.current_job);
      }

      const ended = ["completed", "failed", "stopped"].includes(sess?.status ?? "") ||
                    ["DONE", "FAILED"].includes(task?.status ?? "");
      if (ended) {
        setRailwayStatus("done");
        // Update liveTask with the final task data so the completion report shows
        if (task) {
          setLiveTask({ id: taskId, type: "", status: task.status ?? "DONE", created_at: "", progress: task.progress, current_job: task.current_job, logs: task.logs as LogEntry[], output: task.output as TaskRow["output"] });
        }
        setRailwayLogs((prev) => [
          ...prev,
          { message: `Session ended — ${sess?.status ?? task?.status ?? "done"}`, level: "info", ts: new Date().toISOString() },
        ]);
        fetchRailwayInfo();
        return;
      }

      cloudPollRef.current = setTimeout(pollCloud, 2000);
    }

    cloudPollRef.current = setTimeout(pollCloud, 2000);
  }

  async function stopRailwaySession() {
    if (!railwaySessionId || railwayStopping) return;
    setRailwayStopping(true);
    const session = await supabase.auth.getSession();
    const token = session.data.session?.access_token;
    if (!token) { setRailwayStopping(false); return; }
    await fetch("/api/railway/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ session_id: railwaySessionId, task_id: railwayTaskId }),
    });
    stopCloudPoll();
    setRailwayStatus("done");
    setRailwayStopping(false);
    fetchRailwayInfo();
  }

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
      label: "Jobs Tracking",
      value: loadingData ? "…" : jobs.length.toString(),
      sub: "opportunities saved",
      color: jobs.length > 0 ? "text-emerald-400" : "text-slate-500",
    },
    {
      label: "Applications",
      value: loadingData ? "…" : appsCount.toString(),
      sub: "tracked applications",
      color: appsCount > 0 ? "text-sky-400" : "text-slate-500",
    },
  ];

  const QUICK_ACTIONS = [
    { href: "/job-search",    icon: "🔍", title: "Job Search",    desc: "Discover jobs & analyse JDs" },
    { href: "/resume-studio", icon: "✨", title: "Resume Studio", desc: "AI-tailor your resume to any JD" },
    { href: "/applications",  icon: "📋", title: "Applications",  desc: "Track status & follow-ups" },
    { href: "/analytics",     icon: "📊", title: "Analytics",     desc: "See your job search performance" },
    { href: "/upload-resume", icon: "📄", title: "Upload Resume",  desc: "Add or update your latest CV" },
    { href: "/job-preferences", icon: "🎯", title: "Preferences",  desc: "Set your title, salary & location" },
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

      {/* Plan & Usage */}
      {plan && (
        <div className="card mb-12 animate-fadeUp">
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-1">Current Plan</p>
              <p className="font-display font-bold text-xl text-white">{plan.name}
                {subscription?.status === "trial" && (
                  <span className="ml-2 text-xs font-mono text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">
                    Trial&nbsp;·&nbsp;{Math.max(0, Math.ceil((new Date(subscription.trial_ends_at ?? subscription.current_period_end ?? Date.now()).getTime() - Date.now()) / 86400000))}d left
                  </span>
                )}
              </p>
            </div>
            <Link href="/pricing" className="btn-primary text-sm px-4 py-2">
              {subscription?.plan_id === "trial" ? "Upgrade" : "Manage Plan"}
            </Link>
          </div>
          {usage.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {usage.map((u) => {
                const rem = getRemaining(u.action_type);
                const pct = u.limit > 0 ? Math.min(100, (u.used / u.limit) * 100) : 0;
                const labels: Record<string, string> = {
                  auto_apply: "Auto Apply", semi_auto_apply: "Semi Auto",
                  ai_tailor: "AI Tailor", gmail_send: "Gmail", cover_letter: "Cover Letter", jd_analysis: "JD Analysis",
                };
                return (
                  <div key={u.action_type} className="bg-slate-800/50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">{labels[u.action_type] ?? u.action_type}</p>
                    <p className="font-mono text-sm text-white">{rem}/{u.limit}</p>
                    <div className="w-full bg-slate-700 rounded-full h-1.5 mt-1">
                      <div className={`h-1.5 rounded-full ${pct >= 90 ? "bg-red-500" : pct >= 60 ? "bg-amber-400" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Auto Apply */}
      <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Automation
        </h2>
        <div className="card space-y-4">
          {/* Mode sub-tabs */}
          <div className="flex flex-wrap gap-2 border-b border-slate-700 pb-3">
            {([
              ["auto",   "🚀 Auto Apply"],
              ["tailor", "✨ Tailor & Apply"],
              ["url",    "🔗 URL Apply"],
            ] as const).map(([mode, label]) => (
              <button
                key={mode}
                onClick={() => setApplyMode(mode)}
                className={`px-4 py-1.5 rounded-lg font-mono text-sm font-semibold transition-colors ${
                  applyMode === mode
                    ? "bg-amber-500 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* ── URL Apply mode ──────────────────────────────────────────── */}
          {applyMode === "url" && (
            <div className="space-y-3 p-3 rounded-lg border border-sky-400/20 bg-sky-400/5">
              <p className="font-mono text-xs text-sky-400 uppercase tracking-widest">
                Apply to specific job URLs directly
              </p>
              <p className="font-body text-xs text-slate-400">
                Paste LinkedIn or Naukri job page URLs (one per line). The bot will open each URL, extract the job
                description, optionally tailor your resume, and apply — without doing a keyword search.
              </p>
              <div>
                <label className="block font-mono text-xs text-slate-400 mb-1">
                  Job URLs <span className="text-slate-500">(one per line — LinkedIn or Naukri only)</span>
                </label>
                <textarea
                  rows={6}
                  placeholder={
                    "https://www.linkedin.com/jobs/view/3887654321/\nhttps://www.linkedin.com/jobs/view/3991234567/\nhttps://www.naukri.com/job-listings/software-engineer-xyz-123456"
                  }
                  value={manualUrls}
                  onChange={(e) => setManualUrls(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-sky-500 resize-y font-mono"
                  spellCheck={false}
                />
                {/* Platform detection summary */}
                {manualUrls.trim() && (() => {
                  const lines = manualUrls.split("\n").map(l => l.trim()).filter(Boolean);
                  const li = lines.filter(l => l.includes("linkedin.com")).length;
                  const nk = lines.filter(l => l.includes("naukri.com")).length;
                  const other = lines.length - li - nk;
                  return (
                    <div className="flex flex-wrap gap-2 mt-1">
                      {li > 0 && <span className="text-xs font-mono text-blue-400 bg-blue-500/10 border border-blue-500/30 px-2 py-0.5 rounded">🔵 {li} LinkedIn</span>}
                      {nk > 0 && <span className="text-xs font-mono text-orange-400 bg-orange-500/10 border border-orange-500/30 px-2 py-0.5 rounded">🟠 {nk} Naukri</span>}
                      {other > 0 && <span className="text-xs font-mono text-red-400 bg-red-500/10 border border-red-500/30 px-2 py-0.5 rounded">⚠️ {other} unsupported (will be skipped)</span>}
                    </div>
                  );
                })()}
              </div>

              {/* Tailor toggle */}
              <div className="flex items-start gap-3 p-3 rounded-lg border border-slate-700 bg-slate-800/40">
                <input
                  id="url-tailor-toggle"
                  type="checkbox"
                  checked={urlTailor}
                  onChange={(e) => setUrlTailor(e.target.checked)}
                  className="mt-0.5 accent-amber-400 w-4 h-4 cursor-pointer"
                />
                <label htmlFor="url-tailor-toggle" className="cursor-pointer">
                  <p className="font-body font-semibold text-white text-sm">
                    ✨ Tailor resume before applying
                    {urlTailor && <span className="ml-1 text-xs bg-amber-400/15 text-amber-400 px-2 py-0.5 rounded">ON</span>}
                  </p>
                  <p className="font-body text-xs text-slate-400 mt-0.5">
                    For each job, the bot scores your resume against the JD. If the score is below the Smart Match
                    threshold, it tailors your resume — preserving your original PDF&apos;s look — before applying.
                  </p>
                </label>
              </div>

              {/* Custom tailoring instruction */}
              {urlTailor && (
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Custom Tailoring Instruction <span className="text-slate-500">(optional)</span></label>
                  <input
                    type="text"
                    placeholder='e.g. "Emphasise React and system design experience"'
                    value={tailorPrompt}
                    onChange={(e) => setTailorPrompt(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-sky-500"
                  />
                </div>
              )}
            </div>
          )}

          {applyMode === "tailor" && (
            <div className="space-y-3 p-3 rounded-lg border border-amber-400/20 bg-amber-400/5">
              <p className="font-mono text-xs text-amber-400 uppercase tracking-widest">
                AI tailors your resume to each JD before applying
              </p>
              <p className="font-body text-xs text-slate-400">
                When you start a run, the bot reads each job&apos;s description directly from LinkedIn and tailors your uploaded resume automatically — no pasting needed.
                Use the preview below to test the AI on any specific JD before launching.
              </p>
              {/* Tailor target score */}
              <div className="space-y-1.5 p-2.5 rounded-lg border border-amber-400/20 bg-amber-400/5">
                <div className="flex items-center justify-between">
                  <label className="font-mono text-xs text-slate-400">
                    Target ATS score after tailoring
                  </label>
                  <span className="font-mono text-sm font-bold text-amber-400">{tailorTargetScore}%</span>
                </div>
                <input
                  type="range"
                  min={70}
                  max={98}
                  step={5}
                  value={tailorTargetScore}
                  onChange={(e) => setTailorTargetScore(Number(e.target.value))}
                  className="w-full accent-amber-500"
                />
                <p className="font-body text-xs text-slate-500">
                  The bot will tailor your resume to hit this score before applying. Each tailored resume is saved automatically as <span className="text-amber-400/80">Company — Role</span>.
                </p>
              </div>
              {/* Preview section */}
              <div className="space-y-2">
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">
                    Resume Text
                    {resumeAutoLoaded
                      ? <span className="ml-2 text-emerald-400">✓ loaded from your saved resume</span>
                      : <span className="ml-2 text-slate-500">(paste if not auto-loaded)</span>}
                  </label>
                  <textarea
                    rows={4}
                    placeholder="Paste your resume text here to preview AI tailoring…"
                    value={resumeText}
                    onChange={(e) => setResumeText(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500 resize-y font-mono"
                  />
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">
                    Paste a Job Description <span className="text-slate-500">(preview only — bot reads JDs from LinkedIn automatically)</span>
                  </label>
                  <textarea
                    rows={4}
                    placeholder="Paste the job description here…"
                    value={jdText}
                    onChange={(e) => setJdText(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500 resize-y font-mono"
                  />
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Custom Instruction (optional)</label>
                  <input
                    type="text"
                    placeholder='e.g. "Emphasise leadership and Python skills"'
                    value={tailorPrompt}
                    onChange={(e) => setTailorPrompt(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500"
                  />
                </div>
                <button
                  onClick={runTailorPreview}
                  disabled={tailorLoading}
                  className="bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-white font-bold px-4 py-2 rounded-lg text-sm transition-colors"
                >
                  {tailorLoading ? "Tailoring…" : "✨ Preview Tailored Resume"}
                </button>
              </div>

              {/* Result panel */}
              {tailorResult && (
                <div className="space-y-3 mt-2">
                  {/* Score ring row */}
                  <div className="flex gap-6 items-center">
                    {[["Before", tailorResult.score_before, "text-slate-400"], ["After", tailorResult.score_after, "text-emerald-400"], ["ATS", tailorResult.ats_score, "text-amber-400"]].map(([label, val, color]) => (
                      <div key={label as string} className="text-center">
                        <svg width="60" height="60" viewBox="0 0 60 60">
                          <circle cx="30" cy="30" r="24" fill="none" stroke="#1e293b" strokeWidth="6"/>
                          <circle cx="30" cy="30" r="24" fill="none" stroke="currentColor" strokeWidth="6"
                            strokeDasharray={`${(val as number) / 100 * 150.8} 150.8`}
                            strokeLinecap="round" transform="rotate(-90 30 30)"
                            className={color as string}
                          />
                        </svg>
                        <p className={`font-display font-bold text-lg -mt-12 mb-6 ${color}`}>{val}%</p>
                        <p className="font-mono text-xs text-slate-500">{label}</p>
                      </div>
                    ))}
                  </div>
                  {/* Edited resume textarea */}
                  <div>
                    <label className="block font-mono text-xs text-slate-400 mb-1">Tailored Resume (editable)</label>
                    <textarea
                      rows={10}
                      value={editedResume}
                      onChange={(e) => setEditedResume(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500 resize-y font-mono"
                    />
                  </div>
                  {/* Re-tailor */}
                  <button
                    onClick={runTailorPreview}
                    disabled={tailorLoading}
                    className="text-amber-400 border border-amber-400/30 hover:bg-amber-400/10 disabled:opacity-50 font-mono text-xs px-3 py-1.5 rounded-lg transition-colors"
                  >
                    {tailorLoading ? "Re-tailoring…" : "↻ Re-Tailor"}
                  </button>
                  {/* Improvements list */}
                  {tailorResult.improvements.length > 0 && (
                    <div>
                      <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-1">Suggestions</p>
                      <ul className="space-y-1">
                        {tailorResult.improvements.map((tip, i) => (
                          <li key={i} className="font-body text-xs text-slate-400 flex gap-2">
                            <span className="text-amber-400">•</span>{tip}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Target Companies — visible in both Auto Apply and Tailor & Apply */}
          <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
            <label className="block font-mono text-xs text-slate-400 mb-1">
              🏢 Target Companies <span className="text-slate-500">(optional, max 5 — bot searches each company&apos;s jobs for your keywords)</span>
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="e.g. Google, Stripe, Notion…"
                value={favCompanyInput}
                onChange={(e) => setFavCompanyInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    const name = favCompanyInput.trim();
                    if (name && !favCompanies.includes(name) && favCompanies.length < 5) {
                      setFavCompanies([...favCompanies, name]);
                      setFavCompanyInput("");
                    }
                  }
                }}
                className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500"
                disabled={favCompanies.length >= 5}
              />
              <button
                type="button"
                onClick={() => {
                  const name = favCompanyInput.trim();
                  if (name && !favCompanies.includes(name) && favCompanies.length < 5) {
                    setFavCompanies([...favCompanies, name]);
                    setFavCompanyInput("");
                  }
                }}
                disabled={favCompanies.length >= 5 || !favCompanyInput.trim()}
                className="bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-sm font-bold px-3 py-2 rounded-lg transition-colors"
              >
                + Add
              </button>
            </div>
            {favCompanies.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-1">
                {favCompanies.map((c) => (
                  <span key={c} className="flex items-center gap-1 bg-amber-500/20 border border-amber-400/40 text-amber-300 text-xs font-mono px-2 py-1 rounded-full">
                    🏢 {c}
                    <button
                      type="button"
                      onClick={() => setFavCompanies(favCompanies.filter((x) => x !== c))}
                      className="ml-1 text-amber-400 hover:text-red-400 font-bold leading-none"
                      aria-label={`Remove ${c}`}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Platform tabs */}
          <div className="flex gap-2">
            {(["linkedin", "naukri"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPlatform(p)}
                className={`px-4 py-1.5 rounded-lg font-mono text-sm font-semibold transition-colors ${
                  platform === p
                    ? "bg-blue-500 text-white"
                    : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                }`}
              >
                {p === "linkedin" ? "🔵 LinkedIn" : "🟠 Naukri"}
              </button>
            ))}
          </div>

          {/* Platform login credentials (optional) */}
          <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
            <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
              {platform === "linkedin" ? "🔵 LinkedIn" : "🟠 Naukri"} Login
              <span className="ml-1 normal-case font-normal">
                {semiAuto
                  ? <span className="text-slate-600">(optional for semi-auto — you can type in the browser)</span>
                  : <span className="text-amber-400">*required for auto mode</span>
                }
              </span>
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Email / Username</label>
                <input
                  type="email"
                  placeholder="your@email.com"
                  value={linkedinEmail}
                  onChange={(e) => setLinkedinEmail(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">
                  Password
                  <span className="ml-1 text-slate-600">(leave blank → type in browser)</span>
                </label>
                <div className="flex gap-1">
                  <input
                    type={showLinkedinPwd ? "text" : "password"}
                    placeholder="••••••••"
                    value={linkedinPassword}
                    onChange={(e) => setLinkedinPassword(e.target.value)}
                    className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  />
                  <button type="button" onClick={() => setShowLinkedinPwd(!showLinkedinPwd)}
                    className="px-2 text-slate-500 hover:text-white text-sm">{showLinkedinPwd ? "🙈" : "👁"}</button>
                </div>
              </div>
            </div>
            {/* li_at cookie — required for cloud (Railway) runs */}
            <div className="mt-2">
              <label className="block font-mono text-xs text-slate-500 mb-1">
                Session Cookie (li_at)
                <span className="ml-1 text-blue-400 font-semibold">recommended for Cloud runs</span>
              </label>
              <div className="flex gap-1">
                <input
                  type={showLinkedinCookie ? "text" : "password"}
                  placeholder="AQE..."
                  value={linkedinCookie}
                  onChange={(e) => setLinkedinCookie(e.target.value)}
                  className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 font-mono"
                />
                <button type="button" onClick={() => setShowLinkedinCookie(!showLinkedinCookie)}
                  className="px-2 text-slate-500 hover:text-white text-sm">{showLinkedinCookie ? "🙈" : "👁"}</button>
              </div>
              <p className="font-mono text-xs text-slate-600 mt-1">
                Get it from browser DevTools → Application → Cookies → linkedin.com → <span className="text-slate-400">li_at</span>. Bypasses bot-detection on cloud IPs.
              </p>
            </div>
          </div>

          {/* Naukri — Apply Type */}
          {platform === "naukri" && (
            <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
                🟠 Naukri — Apply Type
              </p>
              <div className="flex flex-wrap gap-2 mt-1">
                {(
                  [
                    { value: "both", label: "🔀 Both" },
                    { value: "direct_only", label: "⚡ Direct Apply Only" },
                    { value: "company_site_only", label: "🌐 Company Site Only" },
                  ] as const
                ).map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setNaukriApplyTypes(value)}
                    className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-colors ${
                      naukriApplyTypes === value
                        ? "bg-orange-500 text-white"
                        : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="font-mono text-xs text-slate-600 mt-1">
                {naukriApplyTypes === "both"
                  ? "Apply using Naukri's Easy Apply AND company site forms."
                  : naukriApplyTypes === "direct_only"
                  ? "Only apply via Easy Apply (Naukri's built-in form). Skip jobs that redirect to company site."
                  : "Only apply on the company's own site. Skip Naukri Easy Apply jobs."}
              </p>
            </div>
          )}

          {/* Naukri — Search Filters */}
          {platform === "naukri" && (
            <div className="space-y-3 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
                🟠 Naukri — Search Filters
              </p>

              {/* Date posted */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Date Posted</label>
                <div className="flex flex-wrap gap-2">
                  {([
                    { value: "any", label: "Any time" },
                    { value: "1",   label: "Today" },
                    { value: "3",   label: "Last 3 days" },
                    { value: "7",   label: "Last week" },
                    { value: "15",  label: "Last 2 weeks" },
                    { value: "30",  label: "Last month" },
                  ] as const).map(({ value, label }) => (
                    <button key={value} type="button" onClick={() => setNaukriDatePosted(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        naukriDatePosted === value ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}>{label}</button>
                  ))}
                </div>
              </div>

              {/* Job type */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Job Type</label>
                <div className="flex flex-wrap gap-2">
                  {([
                    { value: "all",       label: "All" },
                    { value: "fullTime",  label: "Permanent" },
                    { value: "contract",  label: "Contract" },
                    { value: "temporary", label: "Temporary" },
                  ] as const).map(({ value, label }) => (
                    <button key={value} type="button" onClick={() => setNaukriJobType(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        naukriJobType === value ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}>{label}</button>
                  ))}
                </div>
              </div>

              {/* Work mode */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Work Mode</label>
                <div className="flex flex-wrap gap-2">
                  {([
                    { value: "any",    label: "Any" },
                    { value: "remote", label: "🌐 Remote / WFH" },
                    { value: "hybrid", label: "🔀 Hybrid" },
                    { value: "office", label: "🏢 Office" },
                  ] as const).map(({ value, label }) => (
                    <button key={value} type="button" onClick={() => setNaukriWorkMode(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        naukriWorkMode === value ? "bg-orange-500 text-white" : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}>{label}</button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* LinkedIn — Apply Type */}
          {platform === "linkedin" && (
            <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
                🔵 LinkedIn — Apply Type
              </p>
              <div className="flex flex-wrap gap-2 mt-1">
                {(
                  [
                    { value: "easy_apply_only", label: "⚡ Easy Apply Only" },
                    { value: "external_only",   label: "🌐 External Apply Only" },
                    { value: "both",            label: "🔀 Both" },
                  ] as const
                ).map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setLinkedinApplyTypes(value)}
                    className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-colors ${
                      linkedinApplyTypes === value
                        ? "bg-blue-600 text-white"
                        : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="font-mono text-xs text-slate-600 mt-1">
                {linkedinApplyTypes === "easy_apply_only"
                  ? "Only apply to jobs with LinkedIn Easy Apply. Skip jobs requiring external forms."
                  : linkedinApplyTypes === "external_only"
                  ? "Only apply to external company portals (AI fills forms). Skip Easy Apply jobs."
                  : "Apply to both Easy Apply and external company portal jobs."}
              </p>
            </div>
          )}

          {/* LinkedIn — Search Filters */}
          {platform === "linkedin" && (
            <div className="space-y-3 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
              <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
                🔵 LinkedIn — Search Filters
              </p>

              {/* Date posted */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Date Posted</label>
                <div className="flex flex-wrap gap-2">
                  {(
                    [
                      { value: "any", label: "Any time" },
                      { value: "past24h", label: "Past 24h" },
                      { value: "pastWeek", label: "Past week" },
                      { value: "pastMonth", label: "Past month" },
                    ] as const
                  ).map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setLinkedinDatePosted(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        linkedinDatePosted === value
                          ? "bg-blue-500 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Job type */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Job Type</label>
                <div className="flex flex-wrap gap-2">
                  {(
                    [
                      { value: "all", label: "All" },
                      { value: "fullTime", label: "Full-time" },
                      { value: "partTime", label: "Part-time" },
                      { value: "contract", label: "Contract" },
                      { value: "internship", label: "Internship" },
                    ] as const
                  ).map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setLinkedinJobType(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        linkedinJobType === value
                          ? "bg-blue-500 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Experience level */}
              <div>
                <label className="block font-mono text-xs text-slate-500 mb-1">Experience Level</label>
                <div className="flex flex-wrap gap-2">
                  {(
                    [
                      { value: "all", label: "All" },
                      { value: "internship", label: "Internship" },
                      { value: "entry", label: "Entry" },
                      { value: "associate", label: "Associate" },
                      { value: "mid", label: "Mid-Senior" },
                      { value: "director", label: "Director" },
                    ] as const
                  ).map(({ value, label }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setLinkedinExpLevel(value)}
                      className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold transition-colors ${
                        linkedinExpLevel === value
                          ? "bg-blue-500 text-white"
                          : "bg-slate-800 text-slate-400 hover:text-white border border-slate-700"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Remote toggle — synced with the Location widget above */}
              <div className="flex items-center gap-3">
                <input
                  id="linkedin-remote-toggle"
                  type="checkbox"
                  checked={remoteEnabled}
                  onChange={(e) => setRemoteEnabled(e.target.checked)}
                  className="accent-blue-500 w-4 h-4 cursor-pointer"
                />
                <label htmlFor="linkedin-remote-toggle" className="cursor-pointer font-mono text-xs text-slate-300">
                  Remote jobs only <span className="text-slate-600">(also updates the 📍 Location widget)</span>
                </label>
              </div>
            </div>
          )}

          {/* Smart Match — AI resume vs JD scoring gate */}
          <div className="space-y-3 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
            <div className="flex items-start gap-3">
              <input
                id="smart-match-toggle"
                type="checkbox"
                checked={smartMatch}
                onChange={(e) => setSmartMatch(e.target.checked)}
                className="mt-0.5 accent-violet-400 w-4 h-4 cursor-pointer"
              />
              <label htmlFor="smart-match-toggle" className="cursor-pointer">
                <p className="font-body font-semibold text-white text-sm">
                  🧠 Smart Match{" "}
                  {smartMatch && (
                    <span className="ml-1 text-xs bg-violet-400/15 text-violet-400 px-2 py-0.5 rounded">ON</span>
                  )}
                </p>
                <p className="font-body text-xs text-slate-400 mt-0.5">
                  Claude AI reads your resume and the job description before every application. Jobs scoring below the
                  threshold are skipped automatically — saving quota and improving your hit rate.
                </p>
              </label>
            </div>

            {smartMatch && (
              <div className="pl-7 space-y-2">
                <div className="flex items-center justify-between">
                  <label className="font-mono text-xs text-slate-400">
                    Min match score to apply
                  </label>
                  <span className="font-mono text-sm font-bold text-violet-400">{matchThreshold}%</span>
                </div>
                <input
                  type="range"
                  min={30}
                  max={95}
                  step={5}
                  value={matchThreshold}
                  onChange={(e) => setMatchThreshold(Number(e.target.value))}
                  className="w-full accent-violet-500"
                />
                <div className="flex justify-between font-mono text-xs text-slate-600">
                  <span>30% — Apply to almost all</span>
                  <span>95% — Very selective</span>
                </div>
              </div>
            )}
          </div>

          {/* Auto Cover Letter */}
          <div className="flex items-start gap-3 p-3 rounded-lg border border-slate-700 bg-slate-800/50">
            <input
              id="auto-cover-letter-toggle"
              type="checkbox"
              checked={autoCoverLetter}
              onChange={(e) => setAutoCoverLetter(e.target.checked)}
              className="mt-0.5 accent-violet-500 w-4 h-4 cursor-pointer"
            />
            <label htmlFor="auto-cover-letter-toggle" className="cursor-pointer">
              <p className="font-body font-semibold text-white text-sm">
                Auto Cover Letter {autoCoverLetter && <span className="ml-1 text-xs bg-violet-500/15 text-violet-400 px-2 py-0.5 rounded">ON</span>}
              </p>
              <p className="font-body text-xs text-slate-400 mt-0.5">
                Claude AI writes a personalised cover letter / intro message for every application using your resume and the job description.
                Disable to skip AI generation and send a plain default note.
              </p>
            </label>
          </div>

          {/* Smart Apply Scheduler */}
          <div className="p-3 rounded-lg border border-slate-700 bg-slate-800/50 space-y-3">
            <div className="flex items-start gap-3">
              <input
                id="schedule-toggle"
                type="checkbox"
                checked={scheduleEnabled}
                onChange={(e) => setScheduleEnabled(e.target.checked)}
                className="mt-0.5 accent-cyan-400 w-4 h-4 cursor-pointer"
              />
              <label htmlFor="schedule-toggle" className="cursor-pointer">
                <p className="font-body font-semibold text-white text-sm">
                  Smart Apply Scheduler {scheduleEnabled && <span className="ml-1 text-xs bg-cyan-400/15 text-cyan-400 px-2 py-0.5 rounded">ON</span>}
                </p>
                <p className="font-body text-xs text-slate-400 mt-0.5">
                  Restrict the bot to apply only within a specific time window. Applications sent during business hours look more human.
                </p>
              </label>
            </div>
            {scheduleEnabled && (
              <div className="pl-7 flex gap-4 items-center">
                <div className="flex flex-col gap-1">
                  <label className="font-mono text-xs text-slate-400">Start hour (24h)</label>
                  <select
                    value={scheduleStartHour}
                    onChange={(e) => setScheduleStartHour(Number(e.target.value))}
                    className="bg-slate-700 border border-slate-600 text-white font-mono text-sm rounded px-2 py-1"
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
                    ))}
                  </select>
                </div>
                <span className="font-mono text-slate-400 mt-4">→</span>
                <div className="flex flex-col gap-1">
                  <label className="font-mono text-xs text-slate-400">End hour (24h)</label>
                  <select
                    value={scheduleEndHour}
                    onChange={(e) => setScheduleEndHour(Number(e.target.value))}
                    className="bg-slate-700 border border-slate-600 text-white font-mono text-sm rounded px-2 py-1"
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
                    ))}
                  </select>
                </div>
                <p className="font-mono text-xs text-slate-500 mt-4 ml-2">
                  {scheduleStartHour <= scheduleEndHour
                    ? `Applies ${String(scheduleStartHour).padStart(2,"0")}:00–${String(scheduleEndHour).padStart(2,"0")}:00`
                    : `Overnight: ${String(scheduleStartHour).padStart(2,"0")}:00–${String(scheduleEndHour).padStart(2,"0")}:00`}
                </p>
              </div>
            )}
          </div>

          {/* Mode toggle */}
          <div className="flex items-start gap-3 p-3 rounded-lg border border-slate-700 bg-slate-800/50">
            <input
              id="semi-auto-toggle"
              type="checkbox"
              checked={semiAuto}
              onChange={(e) => setSemiAuto(e.target.checked)}
              className="mt-0.5 accent-amber-400 w-4 h-4 cursor-pointer"
            />
            <label htmlFor="semi-auto-toggle" className="cursor-pointer">
              <p className="font-body font-semibold text-white text-sm">
                Semi-Auto Mode {semiAuto && <span className="ml-1 text-xs bg-amber-400/15 text-amber-400 px-2 py-0.5 rounded">ON</span>}
              </p>
              <p className="font-body text-xs text-slate-400 mt-0.5">
                {semiAuto
                  ? "Bot fills all fields and clicks Next automatically. It stops at the final Submit — you review and click it yourself."
                  : "Bot fills all fields, clicks Next, and submits every application automatically."}
              </p>
            </label>
          </div>

          {/* Job History Reset */}
          <div className="space-y-2 p-3 rounded-lg border border-slate-700 bg-slate-800/30">
            <p className="font-mono text-xs text-slate-400 uppercase tracking-widest">
              🗂️ Job History
            </p>
            <p className="font-body text-xs text-slate-500">
              The bot tracks every job URL it has already applied to or skipped (last 30 days) and skips them automatically on future runs.
              Reset to let the bot re-try those jobs.
            </p>
            <div className="flex flex-wrap gap-2 mt-1">
              <button
                type="button"
                disabled={resetHistoryLoading}
                onClick={() => resetJobHistory(platform)}
                className="disabled:opacity-50 px-3 py-1.5 rounded-lg font-mono text-xs font-semibold bg-rose-600/20 text-rose-400 border border-rose-600/40 hover:bg-rose-600/30 transition-colors"
              >
                {resetHistoryLoading ? "Resetting…" : `🔄 Reset ${platform === "naukri" ? "Naukri" : "LinkedIn"} History`}
              </button>
              <button
                type="button"
                disabled={resetHistoryLoading}
                onClick={() => resetJobHistory()}
                className="disabled:opacity-50 px-3 py-1.5 rounded-lg font-mono text-xs font-semibold bg-rose-600/10 text-rose-500 border border-rose-700/40 hover:bg-rose-600/20 transition-colors"
              >
                {resetHistoryLoading ? "Resetting…" : "🔄 Reset All Platforms"}
              </button>
              <button
                type="button"
                disabled={resetSmartMatchLoading}
                onClick={resetSmartMatchHistory}
                className="disabled:opacity-50 px-3 py-1.5 rounded-lg font-mono text-xs font-semibold bg-violet-600/20 text-violet-400 border border-violet-600/40 hover:bg-violet-600/30 transition-colors"
              >
                {resetSmartMatchLoading ? "Clearing…" : "🧠 Clear Smart Match Skips"}
              </button>
            </div>
            <p className="font-body text-xs text-slate-600">
              🧠 Smart Match Skips are tied to your current resume — uploading a new resume clears them automatically.
              Use the button above to force a re-evaluation without changing your resume.
            </p>
          </div>
          {/* AI Keyword Suggester */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-slate-500">Need ideas? Let AI suggest keywords from your resume.</span>
              <button
                type="button"
                disabled={suggestingKeywords}
                onClick={suggestKeywordsFromResume}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-mono text-xs font-semibold bg-violet-600/20 text-violet-300 border border-violet-600/40 hover:bg-violet-600/30 transition-colors disabled:opacity-50"
              >
                {suggestingKeywords ? "Generating…" : "✨ AI Suggest Keywords"}
              </button>
            </div>
            {suggestedKeywords.length > 0 && (
              <div className="p-3 rounded-lg border border-violet-500/20 bg-violet-500/5 space-y-2">
                <p className="font-mono text-xs text-slate-400">Click a keyword to use it:</p>
                <div className="flex flex-wrap gap-2">
                  {suggestedKeywords.map((kw, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => {
                        if (!keywords.trim()) { setKeywords(kw); }
                        else if (!keywords2.trim()) { setKeywords2(kw); }
                        else if (!keywords3.trim()) { setKeywords3(kw); }
                        setSuggestedKeywords(prev => prev.filter((_, idx) => idx !== i));
                      }}
                      className="px-2 py-1 rounded-md text-xs font-mono bg-slate-700 text-slate-300 hover:bg-violet-700 hover:text-white border border-slate-600 hover:border-violet-500 transition-colors"
                    >
                      {kw}
                    </button>
                  ))}
                </div>
                <p className="font-mono text-xs text-slate-600">Fills Keyword 1 → 2 → 3 in order. Max 3 slots.</p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Keyword 1 <span className="text-red-400">*</span></label>
              <input
                type="text"
                placeholder="e.g. Software Engineer"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Keyword 2 <span className="text-slate-500">(optional — runs after Keyword 1)</span></label>
              <input
                type="text"
                placeholder="e.g. Backend Developer"
                value={keywords2}
                onChange={(e) => setKeywords2(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Keyword 3 <span className="text-slate-500">(optional — runs after Keyword 2)</span></label>
              <input
                type="text"
                placeholder="e.g. Full Stack Engineer"
                value={keywords3}
                onChange={(e) => setKeywords3(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            {/* Location widget — full width ─────────────────── */}
            <div className="sm:col-span-2 space-y-2">
              <label className="block font-mono text-xs text-slate-400">📍 Location <span className="text-slate-500 font-normal">(optional — up to 5, bot searches each)</span></label>
              {/* Remote checkbox */}
              <div className="flex items-center gap-2">
                <input
                  id="remote-loc-toggle"
                  type="checkbox"
                  checked={remoteEnabled}
                  onChange={(e) => setRemoteEnabled(e.target.checked)}
                  className="accent-emerald-400 w-4 h-4 cursor-pointer"
                />
                <label htmlFor="remote-loc-toggle" className="cursor-pointer font-mono text-sm text-slate-300">
                  🌐 Remote
                </label>
              </div>
              {/* Tag input */}
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder={locationList.length >= 5 ? "Max 5 locations" : "e.g. Bangalore (press Enter to add)"}
                  value={locationInput}
                  onChange={(e) => setLocationInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      const loc = locationInput.trim();
                      if (loc && !locationList.includes(loc) && locationList.length < 5) {
                        setLocationList([...locationList, loc]);
                        setLocationInput("");
                      }
                    }
                  }}
                  disabled={locationList.length >= 5}
                  className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => {
                    const loc = locationInput.trim();
                    if (loc && !locationList.includes(loc) && locationList.length < 5) {
                      setLocationList([...locationList, loc]);
                      setLocationInput("");
                    }
                  }}
                  disabled={locationList.length >= 5 || !locationInput.trim()}
                  className="bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-sm font-bold px-3 py-2 rounded-lg transition-colors"
                >
                  + Add
                </button>
              </div>
              {locationList.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {locationList.map((loc) => (
                    <span key={loc} className="flex items-center gap-1 bg-blue-500/20 border border-blue-400/40 text-blue-300 text-xs font-mono px-2 py-1 rounded-full">
                      📍 {loc}
                      <button
                        type="button"
                        onClick={() => setLocationList(locationList.filter((l) => l !== loc))}
                        className="ml-1 text-blue-400 hover:text-red-400 font-bold leading-none"
                      >✕</button>
                    </span>
                  ))}
                </div>
              )}
              {!remoteEnabled && locationList.length === 0 && (
                <p className="font-mono text-xs text-slate-600">No location set — bot will search everywhere</p>
              )}
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Phone Country</label>
              <select
                value={phoneCountry}
                onChange={(e) => {
                  setPhoneCountry(e.target.value);
                  const isoMap: Record<string, string> = {
                    "India (+91)": "in",
                    "United States (+1)": "us",
                    "United Kingdom (+44)": "gb",
                    "Canada (+1)": "ca",
                    "Australia (+61)": "au",
                    "Germany (+49)": "de",
                    "Singapore (+65)": "sg",
                  };
                  setPhoneCountryCode(isoMap[e.target.value] || "us");
                }}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              >
                <option value="India (+91)">India (+91)</option>
                <option value="United States (+1)">United States (+1)</option>
                <option value="United Kingdom (+44)">United Kingdom (+44)</option>
                <option value="Canada (+1)">Canada (+1)</option>
                <option value="Australia (+61)">Australia (+61)</option>
                <option value="Germany (+49)">Germany (+49)</option>
                <option value="Singapore (+65)">Singapore (+65)</option>
              </select>
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Phone Number <span className="text-red-400">*</span></label>
              <input
                type="tel"
                placeholder="e.g. 9876543210"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Years of Experience</label>
              <input
                type="number" min="0" max="30" placeholder="e.g. 2"
                value={yearsExp}
                onChange={(e) => setYearsExp(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Skill Rating (0–10)</label>
              <input
                type="number" min="0" max="10" placeholder="e.g. 8"
                value={skillRating}
                onChange={(e) => setSkillRating(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">
                Max Applications
                <span className="ml-1 text-slate-500 font-normal">(max 10 per run — testing mode)</span>
              </label>
              <input
                type="number" min="1" max="10" placeholder="e.g. 5"
                value={maxApply}
                onChange={(e) => {
                  const value = e.target.value;
                  if (value === "") { setMaxApply(""); return; }
                  setMaxApply(String(Math.max(1, Math.min(10, Number(value)))));
                }}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Notice Period (days)</label>
              <input
                type="number" min="0" placeholder="e.g. 30"
                value={noticePeriod}
                onChange={(e) => setNoticePeriod(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Current CTC (optional)</label>
              <input
                type="number" min="0" placeholder="e.g. 600000"
                value={currentCtc}
                onChange={(e) => setCurrentCtc(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Expected Salary (optional)</label>
              <input
                type="number" min="0" placeholder="e.g. 800000"
                value={salaryExpectation}
                onChange={(e) => setSalaryExpectation(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {/* Profile fields for AI form filling */}
          <div className="mt-3 pt-3 border-t border-slate-700/50">
            <div className="flex items-center justify-between mb-3">
              <p className="font-mono text-xs text-slate-500 uppercase tracking-widest">
                Profile (used by AI to fill application forms)
              </p>
              <button
                onClick={() => saveProfile()}
                disabled={profileSaving}
                className="text-xs bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-3 py-1 rounded-lg transition-colors"
              >
                {profileSaving ? "Saving…" : "💾 Save Profile"}
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block font-mono text-xs text-slate-400 mb-1">First Name</label>
                <input
                  type="text" placeholder="e.g. Anand"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block font-mono text-xs text-slate-400 mb-1">Last Name</label>
                <input
                  type="text" placeholder="e.g. Kumar"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block font-mono text-xs text-slate-400 mb-1">Current City</label>
                <input
                  type="text" placeholder="e.g. Chennai"
                  value={currentCity}
                  onChange={(e) => setCurrentCity(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block font-mono text-xs text-slate-400 mb-1">Highest Education</label>
                <select
                  value={highestEducation}
                  onChange={(e) => setHighestEducation(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                >
                  <option value="">Select</option>
                  <option value="High School">High School</option>
                  <option value="Diploma">Diploma</option>
                  <option value="Bachelor's Degree">Bachelor&apos;s Degree</option>
                  <option value="Master's Degree">Master&apos;s Degree</option>
                  <option value="Doctorate">Doctorate</option>
                </select>
              </div>
              <div>
                <label className="block font-mono text-xs text-slate-400 mb-1">LinkedIn URL</label>
                <input
                  type="url" placeholder="https://linkedin.com/in/yourprofile"
                  value={linkedinUrl}
                  onChange={(e) => setLinkedinUrl(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block font-mono text-xs text-slate-400 mb-1">GitHub URL</label>
                <input
                  type="url" placeholder="https://github.com/yourusername"
                  value={githubUrl}
                  onChange={(e) => setGithubUrl(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block font-mono text-xs text-slate-400 mb-1">Portfolio / Website URL</label>
                <input
                  type="url" placeholder="https://yourportfolio.com"
                  value={portfolioUrl}
                  onChange={(e) => setPortfolioUrl(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            {/* ── EEO / Diversity & Work Authorization ──────────── */}
            <details className="mt-4 group">
              <summary className="cursor-pointer font-mono text-xs text-blue-400 uppercase tracking-widest select-none hover:text-blue-300 transition-colors">
                🪪 EEO / Diversity & Work Authorization — <span className="text-slate-500 normal-case">optional, used to answer compliance questions</span>
              </summary>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Work Authorization / Visa Status</label>
                  <select
                    value={workAuthorization}
                    onChange={(e) => setWorkAuthorization(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  >
                    <option value="">Select</option>
                    <option value="Citizen">Citizen</option>
                    <option value="Permanent Resident / Green Card">Permanent Resident / Green Card</option>
                    <option value="EAD (Employment Authorization Document)">EAD (Employment Authorization Document)</option>
                    <option value="H1B Visa">H1B Visa</option>
                    <option value="H4 EAD">H4 EAD</option>
                    <option value="OPT (F1 Student Visa)">OPT (F1 Student Visa)</option>
                    <option value="L1 / L2 Visa">L1 / L2 Visa</option>
                    <option value="TN Visa">TN Visa</option>
                    <option value="Other Work Visa">Other Work Visa</option>
                    <option value="Not Applicable">Not Applicable</option>
                  </select>
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Nationality</label>
                  <input
                    type="text" placeholder="e.g. Indian, American"
                    value={nationality}
                    onChange={(e) => setNationality(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Country of Origin</label>
                  <input
                    type="text" placeholder="e.g. India, USA"
                    value={countryOfOrigin}
                    onChange={(e) => setCountryOfOrigin(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Gender <span className="text-slate-600 font-normal">(used for EEO forms)</span></label>
                  <select
                    value={gender}
                    onChange={(e) => setGender(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  >
                    <option value="">Select</option>
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                    <option value="Non-binary">Non-binary</option>
                    <option value="Other">Other</option>
                    <option value="Prefer not to say">Prefer not to say</option>
                  </select>
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Disability Status <span className="text-slate-600 font-normal">(EEO forms)</span></label>
                  <select
                    value={disabilityStatus}
                    onChange={(e) => setDisabilityStatus(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  >
                    <option value="">Select</option>
                    <option value="I don't have a disability">I don&apos;t have a disability</option>
                    <option value="I have a disability">I have a disability</option>
                    <option value="Prefer not to disclose">Prefer not to disclose</option>
                  </select>
                </div>
                <div>
                  <label className="block font-mono text-xs text-slate-400 mb-1">Veteran Status <span className="text-slate-600 font-normal">(EEO forms)</span></label>
                  <select
                    value={veteranStatus}
                    onChange={(e) => setVeteranStatus(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  >
                    <option value="">Select</option>
                    <option value="I am not a veteran">I am not a veteran</option>
                    <option value="I am a veteran">I am a veteran</option>
                    <option value="I am a disabled veteran">I am a disabled veteran</option>
                    <option value="Prefer not to disclose">Prefer not to disclose</option>
                  </select>
                </div>
                <div className="md:col-span-2">
                  <label className="block font-mono text-xs text-slate-400 mb-1">Race / Ethnicity <span className="text-slate-600 font-normal">(EEO forms)</span></label>
                  <input
                    type="text" placeholder="e.g. Asian, Hispanic/Latino, White/Caucasian, Prefer not to disclose"
                    value={ethnicity}
                    onChange={(e) => setEthnicity(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                  />
                </div>
              </div>
            </details>

            {/* ── Employment History ──────────────────────────────── */}
            <details className="mt-4 group">
              <summary className="cursor-pointer font-mono text-xs text-blue-400 uppercase tracking-widest select-none hover:text-blue-300 transition-colors">
                💼 Employment History ({employments.length}) — <span className="text-slate-500 normal-case">optional, helps AI fill work experience forms</span>
              </summary>
              <div className="mt-3 space-y-3">
                {employments.map((emp, idx) => (
                  <div key={idx} className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-3 relative">
                    <button
                      onClick={() => setEmployments(prev => prev.filter((_, i) => i !== idx))}
                      className="absolute top-2 right-2 text-slate-500 hover:text-red-400 text-xs"
                      title="Remove"
                    >✕</button>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Company</label>
                        <input type="text" placeholder="e.g. Google" value={emp.company}
                          onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, company: e.target.value } : em))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Position / Title</label>
                        <input type="text" placeholder="e.g. Software Engineer" value={emp.position}
                          onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, position: e.target.value } : em))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">City</label>
                        <input type="text" placeholder="e.g. Bangalore" value={emp.city}
                          onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, city: e.target.value } : em))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500 cursor-pointer">
                          <input type="checkbox" checked={emp.is_current}
                            onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, is_current: e.target.checked } : em))}
                            className="rounded border-slate-600" />
                          Currently working here
                        </label>
                      </div>
                      <div className="flex gap-2">
                        <div className="flex-1">
                          <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Start Month</label>
                          <select value={emp.start_month}
                            onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, start_month: e.target.value } : em))}
                            className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500">
                            <option value="">Month</option>
                            {MONTHS.slice(1).map((m, mi) => <option key={mi} value={String(mi + 1)}>{m}</option>)}
                          </select>
                        </div>
                        <div className="flex-1">
                          <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Start Year</label>
                          <select value={emp.start_year}
                            onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, start_year: e.target.value } : em))}
                            className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500">
                            <option value="">Year</option>
                            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                          </select>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <div className="flex-1">
                          <label className="block font-mono text-[10px] text-slate-500 mb-0.5">End Month</label>
                          <select value={emp.end_month} disabled={emp.is_current}
                            onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, end_month: e.target.value } : em))}
                            className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500 disabled:opacity-40">
                            <option value="">{emp.is_current ? "Present" : "Month"}</option>
                            {MONTHS.slice(1).map((m, mi) => <option key={mi} value={String(mi + 1)}>{m}</option>)}
                          </select>
                        </div>
                        <div className="flex-1">
                          <label className="block font-mono text-[10px] text-slate-500 mb-0.5">End Year</label>
                          <select value={emp.end_year} disabled={emp.is_current}
                            onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, end_year: e.target.value } : em))}
                            className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500 disabled:opacity-40">
                            <option value="">{emp.is_current ? "Present" : "Year"}</option>
                            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                          </select>
                        </div>
                      </div>
                      <div className="md:col-span-2">
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Description (optional)</label>
                        <textarea rows={2} placeholder="Key responsibilities or achievements…" value={emp.description}
                          onChange={e => setEmployments(prev => prev.map((em, i) => i === idx ? { ...em, description: e.target.value } : em))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500 resize-none" />
                      </div>
                    </div>
                  </div>
                ))}
                <button
                  onClick={() => setEmployments(prev => [...prev, { ...EMPTY_EMPLOYMENT }])}
                  className="text-xs text-blue-400 hover:text-blue-300 font-mono"
                >+ Add Employment</button>
              </div>
            </details>

            {/* ── Education Details ───────────────────────────────── */}
            <details className="mt-4 group">
              <summary className="cursor-pointer font-mono text-xs text-blue-400 uppercase tracking-widest select-none hover:text-blue-300 transition-colors">
                🎓 Education ({educations.length}) — <span className="text-slate-500 normal-case">optional, helps AI fill education forms</span>
              </summary>
              <div className="mt-3 space-y-3">
                {educations.map((edu, idx) => (
                  <div key={idx} className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-3 relative">
                    <button
                      onClick={() => setEducations(prev => prev.filter((_, i) => i !== idx))}
                      className="absolute top-2 right-2 text-slate-500 hover:text-red-400 text-xs"
                      title="Remove"
                    >✕</button>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">School / University</label>
                        <input type="text" placeholder="e.g. Anna University" value={edu.school}
                          onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, school: e.target.value } : ed))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">City</label>
                        <input type="text" placeholder="e.g. Chennai" value={edu.city}
                          onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, city: e.target.value } : ed))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Degree</label>
                        <select value={edu.degree}
                          onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, degree: e.target.value } : ed))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500">
                          <option value="">Select Degree</option>
                          <option value="High School">High School</option>
                          <option value="Diploma">Diploma</option>
                          <option value="Associate's Degree">Associate&apos;s Degree</option>
                          <option value="Bachelor's Degree">Bachelor&apos;s Degree</option>
                          <option value="Master's Degree">Master&apos;s Degree</option>
                          <option value="Doctorate">Doctorate</option>
                          <option value="B.Tech">B.Tech</option>
                          <option value="B.E">B.E</option>
                          <option value="M.Tech">M.Tech</option>
                          <option value="MBA">MBA</option>
                          <option value="BCA">BCA</option>
                          <option value="MCA">MCA</option>
                          <option value="B.Sc">B.Sc</option>
                          <option value="M.Sc">M.Sc</option>
                        </select>
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Major / Field of Study</label>
                        <input type="text" placeholder="e.g. Computer Science" value={edu.major}
                          onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, major: e.target.value } : ed))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div className="flex gap-2">
                        <div className="flex-1">
                          <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Start Month</label>
                          <select value={edu.start_month}
                            onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, start_month: e.target.value } : ed))}
                            className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500">
                            <option value="">Month</option>
                            {MONTHS.slice(1).map((m, mi) => <option key={mi} value={String(mi + 1)}>{m}</option>)}
                          </select>
                        </div>
                        <div className="flex-1">
                          <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Start Year</label>
                          <select value={edu.start_year}
                            onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, start_year: e.target.value } : ed))}
                            className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500">
                            <option value="">Year</option>
                            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                          </select>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <div className="flex-1">
                          <label className="block font-mono text-[10px] text-slate-500 mb-0.5">End Month</label>
                          <select value={edu.end_month}
                            onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, end_month: e.target.value } : ed))}
                            className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500">
                            <option value="">Month</option>
                            {MONTHS.slice(1).map((m, mi) => <option key={mi} value={String(mi + 1)}>{m}</option>)}
                          </select>
                        </div>
                        <div className="flex-1">
                          <label className="block font-mono text-[10px] text-slate-500 mb-0.5">End Year</label>
                          <select value={edu.end_year}
                            onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, end_year: e.target.value } : ed))}
                            className="w-full bg-slate-900 border border-slate-700 text-white text-xs rounded px-2 py-1.5 focus:outline-none focus:border-blue-500">
                            <option value="">Year</option>
                            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
                          </select>
                        </div>
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">GPA / Percentage (optional)</label>
                        <input type="text" placeholder="e.g. 8.5 or 85%" value={edu.gpa}
                          onChange={e => setEducations(prev => prev.map((ed, i) => i === idx ? { ...ed, gpa: e.target.value } : ed))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                    </div>
                  </div>
                ))}
                <button
                  onClick={() => setEducations(prev => [...prev, { ...EMPTY_EDUCATION }])}
                  className="text-xs text-blue-400 hover:text-blue-300 font-mono"
                >+ Add Education</button>
              </div>
            </details>

            {/* ── Projects ───────────────────────────────────────── */}
            <details className="mt-4 group">
              <summary className="cursor-pointer font-mono text-xs text-blue-400 uppercase tracking-widest select-none hover:text-blue-300 transition-colors">
                🚀 Projects ({projects.length}) — <span className="text-slate-500 normal-case">optional, showcase your work</span>
              </summary>
              <div className="mt-3 space-y-3">
                {projects.map((proj, idx) => (
                  <div key={idx} className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-3 relative">
                    <button
                      onClick={() => setProjects(prev => prev.filter((_, i) => i !== idx))}
                      className="absolute top-2 right-2 text-slate-500 hover:text-red-400 text-xs"
                      title="Remove"
                    >✕</button>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Project Name</label>
                        <input type="text" placeholder="e.g. VantaHire" value={proj.name}
                          onChange={e => setProjects(prev => prev.map((p, i) => i === idx ? { ...p, name: e.target.value } : p))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">URL (optional)</label>
                        <input type="url" placeholder="https://github.com/..." value={proj.url}
                          onChange={e => setProjects(prev => prev.map((p, i) => i === idx ? { ...p, url: e.target.value } : p))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Technologies</label>
                        <input type="text" placeholder="e.g. React, Node.js, PostgreSQL" value={proj.technologies}
                          onChange={e => setProjects(prev => prev.map((p, i) => i === idx ? { ...p, technologies: e.target.value } : p))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                      <div>
                        <label className="block font-mono text-[10px] text-slate-500 mb-0.5">Description</label>
                        <input type="text" placeholder="Brief description…" value={proj.description}
                          onChange={e => setProjects(prev => prev.map((p, i) => i === idx ? { ...p, description: e.target.value } : p))}
                          className="w-full bg-slate-900 border border-slate-700 text-white text-sm rounded px-2 py-1.5 focus:outline-none focus:border-blue-500" />
                      </div>
                    </div>
                  </div>
                ))}
                <button
                  onClick={() => setProjects(prev => [...prev, { ...EMPTY_PROJECT }])}
                  className="text-xs text-blue-400 hover:text-blue-300 font-mono"
                >+ Add Project</button>
              </div>
            </details>
          </div>

          {/* ── Execution Mode Toggle + Apply ────────────────── */}
          <div className="flex flex-col gap-3 mt-2">
            {/* Mode toggle */}
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-slate-500">Run on:</span>
              <div className="flex rounded-lg border border-slate-700 overflow-hidden">
                <button
                  onClick={() => setExecMode("local")}
                  className={`px-3 py-1.5 text-xs font-semibold transition-colors ${
                    execMode === "local" ? "bg-blue-500 text-white" : "bg-slate-800 text-slate-400 hover:text-white"
                  }`}
                >💻 Local Machine</button>
                <button
                  onClick={() => {
                    if (!railwayConfigured) {
                      alert("Railway Cloud is not configured yet. Go to Agent page → Setup Guide to configure it.");
                      return;
                    }
                    setExecMode("cloud");
                  }}
                  className={`px-3 py-1.5 text-xs font-semibold transition-colors ${
                    execMode === "cloud" ? "bg-violet-500 text-white" : "bg-slate-800 text-slate-400 hover:text-white"
                  }`}
                >☁️ Cloud</button>
              </div>
              {execMode === "cloud" && (
                <span className="text-xs text-slate-500 font-mono">
                  {railwayQuota.remaining}/{railwayQuota.limit} min remaining today
                </span>
              )}
            </div>

            {/* Apply button */}
            <div className="flex justify-end">
              <button
                onClick={() => {
                  if (applyMode !== "url" && !phone.trim()) {
                    alert("Please enter your phone number first.");
                    return;
                  }
                  createTask();
                }}
                disabled={taskLoading || (execMode === "cloud" && railwayQuota.remaining <= 0)}
                className={`disabled:opacity-50 text-white font-bold px-5 py-2.5 rounded-lg transition-colors ${
                  execMode === "cloud"
                    ? "bg-violet-500 hover:bg-violet-400"
                    : applyMode === "url"
                    ? "bg-sky-500 hover:bg-sky-400"
                    : applyMode === "tailor"
                    ? "bg-amber-500 hover:bg-amber-400"
                    : semiAuto
                    ? "bg-amber-500 hover:bg-amber-400"
                    : "bg-blue-500 hover:bg-blue-400"
                }`}
              >
                {taskLoading
                  ? "Creating…"
                  : execMode === "cloud"
                  ? "☁️ Start on Cloud"
                  : applyMode === "url"
                  ? "🔗 Apply to These URLs"
                  : applyMode === "tailor"
                  ? "✨ Start Tailor & Apply"
                  : semiAuto
                  ? "🤝 Start Semi-Auto Apply"
                  : "🚀 Start Auto Apply"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Cloud Live Panel (Screenshot + Logs) ─────────────────── */}
      {railwayStatus !== "idle" && (
        <div className="mb-12 animate-fadeUp bg-slate-900/60 border border-violet-500/30 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
            <div className="flex items-center gap-3">
              {railwayStatus === "running" && <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />}
              <div>
                <p className="text-sm font-bold text-white">
                  {railwayStatus === "running" ? "☁️ Cloud Automation Running" : "☁️ Session Ended"}
                </p>
                {railwayCurrentJob && <p className="text-xs text-slate-400 mt-0.5 truncate max-w-64">{railwayCurrentJob}</p>}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {railwayStatus === "running" && (
                <div className="flex items-center gap-2">
                  <div className="w-24 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div className="h-full bg-violet-500 rounded-full transition-all" style={{ width: `${railwayProgress}%` }} />
                  </div>
                  <span className="text-xs text-slate-400">{railwayProgress}%</span>
                </div>
              )}
              <button
                onClick={() => setShowScreenshot(p => !p)}
                className="px-3 py-1.5 text-xs font-medium border border-slate-700 rounded-lg text-slate-400 hover:text-white hover:border-slate-500 transition-colors"
              >{showScreenshot ? "🖥 Hide Feed" : "🖥 Show Feed"}</button>
              {railwayStatus === "running" ? (
                <button onClick={stopRailwaySession} disabled={railwayStopping}
                  className="px-3 py-1.5 text-xs font-semibold bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20 rounded-lg transition-all disabled:opacity-50"
                >{railwayStopping ? "Stopping…" : "⏹ Stop"}</button>
              ) : (
                <button onClick={() => { stopCloudPoll(); setRailwayStatus("idle"); setRailwaySessionId(null); setRailwayTaskId(null); setLiveScreenshot(null); setRailwayLogs([]); }}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:text-white border border-slate-700 rounded-lg transition-colors"
                >Close</button>
              )}
            </div>
          </div>
          <div className={`grid gap-0 divide-y lg:divide-y-0 lg:divide-x divide-slate-800 ${showScreenshot ? "grid-cols-1 lg:grid-cols-2" : "grid-cols-1"}`}>
            {showScreenshot && (
              <div className="relative bg-slate-950 flex items-center justify-center" style={{ minHeight: "280px" }}>
                {liveScreenshot ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={liveScreenshot} alt="Live automation screenshot" className="w-full object-contain" />
                ) : (
                  <div className="flex flex-col items-center gap-3 text-slate-600 px-6 text-center">
                    <span className="text-2xl">🖥️</span>
                    <p className="text-xs text-slate-500 font-mono">Live screenshot preview is currently under testing</p>
                    <p className="text-[10px] text-slate-600">Your automation is running — check the activity log for real-time progress</p>
                  </div>
                )}
                {liveScreenshot && <div className="absolute bottom-2 right-2 bg-black/60 text-xs text-slate-400 px-2 py-0.5 rounded">Live</div>}
              </div>
            )}
            <div style={{ minHeight: "280px", maxHeight: "320px" }}>
              <LogPanel
                logs={railwayLogs.map((l) => ({
                  ts: l.ts ?? new Date().toISOString(),
                  level: (l.level ?? "info") as LogEntry["level"],
                  category: "system" as const,
                  msg: l.message,
                  meta: {},
                }))}
                isRunning={railwayStatus === "running"}
              />
            </div>
          </div>

          {/* ── Completion Report ───────────────────────────────── */}
          {railwayStatus === "done" && liveTask?.output && (
            <div className="p-4 border-t border-slate-800">
              <div className="flex items-center gap-3 mb-3">
                <span className="text-2xl">🎉</span>
                <div>
                  <p className="font-body font-semibold text-emerald-400">
                    Applied to {liveTask.output.applied_count ?? 0} jobs
                  </p>
                  <p className="font-body text-xs text-slate-400 mt-0.5">{liveTask.output.message}</p>
                </div>
              </div>
              {/* Report table from logs */}
              {railwayLogs.length > 0 && (() => {
                const report = railwayLogs
                  .filter((l) => l.level === "success" || l.level === "skip")
                  .map((l) => {
                    const meta = (l as { meta?: Record<string, unknown> }).meta ?? {};
                    return {
                      company: (meta.company as string) || "—",
                      position: (meta.job_title as string) || "—",
                      score: meta.score != null ? `${meta.score}%` : "—",
                      status: l.level === "success" ? "✅ Applied" : "⏭ Skipped",
                      reason: (meta.skip_reason as string) || "",
                    };
                  });
                if (report.length === 0) return null;
                return (
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-700 text-slate-500">
                          <th className="text-left py-2 px-2 font-mono">#</th>
                          <th className="text-left py-2 px-2 font-mono">Company</th>
                          <th className="text-left py-2 px-2 font-mono">Position</th>
                          <th className="text-left py-2 px-2 font-mono">Score</th>
                          <th className="text-left py-2 px-2 font-mono">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {report.map((r, i) => (
                          <tr key={i} className="border-b border-slate-800">
                            <td className="py-1.5 px-2 text-slate-600">{i + 1}</td>
                            <td className="py-1.5 px-2 text-slate-300">{r.company}</td>
                            <td className="py-1.5 px-2 text-slate-300">{r.position}</td>
                            <td className="py-1.5 px-2 text-slate-400">{r.score}</td>
                            <td className={`py-1.5 px-2 ${r.status.includes("Applied") ? "text-emerald-400" : "text-amber-400"}`}>
                              {r.status}{r.reason ? ` (${r.reason})` : ""}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}
            </div>
          )}
          <div ref={logsEndRef} />
        </div>
      )}
      {/* ── Gmail & Email Follow-Up Settings ─────────────────────── */}
      <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          📧 Email Follow-Up
        </h2>
        <div className="card space-y-4">
          <p className="font-body text-xs text-slate-400">
            The bot checks your Gmail daily for job-related replies (acknowledgment, interview, rejection) and sends AI-drafted follow-up emails. Uses Gmail App Password — no OAuth needed.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Gmail Address</label>
              <input
                type="email"
                placeholder="you@gmail.com"
                value={gmailAddress}
                onChange={(e) => setGmailAddress(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">
                App Password
                <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer"
                  className="ml-2 text-blue-400 hover:underline text-xs">(get one here ↗)</a>
              </label>
              <div className="flex gap-1">
                <input
                  type={showGmailPwd ? "text" : "password"}
                  placeholder="xxxx xxxx xxxx xxxx"
                  value={gmailAppPassword}
                  onChange={(e) => setGmailAppPassword(e.target.value)}
                  className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
                />
                <button type="button" onClick={() => setShowGmailPwd(!showGmailPwd)}
                  className="px-2 text-slate-500 hover:text-white text-sm">{showGmailPwd ? "🙈" : "👁"}</button>
              </div>
            </div>
            <div>
              <label className="block font-mono text-xs text-slate-400 mb-1">Follow-Up After (days)</label>
              <input
                type="number" min="1" max="30" placeholder="e.g. 3"
                value={followupDays}
                onChange={(e) => setFollowupDays(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
              />
              <p className="font-body text-xs text-slate-500 mt-1">Bot will send a follow-up email if no reply after this many days.</p>
            </div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={saveGmailSettings}
              disabled={gmailSaving}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold px-4 py-2 rounded-lg text-sm transition-colors"
            >
              {gmailSaving ? "Saving…" : "💾 Save Email Settings"}
            </button>
          </div>
        </div>
      </div>
      {/* ── Live Run Monitor ─────────────────────────────────── */}
      {liveTask && (
        <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
          <div className="flex items-center gap-3 mb-4">
            {liveTask.status === "RUNNING" && (
              <span className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-ping inline-block" />
            )}
            <h2 className="font-display font-semibold text-lg text-white">
              {liveTask.status === "RUNNING" ? "Run in Progress" : liveTask.status === "DONE" ? "Run Complete ✅" : "Run Failed ❌"}
            </h2>
            {liveTask.status === "RUNNING" && (
              <span className="ml-auto flex gap-2">
                <button
                  onClick={togglePause}
                  className={`font-mono text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                    liveTask.paused
                      ? "border-emerald-400 text-emerald-400 hover:bg-emerald-400/10"
                      : "border-amber-400 text-amber-400 hover:bg-amber-400/10"
                  }`}
                >
                  {liveTask.paused ? "▶ Resume" : "⏸ Pause"}
                </button>
                <button
                  onClick={requestStop}
                  className="font-mono text-xs px-3 py-1.5 rounded-lg border border-red-400 text-red-400 hover:bg-red-400/10 transition-colors"
                >
                  ⏹ Stop
                </button>
              </span>
            )}
          </div>

          <div className="card space-y-4">
            {/* Progress bar */}
            <div>
              <div className="flex justify-between mb-1">
                <span className="font-mono text-xs text-slate-400">
                  {liveTask.current_job
                    ? `Working on: ${liveTask.current_job.replace(/.*linkedin\.com\/jobs\/view\//, "job #")}`
                    : "Initialising…"}
                </span>
                <span className="font-mono text-xs text-slate-400">{liveTask.progress ?? 0}%</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-2">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-blue-500 to-amber-400 transition-all duration-500"
                  style={{ width: `${liveTask.progress ?? 0}%` }}
                />
              </div>
            </div>

            {/* Live prompt injection */}
            {liveTask.status === "RUNNING" && (
              <div className="p-3 rounded-lg border border-amber-400/20 bg-amber-400/5 space-y-2">
                <p className="font-mono text-xs text-amber-400 uppercase tracking-widest">
                  Inject custom instruction for next application
                </p>
                <p className="font-body text-xs text-slate-400">
                  Typed here, picked up by the bot before it starts the next job — no restart needed.
                </p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder='e.g. "Emphasise leadership and team management"'
                    value={livePrompt}
                    onChange={(e) => setLivePrompt(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") sendLivePrompt(); }}
                    className="flex-1 bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500"
                  />
                  <button
                    onClick={sendLivePrompt}
                    disabled={livePromptSaving || !livePrompt.trim()}
                    className="bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-white font-bold px-4 py-2 rounded-lg text-sm transition-colors"
                  >
                    {livePromptSaving ? "Saving…" : "Send"}
                  </button>
                </div>
                {liveTask.custom_prompt_override && (
                  <p className="font-mono text-xs text-emerald-400">
                    ✓ Active instruction: &quot;{liveTask.custom_prompt_override}&quot;
                  </p>
                )}
              </div>
            )}

            {/* Log stream */}
            <div>
              <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-2">Live Log</p>
              <div className="bg-slate-950 rounded-lg border border-slate-800 p-3 h-56 overflow-y-auto font-mono text-xs space-y-0.5 flex flex-col-reverse">
                {(liveTask.logs ?? []).length === 0 ? (
                  <p className="text-slate-600">Waiting for bot to start…</p>
                ) : (
                  [...(liveTask.logs ?? [])].reverse().map((entry, i) => (
                    <div key={i} className="flex gap-2 leading-5">
                      <span className="text-slate-600 shrink-0">{entry.ts}</span>
                      <span className={
                        entry.level === "success" ? "text-emerald-400" :
                        entry.level === "error"   ? "text-red-400" :
                        entry.level === "warning" ? "text-amber-400" :
                        "text-slate-400"
                      }>
                        {entry.level === "success" ? "✅" : entry.level === "error" ? "❌" : entry.level === "warning" ? "⚠" : "·"}
                      </span>
                      <span className={
                        entry.level === "success" ? "text-emerald-300" :
                        entry.level === "error"   ? "text-red-300" :
                        entry.level === "warning" ? "text-amber-300" :
                        "text-slate-300"
                      }>{entry.msg}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Final result */}
            {liveTask.status === "DONE" && liveTask.output && (
              <div>
                <div className="flex items-center gap-3 p-3 rounded-lg bg-emerald-400/10 border border-emerald-400/20">
                  <span className="text-2xl">🎉</span>
                  <div>
                    <p className="font-body font-semibold text-emerald-400">
                      Applied to {liveTask.output.applied_count ?? 0} jobs
                    </p>
                    <p className="font-body text-xs text-slate-400 mt-0.5">{liveTask.output.message}</p>
                  </div>
                </div>
                {/* Per-job completion report */}
                {liveTask.output.report && liveTask.output.report.length > 0 && (
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-slate-700 text-slate-500">
                          <th className="text-left py-2 px-2 font-mono">#</th>
                          <th className="text-left py-2 px-2 font-mono">Company</th>
                          <th className="text-left py-2 px-2 font-mono">Position</th>
                          <th className="text-left py-2 px-2 font-mono">Score</th>
                          <th className="text-left py-2 px-2 font-mono">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {liveTask.output.report.map((r, i) => (
                          <tr key={i} className="border-b border-slate-800">
                            <td className="py-1.5 px-2 text-slate-600">{i + 1}</td>
                            <td className="py-1.5 px-2 text-slate-300">{r.company || "—"}</td>
                            <td className="py-1.5 px-2 text-slate-300">{r.job_title || "—"}</td>
                            <td className="py-1.5 px-2 text-slate-400">{r.score != null ? `${r.score}%` : "—"}</td>
                            <td className={`py-1.5 px-2 ${r.status === "applied" ? "text-emerald-400" : "text-amber-400"}`}>
                              {r.status === "applied" ? "✅ Applied" : "⏭ Skipped"}
                              {r.skip_reason ? ` (${r.skip_reason})` : ""}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tasks */}
      <div className="mb-12 animate-fadeUp animate-fadeUp-delay-3">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Tasks ({tasks.length})
        </h2>
        {tasks.length === 0 ? (
          <div className="card border-dashed text-center py-6">
            <p className="text-slate-500 font-body text-sm">No tasks yet. Click "Start Auto Apply" above.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((t) => (
              <div key={t.id} className="card overflow-hidden">
                {/* ── Row header ── */}
                <div
                  onClick={() => {
                    if (t.status === "RUNNING") { setLiveTask(t); return; }
                    if (t.status === "DONE") {
                      setExpandedTaskId((prev) => (prev === t.id ? null : t.id));
                    }
                  }}
                  className={`py-3 flex items-center justify-between ${
                    t.status === "RUNNING" || t.status === "DONE" ? "cursor-pointer hover:bg-slate-800/40" : ""
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="text-lg">
                      {t.status === "PENDING" ? "🟡" : t.status === "RUNNING" ? "🔵" : t.status === "DONE" ? "🟢" : "🔴"}
                    </span>
                    <div>
                      <span className="font-mono text-sm text-white">{t.type}</span>
                      {t.status === "RUNNING" && (
                        <p className="font-mono text-xs text-blue-400 mt-0.5 animate-pulse">
                          Running… {t.progress ?? 0}% — click to view live log
                        </p>
                      )}
                      {t.status === "DONE" && t.output?.applied_count !== undefined && (
                        <p className="font-mono text-xs text-emerald-400 mt-0.5">
                          ✅ {t.output.applied_count} applied — {expandedTaskId === t.id ? "▲ collapse" : "▼ view report"}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`font-mono text-xs px-2 py-0.5 rounded ${
                      t.status === "PENDING" ? "bg-yellow-400/15 text-yellow-400" :
                      t.status === "RUNNING" ? "bg-blue-400/15 text-blue-400" :
                      t.status === "DONE" ? "bg-emerald-400/15 text-emerald-400" :
                      "bg-red-400/15 text-red-400"
                    }`}>{t.status}</span>
                    <span className="font-mono text-xs text-slate-500">
                      {new Date(t.created_at).toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* ── Expanded report ── */}
                {expandedTaskId === t.id && t.output && (
                  <div className="border-t border-slate-800 px-3 pb-3 pt-2">
                    <p className="font-mono text-xs text-slate-500 uppercase tracking-widest mb-2">
                      Completion Report
                    </p>
                    {t.output.report && t.output.report.length > 0 ? (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-slate-700 text-slate-500">
                              <th className="text-left py-2 px-2 font-mono">#</th>
                              <th className="text-left py-2 px-2 font-mono">Company</th>
                              <th className="text-left py-2 px-2 font-mono">Position</th>
                              <th className="text-left py-2 px-2 font-mono">Score</th>
                              <th className="text-left py-2 px-2 font-mono">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {t.output.report.map((r, i) => (
                              <tr key={i} className="border-b border-slate-800">
                                <td className="py-1.5 px-2 text-slate-600">{i + 1}</td>
                                <td className="py-1.5 px-2 text-slate-300">{r.company || "—"}</td>
                                <td className="py-1.5 px-2 text-slate-300">{r.job_title || "—"}</td>
                                <td className="py-1.5 px-2 text-slate-400">{r.score != null ? `${r.score}%` : "—"}</td>
                                <td className={`py-1.5 px-2 ${r.status === "applied" ? "text-emerald-400" : "text-amber-400"}`}>
                                  {r.status === "applied" ? "✅ Applied" : "⏭ Skipped"}
                                  {r.skip_reason ? ` (${r.skip_reason})` : ""}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="font-body text-xs text-slate-500">
                        {t.output.message || `${t.output.applied_count ?? 0} jobs applied`}
                        {" — detailed report not available for older runs."}
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
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
                  <span className="font-body text-sm text-white">{r.title}</span>
                </div>
                <span className="font-mono text-xs text-slate-500">
                  {new Date(r.created_at).toLocaleDateString()}
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
