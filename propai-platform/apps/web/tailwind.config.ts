import type { Config } from "tailwindcss";
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        primary: "#135bec",
        propai: {
          50:  "#f0f7ff",
          100: "#dbeeff",
          200: "#b3d8ff",
          300: "#7fbeff",
          400: "#4496f0",
          500: "#135bec",
          600: "#1557b0",
          700: "#124290",
          800: "#0f2e6a",
          900: "#081b40",
        },
        "background-light": "#f6f6f8",
        "background-dark": "#101622",
        "card-dark": "#1c222e",
        "card-light": "#ffffff",
        "surface-dark": "#1a1d23",
        "border-dark": "#2e3646",
        "border-light": "#e5e7eb",
      },
      fontFamily: {
        sans: ["Pretendard", "Inter", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "Pretendard", "sans-serif"],
        body: ["Noto Sans", "Pretendard", "Inter", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "0.25rem",
        lg: "0.5rem",
        xl: "0.75rem",
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
      boxShadow: {
        glow: "0 0 15px rgba(19, 91, 236, 0.3)",
        "glow-lg": "0 0 25px rgba(19, 91, 236, 0.5)",
        "glow-primary": "0 0 20px rgba(19, 91, 236, 0.4)",
      },
    }
  },
  plugins: []
};
export default config;
