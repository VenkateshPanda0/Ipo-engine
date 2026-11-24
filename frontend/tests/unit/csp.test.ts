import { describe, expect, it } from "vitest";
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { contentSecurityPolicy } = require("../../csp.js");

const directive = (csp: string, name: string): string[] =>
  (csp.split("; ").find((d) => d.startsWith(name + " ")) ?? "").split(" ").slice(1);

describe("content security policy", () => {
  const prod = contentSecurityPolicy({ apiBase: "http://localhost:8000", dev: false });

  it("allows scripts only from the app itself in production, and never eval", () => {
    expect(directive(prod, "script-src")).toEqual(["'self'"]);
    expect(prod).not.toContain("unsafe-eval");
    expect(prod).not.toMatch(/script-src[^;]*unsafe-inline/);
  });

  it("lets the app talk to its API origin and nothing else", () => {
    expect(directive(prod, "connect-src")).toEqual(["'self'", "http://localhost:8000"]);
    const other = contentSecurityPolicy({ apiBase: "https://api.example.com/v1/", dev: false });
    expect(directive(other, "connect-src")).toEqual(["'self'", "https://api.example.com"]);
  });

  it("shows page previews (blob URLs) and blocks plugins, framing and foreign forms", () => {
    expect(directive(prod, "img-src")).toEqual(["'self'", "blob:", "data:"]);
    expect(directive(prod, "object-src")).toEqual(["'none'"]);
    expect(directive(prod, "frame-ancestors")).toEqual(["'none'"]);
    expect(directive(prod, "form-action")).toEqual(["'self'"]);
    expect(directive(prod, "base-uri")).toEqual(["'self'"]);
  });

  it("loosens only what hot reload needs, and only in development", () => {
    const dev = contentSecurityPolicy({ apiBase: "http://localhost:8000", dev: true });
    expect(directive(dev, "script-src")).toEqual(["'self'", "'unsafe-eval'"]);
    expect(directive(dev, "connect-src")).toContain("ws:");
    expect(prod).not.toContain("ws:");
  });

  it("falls back to the default API address when the setting is not a URL", () => {
    const bad = contentSecurityPolicy({ apiBase: "not a url", dev: false });
    expect(directive(bad, "connect-src")).toEqual(["'self'", "http://localhost:8000"]);
  });
});

describe("zod under a strict policy", () => {
  it("is configured not to probe eval (a blocked probe is reported as a CSP violation)", async () => {
    const calls: string[] = [];
    const Original = globalThis.Function;
    globalThis.Function = new Proxy(Original, {
      construct(target, args) {
        calls.push(String(args[args.length - 1]));
        return Reflect.construct(target, args);
      },
    });
    try {
      const { z } = await import("@/lib/zod");
      const { Verdict } = await import("@/lib/schemas");
      expect(z.config().jitless).toBe(true);
      expect(Verdict.parse("pass")).toBe("pass");
      z.object({ a: z.string() }).parse({ a: "x" });
    } finally {
      globalThis.Function = Original;
    }
    expect(calls).toEqual([]);
  });
});
