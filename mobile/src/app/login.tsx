import { Link } from "expo-router";
import { useState } from "react";
import { Text } from "react-native";

import { ApiError } from "@zerobudget/core";

import { useAuth } from "../auth/AuthContext";
import { LegalNotice, ServerNotice } from "../auth/ServerNotice";
import { ErrorMessage, Field, FormScreen, PrimaryButton } from "../components/Form";

export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <FormScreen title="Sign in to ZeroBudget">
      <ServerNotice />
      <Field
        label="Email"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        keyboardType="email-address"
        textContentType="username"
      />
      <Field
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="current-password"
        textContentType="password"
        returnKeyType="go"
        onSubmitEditing={() => void onSubmit()}
      />
      <ErrorMessage message={error} />
      <PrimaryButton label="Sign in" busyLabel="Signing in…" busy={submitting} onPress={() => void onSubmit()} />
      <Text className="text-sm text-stone-600 dark:text-stone-400 text-center">
        No account yet?{" "}
        <Link href="/register" replace className="text-indigo-600 dark:text-indigo-400">
          Create one
        </Link>
      </Text>
      <LegalNotice />
    </FormScreen>
  );
}
