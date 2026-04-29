import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/layout/Providers";
import { Toaster } from "sonner";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: {
    default: "JarviisAI — Test. Deploy. Heal. Autonomously.",
    template: "%s | JarviisAI",
  },
  description:
    "The world's first AI platform that autonomously tests your code, deploys it, and fixes production issues — so you never need a dedicated QA team or DevOps engineer.",
  keywords: ["AI testing", "autonomous QA", "AI deployment", "automated testing", "no-code testing"],
  authors: [{ name: "JarviisAI" }],
  creator: "JarviisAI",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://jarviis.ai",
    title: "JarviisAI — Test. Deploy. Heal. Autonomously.",
    description: "Autonomous AI testing and deployment platform",
    siteName: "JarviisAI",
  },
  twitter: {
    card: "summary_large_image",
    title: "JarviisAI — Test. Deploy. Heal. Autonomously.",
    description: "Autonomous AI testing and deployment platform",
    creator: "@jarviisai",
  },
  robots: { index: true, follow: true },
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"),
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans bg-brand-primary`}>
        <Providers>
          {children}
          <Toaster
            position="bottom-right"
            theme="dark"
            toastOptions={{
              style: {
                background: "#12122A",
                border: "1px solid #2A2A4E",
                color: "#F0F2FF",
              },
            }}
          />
        </Providers>
      </body>
    </html>
  );
}
