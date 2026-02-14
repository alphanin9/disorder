import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#f6f7f9",
        ink: "#141414",
        accent: "#0052cc",
        accentSoft: "#e6efff",
        danger: "#b42318",
        success: "#067647",
        warning: "#b54708",
      },
      boxShadow: {
        panel: "0 10px 30px rgba(12, 18, 28, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
