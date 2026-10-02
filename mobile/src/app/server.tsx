import { useState } from "react";
import { Switch, Text, View } from "react-native";

import { ErrorMessage, Field, FormScreen, PrimaryButton } from "../components/Form";
import { useConnection } from "../connection/ConnectionContext";
import { normalizeServerUrl } from "../connection/serverUrl";
import { verifyServer } from "../connection/verifyServer";

export default function ServerScreen() {
  const { connect } = useConnection();
  const [address, setAddress] = useState("");
  const [allowInsecure, setAllowInsecure] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function onConnect() {
    setError(null);
    const normalized = normalizeServerUrl(address, { allowInsecure });
    if ("error" in normalized) {
      setError(normalized.error);
      return;
    }
    setChecking(true);
    try {
      const verdict = await verifyServer(normalized.url);
      if (!verdict.ok) {
        setError(verdict.error);
        return;
      }
      await connect(normalized.url);
    } finally {
      setChecking(false);
    }
  }

  return (
    <FormScreen title="Connect to your server">
      <Text className="text-sm text-stone-600 dark:text-stone-400">
        Enter the address of your self-hosted ZeroBudget, the same one you open in a browser.
      </Text>
      <Field
        label="Server address"
        placeholder="budget.example.com"
        value={address}
        onChangeText={setAddress}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        textContentType="URL"
        returnKeyType="go"
        onSubmitEditing={() => void onConnect()}
      />
      <View className="flex-row items-center justify-between gap-3">
        <View className="flex-1 gap-1">
          <Text className="text-sm font-medium text-stone-700 dark:text-stone-300">Allow insecure local server</Text>
          <Text className="text-xs text-stone-500 dark:text-stone-400">
            Accepts http:// addresses. Your password and budget travel unencrypted, so only use this on a network you
            trust.
          </Text>
        </View>
        <Switch
          accessibilityLabel="Allow insecure local server"
          value={allowInsecure}
          onValueChange={setAllowInsecure}
        />
      </View>
      <ErrorMessage message={error} />
      <PrimaryButton label="Connect" busyLabel="Checking…" busy={checking} onPress={() => void onConnect()} />
    </FormScreen>
  );
}
