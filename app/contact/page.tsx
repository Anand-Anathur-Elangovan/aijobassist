"use client";

import { useState } from "react";

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });
  const [sent, setSent] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // In production, this would send to an API or email service
    setSent(true);
  };

  return (
    <main className="min-h-screen bg-slate-950 py-16 px-6">
      <div className="max-w-xl mx-auto">
        <h1 className="text-3xl font-display font-bold text-white mb-2">Contact Us</h1>
        <p className="text-slate-400 mb-8">We&apos;d love to hear from you. Send us a message!</p>

        {sent ? (
          <div className="card text-center py-12">
            <div className="text-4xl mb-3">✅</div>
            <h2 className="text-xl font-display font-bold text-white mb-2">Message Sent!</h2>
            <p className="text-slate-400">We&apos;ll get back to you within 24 hours.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="card space-y-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Name</label>
              <input
                type="text"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="input-base"
                placeholder="Your name"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Email</label>
              <input
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="input-base"
                placeholder="you@email.com"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Subject</label>
              <select
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                className="input-base"
              >
                <option value="">Select a topic</option>
                <option value="billing">Billing & Payments</option>
                <option value="bug">Bug Report</option>
                <option value="feature">Feature Request</option>
                <option value="support">Technical Support</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Message</label>
              <textarea
                required
                rows={5}
                value={form.message}
                onChange={(e) => setForm({ ...form, message: e.target.value })}
                className="input-base resize-none"
                placeholder="Tell us what's on your mind..."
              />
            </div>
            <button type="submit" className="btn-primary w-full">
              Send Message
            </button>
          </form>
        )}

        <div className="mt-8 text-center text-slate-500 text-sm">
          <p>Or email us directly at <a href="mailto:support@vantahire.com" className="text-amber-400 hover:underline">support@vantahire.com</a></p>
        </div>
      </div>
    </main>
  );
}
