import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { SCOPES_QUERY_KEY, scopesApi } from "../api/scopes";
import type { Scope } from "../api/types";

/**
 * The user's budget pools, ordered as they chose.
 *
 * Almost every page needs a scope's name or colour, and none of them carry it
 * in their own payload — responses reference scopes by id only, so that a
 * rename never has to invalidate anything else.
 */
export function useScopes() {
  const query = useQuery({ queryKey: SCOPES_QUERY_KEY, queryFn: scopesApi.list });
  const scopes = useMemo<Scope[]>(() => query.data ?? [], [query.data]);
  const scopeById = useMemo(
    () => new Map(scopes.map((scope) => [scope.id, scope])),
    [scopes],
  );

  return {
    scopes,
    scopeById,
    // What a new account, group or bank link starts on. Null only while the
    // query is in flight — a user always has at least one scope.
    defaultScopeId: scopes[0]?.id ?? null,
    isLoading: query.isLoading,
  };
}
