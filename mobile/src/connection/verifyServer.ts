import type { HealthResponse } from "@zerobudget/core";

export type VerifyServerResult = { ok: true } | { ok: false; error: string };

const HEALTH_PATH = "/api/health";
const ZEROBUDGET_SERVICE_ID: HealthResponse["service"] = "zerobudget";
// Long enough for a home server waking from idle, short enough not to look hung.
const VERIFY_TIMEOUT_MS = 10_000;

// Native fetch reports DNS failures, refused connections and untrusted
// certificates as the same opaque network error, so one message has to cover them.
const UNREACHABLE =
  "Couldn't reach that server. Check the address and that this device is on the right network. " +
  "If it uses a self-signed certificate, trust that certificate in your device settings first.";
const NOT_ZEROBUDGET = "A server answered, but it isn't ZeroBudget. Check the address.";
// ZeroBudget servers from before the health check named themselves look like this.
const POSSIBLY_OUTDATED =
  "A server answered but didn't identify itself. If it is ZeroBudget, update it to a newer version first.";

/** Confirms `baseUrl` (already normalized) is a reachable ZeroBudget instance. */
export async function verifyServer(baseUrl: string): Promise<VerifyServerResult> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${HEALTH_PATH}`, { signal: AbortSignal.timeout(VERIFY_TIMEOUT_MS) });
  } catch {
    return { ok: false, error: UNREACHABLE };
  }
  if (!response.ok) return { ok: false, error: NOT_ZEROBUDGET };

  try {
    const body = (await response.json()) as Partial<HealthResponse>;
    if (body.service === ZEROBUDGET_SERVICE_ID) return { ok: true };
    if (body.status === "ok" && body.service === undefined) return { ok: false, error: POSSIBLY_OUTDATED };
    return { ok: false, error: NOT_ZEROBUDGET };
  } catch {
    return { ok: false, error: NOT_ZEROBUDGET };
  }
}
