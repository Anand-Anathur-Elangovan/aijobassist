import NavBar from "@/components/NavBar";
import AuthGuard from "@/components/AuthGuard";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="min-h-screen flex flex-col bg-slate-950">
        <NavBar />
        <main className="flex-1">{children}</main>
      </div>
    </AuthGuard>
  );
}
