/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['selector', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      screens: {
        nav: '860px',
      },
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
        line: 'var(--line)',
        fg: 'var(--fg)',
        muted: 'var(--muted)',
        accent: {
          DEFAULT: 'var(--accent)',
          fg: 'var(--accent-fg)',
          soft: 'var(--accent-soft)',
        },
        ok: { DEFAULT: 'var(--ok)', soft: 'var(--ok-soft)' },
        warn: { DEFAULT: 'var(--warn)', soft: 'var(--warn-soft)' },
        crit: { DEFAULT: 'var(--crit)', soft: 'var(--crit-soft)' },
        info: { DEFAULT: 'var(--info)', soft: 'var(--info-soft)' },
        note: 'var(--note)',
        ring: 'var(--accent)',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontSize: {
        'page-title': ['21px', { lineHeight: '1.3', fontWeight: '600' }],
        'section-title': ['15px', { lineHeight: '1.4', fontWeight: '600' }],
        'label-caps': ['12px', { lineHeight: '1.4', fontWeight: '600', letterSpacing: '0.06em' }],
        body: ['14px', { lineHeight: '1.5' }],
        small: ['12px', { lineHeight: '1.45' }],
      },
      borderRadius: {
        DEFAULT: '6px',
        md: '8px',
        lg: '10px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(16, 24, 40, 0.06), 0 1px 3px rgba(16, 24, 40, 0.1)',
        pop: '0 8px 24px rgba(16, 24, 40, 0.14)',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(2px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          from: { backgroundPosition: '200% 0' },
          to: { backgroundPosition: '-200% 0' },
        },
      },
      animation: {
        'fade-in': 'fade-in 140ms ease-out',
        shimmer: 'shimmer 1.4s linear infinite',
      },
    },
  },
  plugins: [],
};
