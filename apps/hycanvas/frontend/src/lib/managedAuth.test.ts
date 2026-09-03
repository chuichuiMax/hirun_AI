import { describe, expect, it } from "vitest";
import { normalizeManagedLoopbackURL } from "./managedAuth";

describe("normalizeManagedLoopbackURL", () => {
  it("does not add a trailing slash to a configured origin", () => {
    expect(normalizeManagedLoopbackURL("http://127.0.0.1:5173", "localhost")).toBe(
      "http://localhost:5173",
    );
  });

  it("uses the current loopback hostname without changing the configured port", () => {
    expect(normalizeManagedLoopbackURL("http://127.0.0.1:5173/hycanvas", "localhost")).toBe(
      "http://localhost:5173/hycanvas",
    );
  });

  it("rewrites loopback ContentSwarm URLs onto the current LAN hostname", () => {
    expect(normalizeManagedLoopbackURL("http://127.0.0.1:5173", "10.80.18.218")).toBe(
      "http://10.80.18.218:5173",
    );
  });

  it("does not rewrite non-loopback hosts", () => {
    expect(normalizeManagedLoopbackURL("https://content.example/hycanvas", "localhost")).toBe(
      "https://content.example/hycanvas",
    );
  });
});
