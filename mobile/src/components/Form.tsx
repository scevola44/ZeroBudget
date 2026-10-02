import type { ReactNode } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

// Class strings are ported from frontend/src/auth/LoginPage.tsx so the two
// apps share one look.

export function FormScreen({ title, children }: { title: string; children: ReactNode }) {
  return (
    <SafeAreaView className="flex-1 bg-stone-100 dark:bg-stone-950">
      <KeyboardAvoidingView className="flex-1" behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerClassName="flex-grow justify-center px-4 py-8" keyboardShouldPersistTaps="handled">
          <View className="w-full max-w-sm self-center bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-2xl p-6 gap-4">
            <Text className="text-2xl font-semibold text-stone-900 dark:text-stone-100">{title}</Text>
            {children}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export function Field({ label, ...inputProps }: { label: string } & TextInputProps) {
  return (
    <View className="gap-1">
      <Text className="text-sm font-medium text-stone-700 dark:text-stone-300">{label}</Text>
      <TextInput
        accessibilityLabel={label}
        className="w-full border border-stone-300 dark:border-stone-600 rounded-lg px-3 py-2 text-base text-stone-900 dark:text-stone-100"
        placeholderTextColor="#a8a29e"
        {...inputProps}
      />
    </View>
  );
}

export function PrimaryButton({
  label,
  busyLabel,
  busy,
  onPress,
}: {
  label: string;
  busyLabel: string;
  busy: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ busy, disabled: busy }}
      disabled={busy}
      onPress={onPress}
      className="w-full flex-row items-center justify-center gap-2 bg-indigo-600 active:bg-indigo-700 disabled:bg-indigo-400 dark:bg-indigo-500 rounded-lg py-3"
    >
      {busy && <ActivityIndicator color="white" />}
      <Text className="text-white font-medium text-base">{busy ? busyLabel : label}</Text>
    </Pressable>
  );
}

export function TextButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} hitSlop={8}>
      <Text className="text-indigo-600 dark:text-indigo-400">{label}</Text>
    </Pressable>
  );
}

export function ErrorMessage({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <Text accessibilityRole="alert" className="text-sm text-red-600 dark:text-red-400">
      {message}
    </Text>
  );
}
