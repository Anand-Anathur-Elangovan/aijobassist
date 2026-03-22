export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-slate-950 py-16 px-6">
      <div className="max-w-3xl mx-auto prose prose-invert prose-sm">
        <h1 className="text-3xl font-display font-bold text-white mb-8">Privacy Policy</h1>
        <p className="text-slate-400 text-sm mb-6">Last updated: {new Date().toLocaleDateString()}</p>

        <section className="space-y-4 text-slate-300 text-sm leading-relaxed">
          <h2 className="text-lg font-semibold text-white">1. Information We Collect</h2>
          <p>We collect information you provide directly: email address, name, phone number, resume data, job preferences, and Gmail credentials (for email monitoring). We also collect usage data like application counts and feature usage.</p>

          <h2 className="text-lg font-semibold text-white">2. How We Use Your Data</h2>
          <p>Your data is used to: provide AI resume tailoring, automate job applications, monitor your email for interview invites, generate analytics, and manage your subscription. We never sell your personal data to third parties.</p>

          <h2 className="text-lg font-semibold text-white">3. Data Storage & Security</h2>
          <p>All data is stored securely on Supabase (PostgreSQL) with row-level security policies. Passwords are hashed. Communications are encrypted via TLS. Payment processing is handled by Razorpay — we never store card details.</p>

          <h2 className="text-lg font-semibold text-white">4. Third-Party Services</h2>
          <p>We use: Supabase (database & auth), Anthropic Claude (AI processing), Razorpay (payments), LinkedIn & Naukri (job applications — via your own credentials).</p>

          <h2 className="text-lg font-semibold text-white">5. Your Rights</h2>
          <p>You can: access your data, export your data, delete your account, or update your information at any time from the Settings page.</p>

          <h2 className="text-lg font-semibold text-white">6. Gmail Integration</h2>
          <p>When you connect Gmail, we use your App Password to read incoming emails and classify them (interview invites, rejections, etc.). We do not read, store, or share the full content of non-job-related emails.</p>

          <h2 className="text-lg font-semibold text-white">7. Contact</h2>
          <p>For privacy concerns, contact us at support@vantahire.com.</p>
        </section>
      </div>
    </main>
  );
}
