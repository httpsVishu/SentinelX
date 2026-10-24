/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: { DEFAULT: '#E7EAE4', raised: '#F2F4EF', sunk: '#DADFD6' },
        ink: { DEFAULT: '#16203A', soft: '#4A5470', faint: '#7C8498' },
        carbon: { DEFAULT: '#2B4AA8', deep: '#1E3580', wash: '#D5DDF2' },
        stamp: { DEFAULT: '#B3263A', wash: '#F0D3D7' },
        tape: { DEFAULT: '#D08A1E', wash: '#F3E2BF' },
        ledger: { DEFAULT: '#2C7A59', wash: '#CFE5DA' },
        sev: {
          critical: '#B3263A',
          high: '#C45A1C',
          medium: '#C79A24',
          low: '#4D70B8',
          info: '#7C8498',
        },
      },
      fontFamily: {
        sans: ['Archivo', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        display: ['clamp(2.25rem, 5vw, 3.75rem)', { lineHeight: '1.02', letterSpacing: '-0.02em' }],
        title: ['1.75rem', { lineHeight: '1.1', letterSpacing: '-0.01em' }],
      },
      borderRadius: {
        DEFAULT: '2px',
        sm: '2px',
      },
    },
  },
  plugins: [],
}