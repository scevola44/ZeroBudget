import type { ExpoConfig } from "expo/config";

// The web app's page background (bg-stone-100 / dark:bg-stone-950).
const SPLASH_BACKGROUND_LIGHT = "#f5f5f4";
const SPLASH_BACKGROUND_DARK = "#0c0a09";

// Placeholder until App Store Connect / Play Console registration (MOBILE_ROADMAP.md
// Phase 7); changing it after a store listing exists means a new app record.
const APP_IDENTIFIER = "io.github.scevola44.zerobudget";

const config: ExpoConfig = {
  name: "ZeroBudget",
  slug: "zerobudget",
  scheme: "zerobudget",
  version: "0.0.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "automatic",
  ios: {
    bundleIdentifier: APP_IDENTIFIER,
    supportsTablet: true,
    infoPlist: {
      // Self-hosted instances on a home LAN often have no TLS at all. The app
      // only accepts http:// after the user flips the clearly-labelled
      // "insecure local server" switch, but ATS is a build-time setting, so
      // the binary itself must allow cleartext. Revisit before any public
      // App Store submission: review asks for a justification.
      NSAppTransportSecurity: { NSAllowsArbitraryLoads: true },
    },
  },
  android: {
    package: APP_IDENTIFIER,
    adaptiveIcon: {
      backgroundColor: "#E6F4FE",
      foregroundImage: "./assets/android-icon-foreground.png",
      backgroundImage: "./assets/android-icon-background.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
    predictiveBackGestureEnabled: false,
  },
  plugins: [
    "expo-router",
    "expo-secure-store",
    [
      "expo-splash-screen",
      {
        image: "./assets/splash-icon.png",
        imageWidth: 200,
        resizeMode: "contain",
        backgroundColor: SPLASH_BACKGROUND_LIGHT,
        dark: { backgroundColor: SPLASH_BACKGROUND_DARK },
      },
    ],
    // Same reason as the iOS ATS exception above.
    ["expo-build-properties", { android: { usesCleartextTraffic: true } }],
  ],
};

export default config;
