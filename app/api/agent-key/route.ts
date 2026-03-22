import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import crypto from "crypto";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://feqhdpxnzlctpwvvjxui.supabase.co";
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk";

function getServiceSupabase() {
  return createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
}

async function getUser(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  if (!authHeader) return null;
  const sb = getServiceSupabase();
  const { data: { user } } = await sb.auth.getUser(authHeader.replace("Bearer ", ""));
  return user;
}

// GET — get current active key info (prefix only, never the full key)
export async function GET(req: NextRequest) {
  try {
    const user = await getUser(req);
    if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const sb = getServiceSupabase();
    const { data, error } = await sb
      .from("agent_keys")
      .select("id, key_prefix, label, is_active, last_used, created_at")
      .eq("user_id", user.id)
      .eq("is_active", true)
      .single();

    if (error && error.code !== "PGRST116") {
      // PGRST116 = no rows found (that's fine, user has no key)
      return NextResponse.json({ key: null, error: error.message }, { status: 200 });
    }

    return NextResponse.json({ key: data });
  } catch (e) {
    return NextResponse.json({ key: null, error: "Failed to fetch key" }, { status: 200 });
  }
}

// POST — generate a new agent key (revokes any existing one)
export async function POST(req: NextRequest) {
  const user = await getUser(req);
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sb = getServiceSupabase();

  // Revoke any existing active key
  await sb
    .from("agent_keys")
    .update({ is_active: false })
    .eq("user_id", user.id)
    .eq("is_active", true);

  // Generate a new key: vh_<32 random hex chars>
  const rawKey = `vh_${crypto.randomBytes(24).toString("hex")}`;
  const keyHash = crypto.createHash("sha256").update(rawKey).digest("hex");
  const keyPrefix = rawKey.slice(0, 11); // "vh_a1b2c3d4"

  const { error } = await sb.from("agent_keys").insert({
    user_id: user.id,
    key_hash: keyHash,
    key_prefix: keyPrefix,
    label: "default",
    is_active: true,
  });

  if (error) {
    return NextResponse.json({ error: "Failed to create key" }, { status: 500 });
  }

  // Return the FULL key only once — it's never stored in plaintext
  return NextResponse.json({ key: rawKey, prefix: keyPrefix });
}

// DELETE — revoke the active key
export async function DELETE(req: NextRequest) {
  const user = await getUser(req);
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sb = getServiceSupabase();
  await sb
    .from("agent_keys")
    .update({ is_active: false })
    .eq("user_id", user.id)
    .eq("is_active", true);

  return NextResponse.json({ success: true });
}
