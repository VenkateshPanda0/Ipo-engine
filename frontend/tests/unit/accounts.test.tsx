import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Collaboration } from "@/components/case/Collaboration";
import { ShareLinks } from "@/components/report/ShareLinks";
import { api, resetCsrf } from "@/lib/api";
import { setApiKey } from "@/lib/auth";
import { safeNext } from "@/pages/login";

const wrap = (ui: ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

type Call = { url: string; method: string; headers: Record<string, string>; credentials?: string };
let calls: Call[] = [];

function mockFetch(routes: Record<string, unknown>) {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const call: Call = { url: path, method: (init?.method ?? "GET").toUpperCase(), headers: (init?.headers ?? {}) as Record<string, string>, credentials: init?.credentials };
      calls.push(call);
      const key = `${call.method} ${path}`;
      const hit = routes[key] ?? routes[path];
      if (typeof hit === "function") return (hit as (c: Call) => Response)(call);
      if (hit === undefined) return new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "nope" } }), { status: 404 });
      return new Response(JSON.stringify(hit), { status: 200 });
    }),
  );
}

beforeEach(() => {
  resetCsrf();
  setApiKey(null);
});
afterEach(() => vi.unstubAllGlobals());

describe("browser session requests", () => {
  it("send cookies, and a CSRF token on changes only", async () => {
    mockFetch({ "/api/v1/auth/csrf": { csrf_token: "tok-1" }, "POST /api/v1/auth/switch-org": { org_id: "o" }, "/api/v1/me": { user_id: "u", role: "admin", authenticated: true } });
    await api.me();
    expect(calls.map((c) => c.url)).toEqual(["/api/v1/me"]); // a read needs no token
    expect(calls[0]!.credentials).toBe("include");
    await api.switchOrg("o");
    const change = calls.find((c) => c.method === "POST")!;
    expect(change.headers["X-CSRF-Token"]).toBe("tok-1");
    expect(change.headers["Authorization"]).toBeUndefined();
  });

  it("fetch the token once and reuse it", async () => {
    mockFetch({ "/api/v1/auth/csrf": { csrf_token: "tok-1" }, "POST /api/v1/auth/switch-org": {} });
    await api.switchOrg("a");
    await api.switchOrg("b");
    expect(calls.filter((c) => c.url === "/api/v1/auth/csrf")).toHaveLength(1);
  });

  it("refresh a stale token once after a 403 and retry", async () => {
    let n = 0;
    mockFetch({
      "/api/v1/auth/csrf": () => new Response(JSON.stringify({ csrf_token: `tok-${++n}` }), { status: 200 }),
      "POST /api/v1/auth/switch-org": (c: Call) =>
        c.headers["X-CSRF-Token"] === "tok-2" ? new Response("{}", { status: 200 }) : new Response(JSON.stringify({ error: { code: "HTTP_403", message: "CSRF token missing or wrong." } }), { status: 403 }),
    });
    await expect(api.switchOrg("a")).resolves.toBeUndefined();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(2);
  });

  it("do not loop on a genuine 403", async () => {
    mockFetch({
      "/api/v1/auth/csrf": { csrf_token: "tok" },
      "POST /api/v1/auth/switch-org": () => new Response(JSON.stringify({ error: { code: "FORBIDDEN", message: "no" } }), { status: 403 }),
    });
    await expect(api.switchOrg("a")).rejects.toThrow("no");
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(2); // one retry, then stop
  });
});

describe("token requests", () => {
  it("use the Authorization header and never ask for a CSRF token", async () => {
    setApiKey("ipo_secret");
    mockFetch({ "POST /api/v1/cases/1/comments": { id: "c" } });
    await api.addComment("1", "hi");
    expect(calls).toHaveLength(1);
    expect(calls[0]!.headers["Authorization"]).toBe("Bearer ipo_secret");
    expect(calls[0]!.headers["X-CSRF-Token"]).toBeUndefined();
  });
});

describe("safeNext", () => {
  it("keeps paths on this site and drops everything else", () => {
    expect(safeNext("/cases?x=1")).toBe("/cases?x=1");
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)", undefined, 5]) expect(safeNext(bad)).toBe("/");
  });
});

describe("Collaboration", () => {
  const base = {
    "/api/v1/auth/providers": { accounts: true, google: false, signup: "invite" },
    "/api/v1/org/members": [{ user_id: "u1", email: "ann@x.example", name: null, role: "admin", is_owner: true, status: "active" }],
    "/api/v1/cases/c1/comments": [{ id: "k1", author_id: "u1", author: "ann@x.example", body: "Looks odd", created_at: "2026-11-25T10:00:00Z" }],
  };

  it("shows nothing when accounts are off", async () => {
    mockFetch({ "/api/v1/auth/providers": { accounts: false, google: false, signup: "invite" }, "/api/v1/me": { user_id: "local-user", role: "admin", authenticated: false } });
    const { container } = wrap(<Collaboration caseId="c1" assigneeId={null} companyName="Acme" />);
    await waitFor(() => expect(calls.some((c) => c.url === "/api/v1/auth/providers")).toBe(true));
    expect(container).toBeEmptyDOMElement();
  });

  it("lists comments, lets a viewer read but not write", async () => {
    mockFetch({ ...base, "/api/v1/me": { user_id: "u9", role: "viewer", authenticated: true } });
    wrap(<Collaboration caseId="c1" assigneeId={null} companyName="Acme" />);
    expect(await screen.findByText("Looks odd")).toBeInTheDocument();
    expect(screen.queryByLabelText("Add a comment")).toBeNull();
    expect(screen.queryByText(/Erase this case/)).toBeNull();
  });

  it("makes an admin type the exact name before an erase can be sent", async () => {
    mockFetch({ ...base, "/api/v1/me": { user_id: "u1", role: "admin", authenticated: true } });
    wrap(<Collaboration caseId="c1" assigneeId="u1" companyName="Acme Ltd" />);
    fireEvent.click(await screen.findByText(/Erase this case permanently/));
    const button = screen.getByRole("button", { name: "Erase" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Confirm company name"), { target: { value: "Acme" } });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Confirm company name"), { target: { value: "Acme Ltd" } });
    expect(button).toBeEnabled();
  });
});

describe("ShareLinks", () => {
  it("is hidden from analysts and viewers", async () => {
    mockFetch({ "/api/v1/me": { user_id: "u", role: "analyst", authenticated: true } });
    const { container } = wrap(<ShareLinks reportId="r1" />);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a new link once and lists live links", async () => {
    mockFetch({
      "/api/v1/me": { user_id: "u", role: "reviewer", authenticated: true },
      "/api/v1/reports/r1/shares": [{ id: "s1", state: "live", expires_at: "2026-12-01T00:00:00Z", views: 3, created_by: "u" }],
      "POST /api/v1/reports/r1/shares": { link: "http://app/shared/SECRET", id: "s2" },
      "/api/v1/auth/csrf": { csrf_token: "t" },
    });
    wrap(<ShareLinks reportId="r1" />);
    fireEvent.click(await screen.findByText("Create link"));
    expect(await screen.findByText("http://app/shared/SECRET")).toBeInTheDocument();
    expect(await screen.findByText("Live")).toBeInTheDocument();
  });
});
