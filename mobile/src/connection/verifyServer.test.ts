import { verifyServer } from "./verifyServer";

const SERVER = "https://budget.example.com";

function respondWith(status: number, body: unknown) {
  return jest.fn(async () => new Response(JSON.stringify(body), { status }));
}

describe("verifyServer", () => {
  it("accepts a server that identifies itself as ZeroBudget", async () => {
    const fetchMock = respondWith(200, { status: "ok", service: "zerobudget", version: "1.2.3" });
    globalThis.fetch = fetchMock;

    await expect(verifyServer(SERVER)).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(`${SERVER}/api/health`, expect.anything());
  });

  it("rejects a server that answers as something else", async () => {
    globalThis.fetch = respondWith(200, { status: "ok", service: "grafana" });

    await expect(verifyServer(SERVER)).resolves.toMatchObject({ ok: false, error: expect.stringMatching(/isn't ZeroBudget/) });
  });

  it("suggests updating a server that answers health checks without naming itself", async () => {
    globalThis.fetch = respondWith(200, { status: "ok" });

    await expect(verifyServer(SERVER)).resolves.toMatchObject({ ok: false, error: expect.stringMatching(/update/) });
  });

  it("rejects error responses and non-JSON bodies", async () => {
    globalThis.fetch = respondWith(404, { detail: "Not Found" });
    await expect(verifyServer(SERVER)).resolves.toMatchObject({ ok: false });

    globalThis.fetch = jest.fn(async () => new Response("<html>hi</html>", { status: 200 }));
    await expect(verifyServer(SERVER)).resolves.toMatchObject({ ok: false });
  });

  it("reports an unreachable server, mentioning self-signed certificates", async () => {
    globalThis.fetch = jest.fn(async () => {
      throw new TypeError("Network request failed");
    });

    await expect(verifyServer(SERVER)).resolves.toMatchObject({ ok: false, error: expect.stringMatching(/self-signed/) });
  });

  it("gives up on a server that never answers", async () => {
    // AbortSignal.timeout runs on timers Jest can't fake, so the abort is simulated.
    const fetchMock = jest.fn(async () => {
      throw new DOMException("The signal timed out.", "TimeoutError");
    });
    globalThis.fetch = fetchMock;

    await expect(verifyServer(SERVER)).resolves.toMatchObject({ ok: false });
    expect(fetchMock).toHaveBeenCalledWith(expect.any(String), { signal: expect.any(AbortSignal) });
  });
});
