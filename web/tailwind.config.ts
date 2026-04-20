import type { Config } from "tailwindcss";

const colorVar = (name: string) => `rgb(var(${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          base: colorVar("--bg-base"),
          surface: colorVar("--bg-surface"),
          elevated: colorVar("--bg-elevated"),
          subtle: colorVar("--bg-subtle"),
        },
        brand: {
          DEFAULT: colorVar("--brand"),
          hover: colorVar("--brand-hover"),
          muted: colorVar("--brand-muted"),
        },
        pass: {
          DEFAULT: colorVar("--pass"),
          bg: colorVar("--pass-bg"),
          border: colorVar("--pass-border"),
        },
        fail: {
          DEFAULT: colorVar("--fail"),
          bg: colorVar("--fail-bg"),
          border: colorVar("--fail-border"),
        },
        warn: {
          DEFAULT: colorVar("--warn"),
          bg: colorVar("--warn-bg"),
          border: colorVar("--warn-border"),
        },
        info: {
          DEFAULT: colorVar("--info"),
          bg: colorVar("--info-bg"),
          border: colorVar("--info-border"),
        },
        overlay: {
          DEFAULT: colorVar("--overlay"),
        },
        text: {
          primary: colorVar("--text-primary"),
          secondary: colorVar("--text-secondary"),
          muted: colorVar("--text-muted"),
          inverse: colorVar("--text-inverse"),
        },
        border: {
          DEFAULT: colorVar("--border"),
          subtle: colorVar("--border-subtle"),
          focus: colorVar("--border-focus"),
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
