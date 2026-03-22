-- ============================================================
-- BILLING & SUBSCRIPTION SCHEMA
-- Run in Supabase SQL Editor after schema.sql + schema_additions.sql
-- ============================================================

-- ============================================================
-- PLANS — defines available subscription tiers
-- ============================================================
CREATE TABLE IF NOT EXISTS plans (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            TEXT NOT NULL UNIQUE,         -- 'trial', 'free', 'normal', 'premium'
  name            TEXT NOT NULL,
  description     TEXT,
  price_monthly   INT NOT NULL DEFAULT 0,       -- in paise (INR) — 99900 = ₹999
  price_weekly    INT NOT NULL DEFAULT 0,       -- in paise (INR)
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order      INT NOT NULL DEFAULT 0,
  features        JSONB NOT NULL DEFAULT '{}',  -- { "ai_tailoring": true, "auto_apply": true, ... }
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed the 4 plans
INSERT INTO plans (slug, name, description, price_monthly, price_weekly, sort_order, features)
VALUES
  ('trial',   'Free Trial',  '10-day full access trial',  0,      0,     0, '{"trial_days": 10, "auto_apply": true, "semi_auto": true, "ai_tailoring": true, "gmail_monitor": true, "cover_letter": true, "analytics": true, "priority_support": false}'),
  ('free',    'Free',        'Basic job search tools',    0,      0,     1, '{"auto_apply": false, "semi_auto": true, "ai_tailoring": true, "gmail_monitor": true, "cover_letter": true, "analytics": false, "priority_support": false}'),
  ('normal',  'Pro',         'For active job seekers',    99900,  34900, 2, '{"auto_apply": true, "semi_auto": true, "ai_tailoring": true, "gmail_monitor": true, "cover_letter": true, "analytics": true, "priority_support": false}'),
  ('premium', 'Premium',     'Maximum automation power',  199900, 69900, 3, '{"auto_apply": true, "semi_auto": true, "ai_tailoring": true, "gmail_monitor": true, "cover_letter": true, "analytics": true, "priority_support": true}')
ON CONFLICT (slug) DO NOTHING;


-- ============================================================
-- PLAN_LIMITS — daily usage caps per plan
-- ============================================================
CREATE TABLE IF NOT EXISTS plan_limits (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id       UUID NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  action_type   TEXT NOT NULL,                  -- 'auto_apply', 'semi_auto', 'ai_tailor', 'gmail_scan', 'cover_letter', 'jd_analysis'
  daily_limit   INT NOT NULL DEFAULT 0,
  UNIQUE (plan_id, action_type)
);

-- Seed limits (use plan slugs to look up IDs)
INSERT INTO plan_limits (plan_id, action_type, daily_limit)
SELECT p.id, v.action_type, v.daily_limit
FROM plans p
CROSS JOIN (VALUES
  -- Trial limits
  ('trial', 'auto_apply',    10),
  ('trial', 'semi_auto',     20),
  ('trial', 'ai_tailor',      5),
  ('trial', 'gmail_scan',     5),
  ('trial', 'cover_letter',   5),
  ('trial', 'jd_analysis',   10),
  -- Free limits
  ('free',  'auto_apply',     0),
  ('free',  'semi_auto',     10),
  ('free',  'ai_tailor',      1),
  ('free',  'gmail_scan',     3),
  ('free',  'cover_letter',   2),
  ('free',  'jd_analysis',    5),
  -- Normal/Pro limits
  ('normal','auto_apply',    25),
  ('normal','semi_auto',     75),
  ('normal','ai_tailor',     15),
  ('normal','gmail_scan',    25),
  ('normal','cover_letter',  15),
  ('normal','jd_analysis',   50),
  -- Premium limits
  ('premium','auto_apply',   80),
  ('premium','semi_auto',   200),
  ('premium','ai_tailor',    40),
  ('premium','gmail_scan',   75),
  ('premium','cover_letter', 40),
  ('premium','jd_analysis', 999)
) AS v(plan_slug, action_type, daily_limit)
WHERE p.slug = v.plan_slug
ON CONFLICT (plan_id, action_type) DO NOTHING;


-- ============================================================
-- SUBSCRIPTIONS — one active subscription per user
-- ============================================================
CREATE TABLE IF NOT EXISTS subscriptions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  plan_id             UUID NOT NULL REFERENCES plans(id),
  status              TEXT NOT NULL DEFAULT 'active',
                      -- 'active', 'cancelled', 'expired', 'past_due'
  billing_cycle       TEXT NOT NULL DEFAULT 'monthly',
                      -- 'weekly', 'monthly', 'trial'
  razorpay_subscription_id TEXT,
  razorpay_customer_id     TEXT,
  trial_ends_at       TIMESTAMPTZ,
  current_period_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  current_period_end   TIMESTAMPTZ,
  cancelled_at        TIMESTAMPTZ,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status  ON subscriptions(status);

-- Only one active sub per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_active_user
  ON subscriptions(user_id) WHERE status IN ('active', 'past_due');


-- ============================================================
-- USAGE_EVENTS — granular log of every billable action
-- ============================================================
CREATE TABLE IF NOT EXISTS usage_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL,
  metadata    JSONB NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_events_user_id    ON usage_events(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_created_at ON usage_events(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_events_user_day   ON usage_events(user_id, action_type, created_at);


-- ============================================================
-- DAILY_USAGE — materialized daily counter for fast quota checks
-- Updated via trigger on usage_events
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_usage (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  action_type TEXT NOT NULL,
  usage_date  DATE NOT NULL DEFAULT CURRENT_DATE,
  count       INT NOT NULL DEFAULT 0,
  UNIQUE (user_id, action_type, usage_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_usage_lookup
  ON daily_usage(user_id, action_type, usage_date);


-- ============================================================
-- PAYMENTS — Razorpay payment records
-- ============================================================
CREATE TABLE IF NOT EXISTS payments (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  subscription_id      UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
  razorpay_payment_id  TEXT NOT NULL,
  razorpay_order_id    TEXT,
  razorpay_signature   TEXT,
  amount               INT NOT NULL,             -- in paise
  currency             TEXT NOT NULL DEFAULT 'INR',
  status               TEXT NOT NULL DEFAULT 'captured',
  metadata             JSONB NOT NULL DEFAULT '{}',
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);


-- ============================================================
-- USER_PROFILES — extended user info
-- ============================================================
CREATE TABLE IF NOT EXISTS user_profiles (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name       TEXT,
  phone           TEXT,
  country         TEXT DEFAULT 'India',
  avatar_url      TEXT,
  onboarding_done BOOLEAN NOT NULL DEFAULT FALSE,
  role            TEXT NOT NULL DEFAULT 'user',   -- 'user' | 'admin'
  job_preferences JSONB NOT NULL DEFAULT '{}',    -- desired_roles, locations, etc.
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_role    ON user_profiles(role);


-- ============================================================
-- FUNCTIONS
-- ============================================================

-- Increment daily usage counter (called by API)
CREATE OR REPLACE FUNCTION increment_usage(
  p_user_id UUID,
  p_action_type TEXT
)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_count INT;
BEGIN
  INSERT INTO daily_usage (user_id, action_type, usage_date, count)
  VALUES (p_user_id, p_action_type, CURRENT_DATE, 1)
  ON CONFLICT (user_id, action_type, usage_date)
  DO UPDATE SET count = daily_usage.count + 1
  RETURNING count INTO v_count;

  INSERT INTO usage_events (user_id, action_type)
  VALUES (p_user_id, p_action_type);

  RETURN v_count;
END;
$$;

-- Check if user has quota remaining
CREATE OR REPLACE FUNCTION check_quota(
  p_user_id UUID,
  p_action_type TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_plan_id UUID;
  v_limit INT;
  v_used INT;
  v_sub_status TEXT;
  v_trial_end TIMESTAMPTZ;
BEGIN
  -- Get active subscription
  SELECT s.plan_id, s.status, s.trial_ends_at
  INTO v_plan_id, v_sub_status, v_trial_end
  FROM subscriptions s
  WHERE s.user_id = p_user_id
    AND s.status IN ('active', 'past_due')
  ORDER BY s.created_at DESC
  LIMIT 1;

  -- No subscription = free plan
  IF v_plan_id IS NULL THEN
    SELECT id INTO v_plan_id FROM plans WHERE slug = 'free';
  END IF;

  -- Check trial expiry
  IF v_trial_end IS NOT NULL AND v_trial_end < NOW() THEN
    SELECT id INTO v_plan_id FROM plans WHERE slug = 'free';
  END IF;

  -- Get limit
  SELECT daily_limit INTO v_limit
  FROM plan_limits
  WHERE plan_id = v_plan_id AND action_type = p_action_type;

  IF v_limit IS NULL THEN v_limit := 0; END IF;

  -- Get today's usage
  SELECT COALESCE(count, 0) INTO v_used
  FROM daily_usage
  WHERE user_id = p_user_id
    AND action_type = p_action_type
    AND usage_date = CURRENT_DATE;

  IF v_used IS NULL THEN v_used := 0; END IF;

  RETURN jsonb_build_object(
    'allowed', v_used < v_limit,
    'used', v_used,
    'limit', v_limit,
    'remaining', GREATEST(0, v_limit - v_used)
  );
END;
$$;

-- Auto-create trial subscription for new users
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_trial_plan_id UUID;
BEGIN
  -- Create profile
  INSERT INTO user_profiles (user_id, full_name)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'full_name', ''));

  -- Create trial subscription
  SELECT id INTO v_trial_plan_id FROM plans WHERE slug = 'trial';
  IF v_trial_plan_id IS NOT NULL THEN
    INSERT INTO subscriptions (user_id, plan_id, status, billing_cycle, trial_ends_at, current_period_end)
    VALUES (NEW.id, v_trial_plan_id, 'active', 'trial', NOW() + INTERVAL '10 days', NOW() + INTERVAL '10 days');
  END IF;

  RETURN NEW;
END;
$$;

-- Trigger on new user signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();


-- ============================================================
-- AUTO-PROMOTE SUPER ADMINS
-- Run once after schema setup — makes these emails admin
-- ============================================================
DO $$
BEGIN
  UPDATE user_profiles
  SET role = 'admin'
  WHERE user_id IN (
    SELECT id FROM auth.users
    WHERE email IN (
      'kaviyasaravanan01@gmail.com',
      'anandanathurelangovan94@gmail.com'
    )
  );
END $$;


-- ============================================================
-- RLS POLICIES
-- ============================================================
ALTER TABLE plans          ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_limits    ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events   ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_usage    ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments       ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles  ENABLE ROW LEVEL SECURITY;

-- Plans & limits are readable by everyone
DROP POLICY IF EXISTS "plans: public read" ON plans;
CREATE POLICY "plans: public read" ON plans FOR SELECT USING (true);
DROP POLICY IF EXISTS "plan_limits: public read" ON plan_limits;
CREATE POLICY "plan_limits: public read" ON plan_limits FOR SELECT USING (true);

-- Users can only see their own data
DROP POLICY IF EXISTS "subscriptions: owner access" ON subscriptions;
CREATE POLICY "subscriptions: owner access" ON subscriptions FOR ALL USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "usage_events: owner access" ON usage_events;
CREATE POLICY "usage_events: owner access" ON usage_events FOR ALL USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "daily_usage: owner access" ON daily_usage;
CREATE POLICY "daily_usage: owner access" ON daily_usage FOR ALL USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "payments: owner access" ON payments;
CREATE POLICY "payments: owner access" ON payments FOR ALL USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "user_profiles: owner access" ON user_profiles;
CREATE POLICY "user_profiles: owner access" ON user_profiles FOR ALL USING (auth.uid() = user_id);

-- Grant RPC functions to service_role and authenticated
GRANT EXECUTE ON FUNCTION increment_usage(UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION increment_usage(UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION check_quota(UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION check_quota(UUID, TEXT) TO authenticated;


-- ============================================================
-- AGENT_KEYS — personal API keys for the desktop agent
-- Each user can have one active key at a time
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_keys (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  key_hash    TEXT NOT NULL,                    -- SHA-256 hash of the key (never store plaintext)
  key_prefix  TEXT NOT NULL,                    -- first 8 chars for display: "vh_a1b2..."
  label       TEXT DEFAULT 'default',
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  last_used   TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_keys_user_id ON agent_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_keys_hash    ON agent_keys(key_hash);

-- Only one active key per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_keys_active_user
  ON agent_keys(user_id) WHERE is_active = TRUE;

ALTER TABLE agent_keys ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "agent_keys: owner access" ON agent_keys;
CREATE POLICY "agent_keys: owner access" ON agent_keys FOR ALL USING (auth.uid() = user_id);
