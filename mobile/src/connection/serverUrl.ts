export type ServerUrlResult = { url: string } | { error: string };

const HTTPS = "https:";
const HTTP = "http:";
const HAS_SCHEME = /^[a-z][a-z0-9+.-]*:\/\//i;
// The client appends `/api/...` itself, so a pasted API URL would double it.
const TRAILING_API_SEGMENT = /\/api\/?$/i;

/**
 * Turns what someone typed into the base URL the API client is configured
 * with: an origin plus an optional path prefix (for reverse proxies that
 * mount ZeroBudget under a sub-path), with no trailing slash.
 */
export function normalizeServerUrl(input: string, { allowInsecure }: { allowInsecure: boolean }): ServerUrlResult {
  const trimmed = input.trim();
  if (!trimmed) return { error: "Enter your ZeroBudget server's address." };

  // People usually type a bare host; HTTPS is the only safe guess.
  const withScheme = HAS_SCHEME.test(trimmed) ? trimmed : `https://${trimmed}`;

  let parsed: URL;
  try {
    parsed = new URL(withScheme);
  } catch {
    return { error: "That doesn't look like a web address." };
  }

  if (parsed.protocol !== HTTPS && parsed.protocol !== HTTP) {
    return { error: "The address must start with https://" };
  }
  if (parsed.protocol === HTTP && !allowInsecure) {
    return {
      error: "This server isn't using HTTPS. Turn on \"Allow insecure local server\" only if you trust your network.",
    };
  }
  if (!parsed.hostname) return { error: "That doesn't look like a web address." };

  const path = parsed.pathname.replace(TRAILING_API_SEGMENT, "").replace(/\/+$/, "");
  return { url: `${parsed.protocol}//${parsed.host}${path}` };
}
