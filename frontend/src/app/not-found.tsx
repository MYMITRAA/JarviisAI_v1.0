import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-brand-primary flex items-center justify-center p-6">
      <div className="text-center max-w-md">
        <div className="text-8xl font-black text-brand-accent/20 mb-4">404</div>
        <h1 className="text-2xl font-black text-content-primary mb-2">Page not found</h1>
        <p className="text-content-muted text-sm mb-6">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link href="/dashboard">
            <button className="px-4 py-2 bg-brand-accent text-white rounded-lg text-sm font-semibold hover:bg-brand-accent/80 transition-all">
              Go to Dashboard
            </button>
          </Link>
          <Link href="/">
            <button className="px-4 py-2 border border-surface-border text-content-muted rounded-lg text-sm hover:border-surface-muted transition-all">
              Home
            </button>
          </Link>
        </div>
      </div>
    </div>
  );
}
