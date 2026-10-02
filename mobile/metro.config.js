// Expo's default config already handles the npm workspace (watch folders and
// node_modules lookup for @zerobudget/core), so only NativeWind is added here.
const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");

module.exports = withNativeWind(getDefaultConfig(__dirname), { input: "./global.css" });
