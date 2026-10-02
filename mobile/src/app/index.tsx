import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ActivityIndicator, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { budgetApi, currentMonth, formatCents, monthLabel, useScopes } from "@zerobudget/core";

import { useAuth } from "../auth/AuthContext";
import { ErrorMessage, PrimaryButton, TextButton } from "../components/Form";
import { useConnection } from "../connection/ConnectionContext";

// Phase 1's home screen: proof of a real authenticated round-trip, and the
// first on-device exercise of core's Intl-based money/date formatting.
export default function HomeScreen() {
  const { status } = useAuth();
  return (
    <SafeAreaView className="flex-1 bg-amber-50 dark:bg-stone-950">
      <ScrollView contentContainerClassName="p-4 gap-4">
        {status === "unreachable" ? <ServerUnreachable /> : <ReadyToAssignSummary />}
      </ScrollView>
    </SafeAreaView>
  );
}

function ReadyToAssignSummary() {
  const { user, logout } = useAuth();
  const { scopeById } = useScopes();
  const month = currentMonth();
  const budget = useQuery({ queryKey: ["budget", month], queryFn: () => budgetApi.get(month) });

  return (
    <>
      <View className="gap-1">
        <Text className="text-2xl font-semibold text-stone-900 dark:text-stone-100">{monthLabel(month)}</Text>
        <Text className="text-sm text-stone-600 dark:text-stone-400">Signed in as {user?.email}</Text>
      </View>

      {budget.isPending && <ActivityIndicator />}
      <ErrorMessage message={budget.error ? budget.error.message : null} />
      {budget.data?.ready_to_assign.map((scopeTotal) => (
        <View
          key={scopeTotal.scope_id}
          className="rounded-2xl p-5 bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700"
        >
          <Text className="text-sm text-stone-600 dark:text-stone-400">
            Ready to Assign — {scopeById.get(scopeTotal.scope_id)?.name ?? "…"}
          </Text>
          <Text className="text-3xl font-semibold tabular-nums text-stone-900 dark:text-stone-100">
            {formatCents(scopeTotal.ready_to_assign_cents)}
          </Text>
        </View>
      ))}

      <TextButton label="Sign out" onPress={logout} />
    </>
  );
}

function ServerUnreachable() {
  const { retry, logout } = useAuth();
  const { serverUrl } = useConnection();
  const [retrying, setRetrying] = useState(false);

  async function onRetry() {
    setRetrying(true);
    try {
      await retry();
    } finally {
      setRetrying(false);
    }
  }

  return (
    <View className="gap-4 rounded-2xl p-5 bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700">
      <Text className="text-lg font-semibold text-stone-900 dark:text-stone-100">Can't reach your server</Text>
      <Text className="text-sm text-stone-600 dark:text-stone-400">
        {serverUrl} isn't answering. You're still signed in; check your connection and try again.
      </Text>
      <PrimaryButton label="Try again" busyLabel="Trying…" busy={retrying} onPress={() => void onRetry()} />
      <TextButton label="Sign out" onPress={logout} />
    </View>
  );
}
