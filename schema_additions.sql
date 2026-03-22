-- ============================================================
-- SCHEMA ADDITIONS — Run these in Supabase SQL Editor
-- These tables extend the base schema.sql
-- ============================================================


-- ============================================================
-- RESUME VERSIONS
-- Stores AI-tailored versions of a resume (one per job applied)
-- e.g. "Amazon_SDE_v1", "Zoho_Backend_v2"
-- ============================================================
CREATE TABLE IF NOT EXISTS resume_versions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  resume_id        UUID REFERENCES resumes(id) ON DELETE SET NULL,
  job_id           UUID REFERENCES jobs(id)    ON DELETE SET NULL,
  version_name     TEXT NOT NULL,                        -- e.g. "Amazon_SDE_v1"
  original_text    TEXT NOT NULL DEFAULT '',
  tailored_text    TEXT NOT NULL DEFAULT '',
  tailored_content JSONB NOT NULL DEFAULT '{}',          -- bullets, summary, improvements
  ats_score        INT,                                  -- 0-100
  missing_skills   TEXT[] NOT NULL DEFAULT '{}',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resume_versions_user_id   ON resume_versions(user_id);
CREATE INDEX IF NOT EXISTS idx_resume_versions_resume_id ON resume_versions(resume_id);


-- ============================================================
-- COVER LETTERS
-- Stores generated cover letters / intros / follow-up emails
-- ============================================================
CREATE TABLE IF NOT EXISTS cover_letters (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  job_id      UUID REFERENCES jobs(id) ON DELETE SET NULL,
  type        TEXT NOT NULL DEFAULT 'cover_letter',
               -- 'cover_letter' | 'intro_message' | 'linkedin_intro' | 'email_followup'
  content     TEXT NOT NULL,
  metadata    JSONB NOT NULL DEFAULT '{}',               -- company, role, email_subject
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cover_letters_user_id ON cover_letters(user_id);


-- ============================================================
-- JD ANALYSES  (cached — avoid re-calling AI for same JD)
-- ============================================================
CREATE TABLE IF NOT EXISTS jd_analyses (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  job_id            UUID REFERENCES jobs(id) ON DELETE CASCADE,
  jd_text           TEXT NOT NULL,
  required_skills   TEXT[] NOT NULL DEFAULT '{}',
  nice_to_have      TEXT[] NOT NULL DEFAULT '{}',
  keywords          TEXT[] NOT NULL DEFAULT '{}',
  responsibilities  TEXT[] NOT NULL DEFAULT '{}',
  seniority         TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jd_analyses_user_id ON jd_analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_jd_analyses_job_id  ON jd_analyses(job_id);


-- ============================================================
-- COMPANY WATCHLIST
-- Companies the user wants to track for new job postings
-- ============================================================
CREATE TABLE IF NOT EXISTS company_watchlist (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  company     TEXT NOT NULL,
  keywords    TEXT[] NOT NULL DEFAULT '{}',
  platform    TEXT NOT NULL DEFAULT 'both',              -- 'linkedin' | 'naukri' | 'both'
  active      BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, company)
);

CREATE INDEX IF NOT EXISTS idx_company_watchlist_user_id ON company_watchlist(user_id);


-- ============================================================
-- NOTIFICATIONS  (in-app)
-- ============================================================
CREATE TABLE IF NOT EXISTS notifications (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  type        TEXT NOT NULL,
               -- 'new_job' | 'application_complete' | 'follow_up'
               -- | 'resume_ready' | 'interview' | 'general'
  title       TEXT NOT NULL,
  message     TEXT NOT NULL,
  read        BOOLEAN NOT NULL DEFAULT FALSE,
  metadata    JSONB NOT NULL DEFAULT '{}',               -- link, job_id, etc.
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_unread  ON notifications(user_id, read) WHERE read = FALSE;


-- ============================================================
-- Add parsed_text column to resumes (stores extracted text so
-- the AI doesn't need to re-parse the PDF every time)
-- ============================================================
ALTER TABLE resumes ADD COLUMN IF NOT EXISTS parsed_text TEXT;


-- ============================================================
-- Add cover_letter_id to applications so we can link which
-- cover letter was used when applying
-- ============================================================
ALTER TABLE applications ADD COLUMN IF NOT EXISTS cover_letter_id UUID REFERENCES cover_letters(id) ON DELETE SET NULL;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS jd_text         TEXT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS ats_score       INT;
ALTER TABLE applications ADD COLUMN IF NOT EXISTS follow_up_at    TIMESTAMPTZ;


-- ============================================================
-- Live run monitoring columns on tasks
--   logs        — append-only array of {ts, msg} objects streamed by the bot
--   progress    — 0-100 integer shown as a progress bar
--   current_job — company + role the bot is working on right now
--   custom_prompt_override — user can update this while the run is live;
--                            the bot picks it up before each new application
--   paused      — user can flip TRUE to pause; bot polls and waits
--   stop_requested — user can flip TRUE to cleanly stop the run
-- ============================================================
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS logs                   JSONB    NOT NULL DEFAULT '[]';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress               INT      NOT NULL DEFAULT 0;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS current_job            TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS custom_prompt_override TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS paused                 BOOLEAN  NOT NULL DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS stop_requested         BOOLEAN  NOT NULL DEFAULT FALSE;


-- ============================================================
-- Atomic log-append RPC (called by the Python bot)
-- Appends a single entry to tasks.logs without a read-modify-write race.
-- Run this in Supabase SQL Editor after the ALTER TABLE above.
-- ============================================================
CREATE OR REPLACE FUNCTION append_task_log(p_task_id UUID, p_entry JSONB)
RETURNS VOID
LANGUAGE SQL
SECURITY DEFINER
AS $$
  UPDATE tasks
  SET logs = logs || jsonb_build_array(p_entry)
  WHERE id = p_task_id;
$$;

-- Allow the service role (used by the Python bot) to call it
GRANT EXECUTE ON FUNCTION append_task_log(UUID, JSONB) TO service_role;


-- ============================================================
-- RLS — users can only see & modify their own rows
-- ============================================================
ALTER TABLE resume_versions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE cover_letters     ENABLE ROW LEVEL SECURITY;
ALTER TABLE jd_analyses       ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications     ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "owner_only" ON resume_versions;
DROP POLICY IF EXISTS "owner_only" ON cover_letters;
DROP POLICY IF EXISTS "owner_only" ON jd_analyses;
DROP POLICY IF EXISTS "owner_only" ON company_watchlist;
DROP POLICY IF EXISTS "owner_only" ON notifications;

CREATE POLICY "owner_only" ON resume_versions   FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "owner_only" ON cover_letters     FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "owner_only" ON jd_analyses       FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "owner_only" ON company_watchlist FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "owner_only" ON notifications     FOR ALL USING (auth.uid() = user_id);


-- ============================================================
-- GMAIL SETTINGS
-- Stores Gmail App Password credentials for the daily email checker.
-- One row per user.
-- ============================================================
CREATE TABLE IF NOT EXISTS gmail_settings (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  gmail_address  TEXT NOT NULL,
  app_password   TEXT NOT NULL,          -- Google App Password (16-char)
  followup_days  INT  NOT NULL DEFAULT 3,
  last_scanned   TIMESTAMPTZ,
  active         BOOLEAN NOT NULL DEFAULT TRUE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE gmail_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "owner_only" ON gmail_settings;
CREATE POLICY "owner_only" ON gmail_settings FOR ALL USING (auth.uid() = user_id);


-- ============================================================
-- EMAIL THREADS
-- Stores incoming job-related emails and AI-generated replies.
-- Linked to an application when the company can be matched.
-- ============================================================
CREATE TABLE IF NOT EXISTS email_threads (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  application_id  UUID REFERENCES applications(id) ON DELETE SET NULL,
  thread_id       TEXT NOT NULL,
  subject         TEXT NOT NULL,
  from_address    TEXT NOT NULL,
  received_at     TIMESTAMPTZ NOT NULL,
  classification  TEXT NOT NULL DEFAULT 'GENERAL',
                  -- ACKNOWLEDGMENT | INTERVIEW_INVITE | REJECTION
                  -- | SCHEDULE_REQUEST | OFFER | FOLLOWUP_SENT | GENERAL
  ai_summary      TEXT,
  ai_reply_text   TEXT,
  ai_reply_sent   BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, thread_id)
);

CREATE INDEX IF NOT EXISTS idx_email_threads_user_id        ON email_threads(user_id);
CREATE INDEX IF NOT EXISTS idx_email_threads_application_id ON email_threads(application_id);

ALTER TABLE email_threads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "owner_only" ON email_threads;
CREATE POLICY "owner_only" ON email_threads FOR ALL USING (auth.uid() = user_id);
