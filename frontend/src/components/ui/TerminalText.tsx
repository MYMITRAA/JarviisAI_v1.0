"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

interface TerminalTextProps {
  text: string;
  className?: string;
  speed?: number;
  prefix?: string;
}

export function TerminalText({ text, className, speed = 40, prefix = "> " }: TerminalTextProps) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    let i = 0;
    setDisplayed("");
    setDone(false);

    const interval = setInterval(() => {
      if (i < text.length) {
        setDisplayed(text.slice(0, i + 1));
        i++;
      } else {
        setDone(true);
        clearInterval(interval);
      }
    }, speed);

    return () => clearInterval(interval);
  }, [text, speed]);

  return (
    <div className={cn("font-mono text-sm", className)}>
      <span className="text-brand-accent opacity-60">{prefix}</span>
      <span>{displayed}</span>
      {!done && <span className="animate-pulse text-brand-accent">█</span>}
    </div>
  );
}
