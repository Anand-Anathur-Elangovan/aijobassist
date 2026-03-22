export default function TermsPage() {
  return (
    <main className="min-h-screen bg-slate-950 py-16 px-6">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-3xl font-display font-bold text-white mb-8">Terms of Service</h1>
        <p className="text-slate-400 text-sm mb-6">Last updated: {new Date().toLocaleDateString()}</p>

        <section className="space-y-4 text-slate-300 text-sm leading-relaxed">
          <h2 className="text-lg font-semibold text-white">1. Acceptance</h2>
          <p>By using VantaHire, you agree to these terms. If you disagree, please discontinue use.</p>

          <h2 className="text-lg font-semibold text-white">2. Service Description</h2>
          <p>VantaHire is an AI-powered job search platform that helps users tailor resumes, auto-apply to jobs, monitor emails, and track applications. The service runs automation on your behalf on third-party platforms (LinkedIn, Naukri).</p>

          <h2 className="text-lg font-semibold text-white">3. User Responsibilities</h2>
          <p>You are responsible for: providing accurate information, maintaining your LinkedIn/Naukri credentials, ensuring your resume content is truthful, and complying with third-party platform terms of service.</p>

          <h2 className="text-lg font-semibold text-white">4. Subscriptions & Billing</h2>
          <p>Paid plans are billed weekly or monthly via Razorpay. You can cancel anytime — access continues until the current billing period ends. Free trial is 10 days with full access.</p>

          <h2 className="text-lg font-semibold text-white">5. Usage Limits</h2>
          <p>Each plan has daily usage limits for auto-apply, AI tailoring, and other features. Exceeding limits may result in throttling until the next day.</p>

          <h2 className="text-lg font-semibold text-white">6. Disclaimer</h2>
          <p>VantaHire does not guarantee job placement, interview calls, or specific outcomes. AI-generated content should be reviewed before use. We are not responsible for actions taken by third-party platforms.</p>

          <h2 className="text-lg font-semibold text-white">7. Termination</h2>
          <p>We reserve the right to suspend accounts that violate these terms, abuse automation limits, or engage in fraudulent activity.</p>

          <h2 className="text-lg font-semibold text-white">8. Contact</h2>
          <p>Questions? Email us at support@vantahire.com.</p>
        </section>
      </div>
    </main>
  );
}
