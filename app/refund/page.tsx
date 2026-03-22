export default function RefundPage() {
  return (
    <main className="min-h-screen bg-slate-950 py-16 px-6">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-display font-bold text-white mb-8">Refund Policy</h1>
        <p className="text-slate-400 text-sm mb-6">Last updated: {new Date().toLocaleDateString()}</p>

        <section className="space-y-4 text-slate-300 text-sm leading-relaxed">
          <h2 className="text-lg font-semibold text-white">1. Free Trial</h2>
          <p>The 10-day free trial requires no payment. If you don&apos;t upgrade, you automatically move to the Free plan with no charges.</p>

          <h2 className="text-lg font-semibold text-white">2. Paid Subscriptions</h2>
          <p>When you subscribe to a paid plan, you are billed at the start of each billing period (weekly or monthly). You can cancel at any time and retain access until the end of the current billing period.</p>

          <h2 className="text-lg font-semibold text-white">3. Refund Eligibility</h2>
          <p>We offer full refunds within 48 hours of purchase if you haven&apos;t used the service significantly (fewer than 5 actions). After 48 hours, or if the service has been used substantially, refunds are handled on a case-by-case basis.</p>

          <h2 className="text-lg font-semibold text-white">4. How to Request a Refund</h2>
          <p>Email support@vantahire.com with your registered email and reason for the refund. We aim to process all requests within 5-7 business days.</p>

          <h2 className="text-lg font-semibold text-white">5. Cancellation</h2>
          <p>You can cancel your subscription from the Billing page in your account. No future charges will be applied after cancellation.</p>

          <h2 className="text-lg font-semibold text-white">6. Contact</h2>
          <p>For refund queries: support@vantahire.com</p>
        </section>
      </div>
    </main>
  );
}
