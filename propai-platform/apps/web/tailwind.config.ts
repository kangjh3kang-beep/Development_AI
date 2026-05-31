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
        propai: {
          50:  "#f0f7ff",
          100: "#dbeeff",
          200: "#b3d8ff",
          300: "#7fbeff",
          400: "#4496f0",
          500: "#1d6fd6",
          600: "#1557b0",
          700: "#124290",
          800: "#0f2e6a",
          900: "#081b40",
        }
      },
      fontFamily: {
        sans: ["Pretendard", "Inter", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
};
export default config;
