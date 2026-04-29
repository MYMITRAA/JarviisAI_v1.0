import type { ReactNode } from "react";

// Marketing pages use a plain layout (no app sidebar/topnav)
export default function MarketingLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
