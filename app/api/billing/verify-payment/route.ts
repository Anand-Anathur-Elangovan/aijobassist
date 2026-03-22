// app/api/billing/verify-payment/route.ts
// Verifies Razorpay payment signature and activates subscription

import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import crypto from "crypto";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://feqhdpxnzlctpwvvjxui.supabase.co";
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk";
const RAZORPAY_KEY_SECRET = process.env.RAZORPAY_KEY_SECRET || "";

export async function POST(req: NextRequest) {
  try {
    const authHeader = req.headers.get("authorization");
    if (!authHeader) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);
    const { data: { user }, error: authError } = await supabase.auth.getUser(authHeader.replace("Bearer ", ""));
    if (authError || !user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

    const { razorpay_order_id, razorpay_payment_id, razorpay_signature, plan_slug, billing_cycle } = await req.json();

    if (!razorpay_order_id || !razorpay_payment_id || !razorpay_signature) {
      return NextResponse.json({ error: "Missing payment details" }, { status: 400 });
    }

    // Verify signature
    const body = razorpay_order_id + "|" + razorpay_payment_id;
    const expectedSignature = crypto
      .createHmac("sha256", RAZORPAY_KEY_SECRET)
      .update(body)
      .digest("hex");

    if (expectedSignature !== razorpay_signature) {
      return NextResponse.json({ error: "Invalid payment signature" }, { status: 400 });
    }

    // Get plan
    const { data: plan } = await supabase
      .from("plans")
      .select("*")
      .eq("slug", plan_slug)
      .single();

    if (!plan) return NextResponse.json({ error: "Plan not found" }, { status: 404 });

    const amount = billing_cycle === "weekly" ? plan.price_weekly : plan.price_monthly;
    const periodDays = billing_cycle === "weekly" ? 7 : 30;

    // Cancel existing active subscriptions
    await supabase
      .from("subscriptions")
      .update({ status: "cancelled", cancelled_at: new Date().toISOString() })
      .eq("user_id", user.id)
      .in("status", ["active", "past_due"]);

    // Create new subscription
    const now = new Date();
    const periodEnd = new Date(now.getTime() + periodDays * 24 * 60 * 60 * 1000);

    const { data: subscription } = await supabase
      .from("subscriptions")
      .insert({
        user_id: user.id,
        plan_id: plan.id,
        status: "active",
        billing_cycle,
        current_period_start: now.toISOString(),
        current_period_end: periodEnd.toISOString(),
      })
      .select()
      .single();

    // Record payment
    await supabase.from("payments").insert({
      user_id: user.id,
      subscription_id: subscription?.id,
      razorpay_payment_id,
      razorpay_order_id,
      razorpay_signature,
      amount,
      currency: "INR",
      status: "captured",
      metadata: { plan_slug, billing_cycle },
    });

    // Send notification
    await supabase.from("notifications").insert({
      user_id: user.id,
      type: "general",
      title: "Subscription Activated",
      message: `Your ${plan.name} plan (${billing_cycle}) is now active!`,
      metadata: { plan_slug },
    });

    return NextResponse.json({
      success: true,
      subscription_id: subscription?.id,
      plan: plan.name,
      period_end: periodEnd.toISOString(),
    });
  } catch (err) {
    console.error("Verify payment error:", err);
    return NextResponse.json({ error: "Payment verification failed" }, { status: 500 });
  }
}
