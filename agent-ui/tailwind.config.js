/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#0f172a", muted: "#475569", subtle: "#94a3b8", tertiary: "#cbd5e1" },
        canvas: "#f1f5f9",
        surface: { DEFAULT: "#ffffff", hover: "#f8fafc", raised: "#ffffff", sunken: "#e2e8f0" },
        hairline: { DEFAULT: "#e2e8f0", soft: "#f1f5f9" },
        accent: { DEFAULT: "#2563eb", soft: "#eff6ff", strong: "#1d4ed8" },
        primary: { DEFAULT: "#1e3a5f", light: "#2d5a8e", dark: "#0f1d30" },
        call: { green: "#059669", "green-soft": "#ecfdf5", red: "#dc2626", "red-soft": "#fef2f2", amber: "#d97706", "amber-soft": "#fffbeb" },
      },
      fontFamily: { sans: ['"Inter"', "system-ui", "sans-serif"], mono: ['"JetBrains Mono"', "monospace"] },
      boxShadow: { modal: "0 20px 25px -5px rgb(0 0 0 / 0.12), 0 8px 10px -6px rgb(0 0 0 / 0.1)" },
      animation: {
        "pulse-glow": "pulse-glow 2s ease-in-out infinite",
        "pulse-dot": "pulse-dot 1.5s ease-in-out infinite",
        "pulse-call": "pulse-call 2s ease-in-out infinite",
        float: "float 3s ease-in-out infinite",
        shimmer: "shimmer 1.5s ease-in-out infinite",
        "slide-up": "slide-up 0.3s ease-out",
        "scale-in": "scale-in 0.2s ease-out",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-conic": "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
      },
    },
  },
  plugins: [],
};
