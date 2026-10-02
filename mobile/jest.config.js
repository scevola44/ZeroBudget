/** @type {import('jest').Config} */
module.exports = {
  preset: "jest-expo",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  // global.css only means something to NativeWind's Metro transform.
  moduleNameMapper: { "\\.css$": "<rootDir>/jest.emptyModule.js" },
};
