import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import { useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui";

const icon = (d: string) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
);

const NAV = [
  { href: "/", label: "Dashboard", icon: icon("M3 12 12 3l9 9M5 10v10h5v-6h4v6h5V10") },
  { href: "/cases", label: "Screening cases", icon: icon("M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z") },
  { href: "/review", label: "Review workspace", icon: icon("M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h9") },
  { href: "/reports", label: "Reports", icon: icon("M7 3h8l4 4v14H7zM15 3v4h4M10 12h6M10 16h6") },
  { href: "/rules", label: "Rule explorer", icon: icon("M4 6h16M4 12h10M4 18h16") },
  { href: "/settings", label: "Settings & health", icon: icon("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12l2-1-2-4-2 .5-1.5-1.2.3-2.1-4-.2-.6 2-1.9.7L7 5 4.5 8l1.4 1.5L5 12l-2 1 2 4 2-.5 1.5 1.2-.3 2.1 4 .2.6-2 1.9-.7L17 19l2.5-3-1.4-1.5z") },
];

export function AppShell({ title, children }: { title: string; children: ReactNode }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 60_000, retry: 0 });
  // The badge only needs a count: reuse the (cached) dashboard aggregate rather than
  // downloading every open review item with its candidates and history.
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, retry: 0 });
  const openCount = dash.data?.open_review_items ?? 0;
  const active = (href: string) => (href === "/" ? router.pathname === "/" : router.pathname.startsWith(href));

  return (
    <div className="shell">
      <Head>
        <title>{`${title} · IPO Engine`}</title>
      </Head>
      <a href="#main" className="sr-only">
        Skip to content
      </a>
      <aside className="sidebar" data-open={open} aria-label="Primary">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 4h10l4 4v12H5zM14 4v5h5M8.5 15.5l2 2 4-4.5" />
            </svg>
          </span>
          <span className="brand-text">
            <strong>IPO Engine</strong>
            <span>Offer documents, read and screened</span>
          </span>
        </div>
        <nav className="nav" onClick={() => setOpen(false)}>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} aria-current={active(n.href) ? "page" : undefined}>
              {n.icon}
              <span>{n.label}</span>
              {n.href === "/review" && openCount > 0 && <Badge tone="attention" plain>{openCount}</Badge>}
            </Link>
          ))}
        </nav>
        <div className="sidebar-foot">
          Decision support only. Not legal advice.
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="row">
            <button className="btn btn-sm mobile-nav-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="Toggle navigation">
              ☰
            </button>
            <span className="muted">{title}</span>
          </div>
          <div className="row">
            {health.isError ? (
              <Badge tone="negative">API unreachable</Badge>
            ) : health.data ? (
              <>
                <Badge tone="info" plain title="Active ruleset version">
                  Ruleset {health.data.ruleset_version}
                </Badge>
                <Badge tone={health.data.database ? "positive" : "negative"}>{health.data.database ? "Database OK" : "Database error"}</Badge>
              </>
            ) : null}
          </div>
        </header>
        <main id="main" className="content">
          {children}
        </main>
      </div>
    </div>
  );
}

export function PageHead({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}
