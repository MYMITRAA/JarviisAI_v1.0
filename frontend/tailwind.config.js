/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // ── JarviisAI Design Tokens ──────────────────────────
        brand: {
          primary:  "#0D0D1A",   // near-black navy
          accent:   "#6C63FF",   // electric violet
          cyan:     "#00D4FF",   // electric cyan
          teal:     "#00C9A7",   // teal
          gold:     "#FFB800",   // gold
          crimson:  "#FF2D55",   // vivid red
          neon:     "#39FF14",   // neon green
        },
        // ── Surface colors ───────────────────────────────────
        surface: {
          base:     "#0D0D1A",
          raised:   "#12122A",
          overlay:  "#1A1A3E",
          border:   "#2A2A4E",
          muted:    "#3A3A5C",
        },
        // ── Text ─────────────────────────────────────────────
        content: {
          primary:  "#F0F2FF",
          secondary:"#C8C8E0",
          muted:    "#7A7A9A",
          inverse:  "#0D0D1A",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      animation: {
        "fade-in":    "fadeIn 0.3s ease-in-out",
        "slide-up":   "slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "glow-pulse": "glowPulse 2s ease-in-out infinite",
        "float":      "float 3s ease-in-out infinite",
        "spin-slow":  "spin 3s linear infinite",
        "code-rain":  "codeRain 8s linear infinite",
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%":   { opacity: "0", transform: "translateY(20px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        glowPulse: {
          "0%, 100%": { boxShadow: "0 0 20px rgba(108, 99, 255, 0.3)" },
          "50%":      { boxShadow: "0 0 40px rgba(108, 99, 255, 0.6)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%":      { transform: "translateY(-10px)" },
        },
        codeRain: {
          "0%":   { transform: "translateY(-100%)", opacity: "0" },
          "10%":  { opacity: "1" },
          "90%":  { opacity: "1" },
          "100%": { transform: "translateY(100vh)", opacity: "0" },
        },
      },
      backgroundImage: {
        "gradient-radial":   "radial-gradient(var(--tw-gradient-stops))",
        "gradient-jarviis":  "linear-gradient(135deg, #6C63FF 0%, #00D4FF 100%)",
        "gradient-dark":     "linear-gradient(180deg, #0D0D1A 0%, #12122A 100%)",
      },
      boxShadow: {
        "glow-accent":  "0 0 20px rgba(108, 99, 255, 0.4)",
        "glow-cyan":    "0 0 20px rgba(0, 212, 255, 0.4)",
        "glow-crimson": "0 0 20px rgba(255, 45, 85, 0.4)",
        "card":         "0 4px 24px rgba(0, 0, 0, 0.4)",
        "card-hover":   "0 8px 40px rgba(108, 99, 255, 0.2)",
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
  ],
};
