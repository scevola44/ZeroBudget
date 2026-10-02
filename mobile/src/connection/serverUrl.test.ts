import { normalizeServerUrl } from "./serverUrl";

const SECURE_ONLY = { allowInsecure: false };
const INSECURE_ALLOWED = { allowInsecure: true };

describe("normalizeServerUrl", () => {
  it("assumes HTTPS for a bare host", () => {
    expect(normalizeServerUrl("budget.example.com", SECURE_ONLY)).toEqual({ url: "https://budget.example.com" });
  });

  it("trims whitespace, trailing slashes and a pasted /api suffix", () => {
    expect(normalizeServerUrl("  https://budget.example.com/api/  ", SECURE_ONLY)).toEqual({
      url: "https://budget.example.com",
    });
  });

  it("keeps a port and a reverse-proxy sub-path", () => {
    expect(normalizeServerUrl("https://home.example.com:8443/zerobudget/", SECURE_ONLY)).toEqual({
      url: "https://home.example.com:8443/zerobudget",
    });
  });

  it("rejects http unless insecure servers are allowed", () => {
    expect(normalizeServerUrl("http://192.168.1.20:8000", SECURE_ONLY)).toHaveProperty("error");
    expect(normalizeServerUrl("http://192.168.1.20:8000", INSECURE_ALLOWED)).toEqual({
      url: "http://192.168.1.20:8000",
    });
  });

  it("never downgrades a bare host to http, even when insecure servers are allowed", () => {
    expect(normalizeServerUrl("192.168.1.20:8000", INSECURE_ALLOWED)).toEqual({ url: "https://192.168.1.20:8000" });
  });

  it("rejects empty input, other schemes and junk", () => {
    expect(normalizeServerUrl("   ", SECURE_ONLY)).toHaveProperty("error");
    expect(normalizeServerUrl("ftp://budget.example.com", SECURE_ONLY)).toHaveProperty("error");
    expect(normalizeServerUrl("https://", SECURE_ONLY)).toHaveProperty("error");
    expect(normalizeServerUrl("not a url", SECURE_ONLY)).toHaveProperty("error");
  });
});
