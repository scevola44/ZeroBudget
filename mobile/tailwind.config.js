/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  presets: [require("nativewind/preset")],
  // Follows the OS theme, like the web app's `darkMode: "media"`.
  darkMode: "media",
  theme: {
    extend: {},
  },
  plugins: [],
};
