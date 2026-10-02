import { Link } from "expo-router";
import { useState } from "react";
import { Text } from "react-native";

import { ApiError } from "@zerobudget/core";

import { useAuth } from "../auth/AuthContext";
import { LegalNotice, ServerNotice } from "../auth/ServerNotice";
import { ErrorMessage, Field, FormScreen, PrimaryButton } from "../components/Form";

// Mirrors the backend's RegisterRequest; checked here because its 422 has no
// human-readable message for the client to surface.
const MIN_PASSWORD_LENGTH = 8;

export default function RegisterScreen() {
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    setError(null);
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Use at least ${MIN_PASSWORD_LENGTH} characters for your password.`);
      return;
    }
    setSubmitting(true);
    try {
      await register(email.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <FormScreen title="Create your account">
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
        label={`Password (min. ${MIN_PASSWORD_LENGTH} chars)`}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="new-password"
        textContentType="newPassword"
        returnKeyType="go"
        onSubmitEditing={() => void onSubmit()}
      />
      <ErrorMessage message={error} />
      <PrimaryButton label="Create account" busyLabel="Creating…" busy={submitting} onPress={() => void onSubmit()} />
      <Text className="text-sm text-stone-600 dark:text-stone-400 text-center">
        Already have an account?{" "}
        <Link href="/login" replace className="text-indigo-600 dark:text-indigo-400">
          Sign in
        </Link>
      </Text>
      <LegalNotice />
    </FormScreen>
  );
}
