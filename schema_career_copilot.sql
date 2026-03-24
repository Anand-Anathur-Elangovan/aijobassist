-- ============================================================
-- CAREER COPILOT SCHEMA
-- School → College Engine — Student profiles + AI predictions
-- Run this in Supabase SQL Editor AFTER schema.sql,
-- schema_additions.sql, and schema_billing.sql
-- ============================================================


-- ============================================================
-- APP MODE on user_profiles
-- Lets users switch between job-seeker and student mode.
-- user_profiles is auto-created by Supabase Auth triggers.
-- ============================================================
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS app_mode TEXT NOT NULL DEFAULT 'job_seeker';
-- 'job_seeker' → VantaHire job automation features
-- 'student'    → Career Copilot school-to-college engine

COMMENT ON COLUMN user_profiles.app_mode IS
  'Active product mode: job_seeker | student';


-- ============================================================
-- STUDENT PROFILES
-- One row per user; upserted on each Career Copilot query.
-- ============================================================
CREATE TABLE IF NOT EXISTS student_profiles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  student_name    TEXT     NOT NULL DEFAULT '',
  state           TEXT     NOT NULL DEFAULT '',
  board           TEXT     NOT NULL DEFAULT 'CBSE',   -- 'CBSE' | 'ICSE' | 'State Board'
  marks_10th      NUMERIC(5,2),                       -- percentage e.g. 92.5
  marks_12th      NUMERIC(5,2),
  stream_12th     TEXT,                               -- 'PCM' | 'PCB' | 'Commerce' | 'Arts'
  entrance_exams  TEXT[]   NOT NULL DEFAULT '{}',     -- ['JEE Main','NEET', ...]
  community       TEXT     NOT NULL DEFAULT 'OC',     -- 'OC'|'BC'|'MBC'|'SC'|'ST'
  quota           TEXT[]   NOT NULL DEFAULT '{}',     -- ['Sports','Management', ...]
  interests       TEXT[]   NOT NULL DEFAULT '{}',     -- ['AI','Medicine','Finance', ...]
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_student_profiles_user_id
  ON student_profiles(user_id);

ALTER TABLE student_profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "owner_only" ON student_profiles;
CREATE POLICY "owner_only" ON student_profiles
  FOR ALL USING (auth.uid() = user_id);


-- ============================================================
-- CAREER PREDICTIONS
-- Every AI prediction run is stored here (full history).
-- ============================================================
CREATE TABLE IF NOT EXISTS career_predictions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  student_profile_id  UUID REFERENCES student_profiles(id) ON DELETE SET NULL,
  input_snapshot      JSONB NOT NULL DEFAULT '{}',  -- copy of inputs at prediction time
  courses             JSONB NOT NULL DEFAULT '[]',  -- CareerCourseResult[]
  colleges            JSONB NOT NULL DEFAULT '[]',  -- CareerCollegeResult[]
  exam_roadmap        JSONB NOT NULL DEFAULT '[]',  -- CareerExamRoadmap[]
  strategy            JSONB NOT NULL DEFAULT '{}',  -- CareerStrategy
  is_fallback         BOOLEAN NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_career_predictions_user_id
  ON career_predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_career_predictions_created
  ON career_predictions(created_at DESC);

ALTER TABLE career_predictions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "owner_only" ON career_predictions;
CREATE POLICY "owner_only" ON career_predictions
  FOR ALL USING (auth.uid() = user_id);


-- ============================================================
-- Auto-update student_profiles.updated_at on row change
-- ============================================================
CREATE TRIGGER trg_student_profiles_updated_at
  BEFORE UPDATE ON student_profiles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
-- (set_updated_at() is already defined in schema.sql)
