// app/api/billing/webhook/route.ts
// Razorpay webhook handler for automated payment events

import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import crypto from "crypto";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://feqhdpxnzlctpwvvjxui.supabase.co";
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZlcWhkcHhuemxjdHB3dnZqeHVpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDEwNzMyNSwiZXhwIjoyMDg5NjgzMzI1fQ.LDv5jcFnSgMEha9SkWPaCohxgQsJwH64FeQXDx4x5nk";
const RAZORPAY_WEBHOOK_SECRET = process.env.RAZORPAY_WEBHOOK_SECRET || "";

export async function POST(req: NextRequest) {
  try {
    const body = await req.text();

    // Verify webhook signature
    if (RAZORPAY_WEBHOOK_SECRET) {
      const signature = req.headers.get("x-razorpay-signature") || "";
      const expectedSignature = crypto
        .createHmac("sha256", RAZORPAY_WEBHOOK_SECRET)
        .update(body)
        .digest("hex");

      if (signature !== expectedSignature) {
        return NextResponse.json({ error: "Invalid signature" }, { status: 400 });
      }
    }

    const event = JSON.parse(body);
    const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

    switch (event.event) {
      case "payment.captured": {
        const payment = event.payload?.payment?.entity;
        if (!payment) break;

        const userId = payment.notes?.user_id;
        if (!userId) break;

        // Record payment
        await sb.from("payments").insert({
          user_id: userId,
          razorpay_payment_id: payment.id,
          razorpay_order_id: payment.order_id,
          amount: payment.amount,
          currency: payment.currency,
          status: "captured",
          metadata: payment.notes || {},
        });
        break;
      }

      case "payment.failed": {
        const payment = event.payload?.payment?.entity;
        if (!payment) break;

        const userId = payment.notes?.user_id;
        if (!userId) break;

        await sb.from("notifications").insert({
          user_id: userId,
          type: "general",
          title: "Payment Failed",
          message: "Your payment failed. Please retry or update your payment method.",
          metadata: { razorpay_payment_id: payment.id },
        });
        break;
      }

      case "subscription.cancelled": {
        const subscription = event.payload?.subscription?.entity;
        if (!subscription) break;

        await sb
          .from("subscriptions")
          .update({ status: "cancelled", cancelled_at: new Date().toISOString() })
          .eq("razorpay_subscription_id", subscription.id);
        break;
      }
    }

    return NextResponse.json({ status: "ok" });
  } catch (err) {
    console.error("Webhook error:", err);
    return NextResponse.json({ error: "Webhook processing failed" }, { status: 500 });
  }
}
