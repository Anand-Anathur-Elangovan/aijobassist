import NavBar from "@/components/NavBar";
import AuthGuard from "@/components/AuthGuard";
import { SubscriptionProvider, TrialBanner } from "@/components/SubscriptionGuard";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <SubscriptionProvider>
        <div className="min-h-screen flex flex-col bg-slate-950">
          <TrialBanner />
          <NavBar />
          <main className="flex-1">{children}</main>
        </div>
      </SubscriptionProvider>
    </AuthGuard>
  );
}
