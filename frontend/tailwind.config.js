/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Instrument Serif"', 'Georgia', 'serif'],
        sans: ['Geist', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"Geist Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        // Remap slate to warm neutrals (dark values → light equivalents for new light theme)
        slate: {
          50:  'var(--ink)',
          100: 'var(--ink)',
          200: 'var(--ink)',
          300: 'var(--ink-2)',
          400: 'var(--muted)',
          500: 'var(--muted)',
          600: 'var(--hairline-2)',
          700: 'var(--hairline)',
          800: 'var(--bg-2)',
          900: 'var(--card)',
          950: 'var(--bg)',
        },
        // Brand → copper accent
        brand: {
          50:  'oklch(0.97 0.004 48)',
          100: 'oklch(0.94 0.010 48)',
          200: 'oklch(0.88 0.030 48)',
          300: 'oklch(0.80 0.070 48)',
          400: 'oklch(0.72 0.110 48)',
          500: 'var(--accent)',
          600: 'var(--accent)',
          700: 'oklch(0.52 0.130 48)',
          800: 'oklch(0.42 0.120 48)',
          900: 'oklch(0.32 0.100 48)',
        },
        // Semantic tone mapping for existing pages
        emerald: {
          400: 'var(--positive)',
          500: 'var(--positive)',
        },
        red: {
          400: 'var(--danger)',
          500: 'var(--danger)',
        },
        amber: {
          300: 'var(--warn)',
          400: 'var(--warn)',
          500: 'var(--warn)',
        },
      },
    },
  },
  plugins: [],
}
