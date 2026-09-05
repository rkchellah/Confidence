/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          gold: "#D9FF5C",
          mint: "#D9FF5C",
          charcoal: "#242426",
          darkCard: "#35363B",
          slate: "rgba(36, 36, 38, 0.75)",
          bgLight: "#EBEFF5",
          borderLight: "rgba(36, 36, 38, 0.12)",
        },
      },
      fontFamily: {
        sans: ["Inter Display", "sans-serif"],
      },
      borderRadius: {
        "3xl": "24px",
        "4xl": "32px",
      },
    },
  },
  plugins: [],
};
