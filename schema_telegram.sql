-- ============================================================
-- Telegram Chat ID for per-user notifications
-- Run in Supabase SQL Editor
-- ============================================================

-- Add telegram_chat_id to user_profiles
-- Users enter this in Settings → Notifications tab
-- The bot token is a server-side env var (TELEGRAM_BOT_TOKEN)
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT;
