-- ============================================================
-- VantaHire — Railway Cloud Execution Tables
-- Run ALL of these in Supabase SQL Editor in order
-- ============================================================

-- ── 1. Add execution mode columns to tasks table ────────────
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS execution_mode TEXT DEFAULT 'own_machine';
-- 'own_machine' (default, existing behaviour) or 'railway' (cloud)

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS railway_job_id TEXT;
-- Stores the Railway run ID when execution_mode = 'railway'

-- ── 2. Add Railway preference columns to user_profiles ───────
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_execution_mode TEXT DEFAULT 'own_machine';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS railway_configured BOOL DEFAULT FALSE;

-- ── 3. Add railway_minutes daily limit to plan_limits ────────
-- Adds a new action_type 'railway_minutes' for each plan
INSERT INTO plan_limits (plan_id, action_type, daily_limit)
SELECT
  p.id,
  'railway_minutes',
  CASE p.slug
    WHEN 'trial'   THEN 5
    WHEN 'free'    THEN 5
    WHEN 'normal'  THEN 15
    WHEN 'premium' THEN 30
    ELSE 5
  END
FROM plans p
WHERE p.slug IN ('trial', 'free', 'normal', 'premium')
ON CONFLICT (plan_id, action_type) DO NOTHING;

-- ── 4. Railway sessions table ────────────────────────────────
-- Tracks every cloud automation run per user
CREATE TABLE IF NOT EXISTS railway_sessions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            UUID REFERENCES auth.users NOT NULL,
  task_id            UUID REFERENCES tasks(id),
  railway_run_id     TEXT,
  status             TEXT DEFAULT 'pending',
    -- 'pending' | 'running' | 'completed' | 'failed' | 'stopped'
  started_at         TIMESTAMPTZ DEFAULT now(),
  ended_at           TIMESTAMPTZ,
  duration_seconds   INT,
  screenshot_count   INT DEFAULT 0,
  latest_screenshot  TEXT,        -- base64-encoded JPEG updated every ~1s by bot
  error              TEXT,
  created_at         TIMESTAMPTZ DEFAULT now()
);

-- ── 5. Railway daily usage tracker ───────────────────────────
-- One row per (user, date) — minutes_used increments as sessions complete
CREATE TABLE IF NOT EXISTS railway_daily_usage (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID REFERENCES auth.users NOT NULL,
  usage_date   DATE DEFAULT CURRENT_DATE,
  minutes_used NUMERIC(6,2) DEFAULT 0,
  UNIQUE(user_id, usage_date)
);

-- ── 6. Row Level Security ─────────────────────────────────────
ALTER TABLE railway_sessions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE railway_daily_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users own railway sessions"
  ON railway_sessions FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "Users own railway daily usage"
  ON railway_daily_usage FOR ALL
  USING (auth.uid() = user_id);

-- ── 7. RPC: atomically increment Railway minutes used today ───
-- Called from lib/railway.ts → incrementRailwayUsage()
CREATE OR REPLACE FUNCTION increment_railway_minutes(
  p_user_id UUID,
  p_date    DATE,
  p_minutes NUMERIC
) RETURNS VOID AS $$
BEGIN
  INSERT INTO railway_daily_usage (user_id, usage_date, minutes_used)
  VALUES (p_user_id, p_date, p_minutes)
  ON CONFLICT (user_id, usage_date)
  DO UPDATE SET minutes_used = railway_daily_usage.minutes_used + EXCLUDED.minutes_used;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ── 8. Add vnc_port to railway_sessions (per-user display isolation) ─────────
-- Each session now gets its own Xvfb display + x11vnc port (5901–5910).
-- The frontend uses this to build the correct /novnc/?session= URL.
ALTER TABLE railway_sessions ADD COLUMN IF NOT EXISTS vnc_port INT;

-- ── Done ──────────────────────────────────────────────────────
-- After running this, update your .env.local with real Railway values.
-- See CODEBASE_CONTEXT.md Section 3 for required env vars.
