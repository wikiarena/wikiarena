/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'wiki-blue': '#0645ad',
        'wiki-visited': '#0b0080',
        'wiki-red': '#ba0000',
      },
    },
  },
  plugins: [],
} 