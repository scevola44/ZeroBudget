import { Linking, Text, View } from "react-native";

import { TextButton } from "../components/Form";
import { useConnection } from "../connection/ConnectionContext";

const SCHEME_PREFIX = /^https?:\/\//;

/** Which server the credentials go to, with a way back to onboarding. */
export function ServerNotice() {
  const { serverUrl, disconnect } = useConnection();
  if (!serverUrl) return null;
  const insecure = serverUrl.startsWith("http://");

  return (
    <View className="flex-row items-center justify-between gap-3 rounded-lg bg-stone-100 dark:bg-stone-800 px-3 py-2">
      <View className="flex-1">
        <Text className="text-xs text-stone-500 dark:text-stone-400">Server</Text>
        <Text className="text-sm text-stone-900 dark:text-stone-100" numberOfLines={1}>
          {serverUrl.replace(SCHEME_PREFIX, "")}
        </Text>
        {insecure && <Text className="text-xs text-amber-700 dark:text-amber-400">Not encrypted (http)</Text>}
      </View>
      <TextButton label="Change" onPress={() => void disconnect()} />
    </View>
  );
}

/** The server hosts its own Terms and Privacy pages; the app just links to them. */
export function LegalNotice() {
  const { serverUrl } = useConnection();
  if (!serverUrl) return null;

  return (
    <Text className="text-xs text-stone-500 text-center">
      By continuing you agree to the{" "}
      <Text className="text-indigo-600 dark:text-indigo-400" onPress={() => void Linking.openURL(`${serverUrl}/terms`)}>
        Terms of Service
      </Text>{" "}
      and{" "}
      <Text className="text-indigo-600 dark:text-indigo-400" onPress={() => void Linking.openURL(`${serverUrl}/privacy`)}>
        Privacy Policy
      </Text>
      .
    </Text>
  );
}
