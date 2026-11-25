import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import { AppShell, PageHead } from "@/components/layout/AppShell";
import { Badge, Card, EmptyState, ErrorState, LoadingBlock } from "@/components/ui";
import { api } from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { caseStatusLabel, caseStatusTone, formatDate, routeLabel } from "@/lib/format";

export default function CasesPage() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState(""); // debounced search term sent to the API
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);
  const qc = useQueryClient();
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers, retry: 0 });
  const accounts = !!providers.data?.accounts;
  const saved = useQuery({ queryKey: ["saved-filters"], queryFn: api.savedFilters, retry: 0, enabled: accounts });
  const saveIt = useMutation({
    mutationFn: (name: string) => api.saveFilter(name, { ...(query ? { q: query } : {}), ...(status ? { status } : {}), ...(mine ? { mine: true } : {}) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["saved-filters"] }),
  });
  const dropIt = useMutation({ mutationFn: api.deleteFilter, onSuccess: () => qc.invalidateQueries({ queryKey: ["saved-filters"] }) });
  const download = useMutation({
    mutationFn: (format: "csv" | "xlsx") => api.exportList("cases", format, { ...(query ? { q: query } : {}), ...(status ? { status } : {}), ...(mine ? { assignee: "me" } : {}) }),
    onSuccess: (blob, format) => saveBlob(blob, `cases.${format}`),
  });
  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);
  const cases = useQuery({
    queryKey: ["cases", query, status, mine],
    queryFn: () => api.listCases({ q: query, status, ...(mine ? { assignee: "me" } : {}) }),
    placeholderData: (prev) => prev, // keep the current rows while the next page loads
  });

  return (
    <AppShell title="Screening cases">
      <PageHead
        title="Screening cases"
        description="Each case holds the company's evidence, its versioned data and every screening report."
        actions={
          <Link className="btn btn-primary" href="/cases/new">
            New case
          </Link>
        }
      />
      <Card>
        <div className="row" style={{ marginBottom: 14 }}>
          <input aria-label="Search by company name" placeholder="Search company…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 280 }} />
          <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 220 }}>
            <option value="">All statuses</option>
            {Object.entries(caseStatusLabel).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
          {accounts && (
            <label className="row">
              <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
              <span>Assigned to me</span>
            </label>
          )}
          <span className="row" style={{ marginLeft: "auto" }}>
            {accounts && (
              <button className="btn btn-sm btn-ghost" onClick={() => { const n = window.prompt("Name this search"); if (n?.trim()) saveIt.mutate(n.trim()); }}>Save search</button>
            )}
            <button className="btn btn-sm" onClick={() => download.mutate("csv")} disabled={download.isPending}>CSV</button>
            <button className="btn btn-sm" onClick={() => download.mutate("xlsx")} disabled={download.isPending}>Excel</button>
          </span>
        </div>
        {saved.data && saved.data.length > 0 && (
          <div className="row" style={{ marginBottom: 12 }} aria-label="Saved searches">
            {saved.data.map((f) => (
              <span key={f.id} className="row">
                <button className="btn btn-sm" onClick={() => { setQ(String(f.params.q ?? "")); setStatus(String(f.params.status ?? "")); setMine(!!f.params.mine); }}>{f.name}</button>
                <button className="btn btn-sm btn-ghost" aria-label={`Delete saved search ${f.name}`} onClick={() => dropIt.mutate(f.id)}>×</button>
              </span>
            ))}
          </div>
        )}
        {cases.isLoading && <LoadingBlock />}
        {cases.isError && <ErrorState error={cases.error} onRetry={() => cases.refetch()} />}
        {cases.data && cases.data.items.length === 0 && (
          <EmptyState title={q || status ? "No matching cases" : "No cases yet"} action={<Link className="btn" href="/cases/new">Create a case</Link>} />
        )}
        {cases.data && cases.data.items.length > 0 && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Route</th>
                  <th>Status</th>
                  <th className="num">Documents</th>
                  <th className="num">Open review</th>
                  <th className="num">Reports</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {cases.data.items.map((c) => (
                  <tr key={c.id} className="clickable" onClick={() => router.push(`/cases/${c.id}`)}>
                    <td>
                      <Link href={`/cases/${c.id}`} onClick={(e) => e.stopPropagation()}>
                        {c.company_name}
                      </Link>
                    </td>
                    <td className="subtle">{routeLabel[c.listing_route]}</td>
                    <td>
                      <Badge tone={caseStatusTone[c.status] ?? "neutral"}>{caseStatusLabel[c.status] ?? c.status}</Badge>
                    </td>
                    <td className="num">{c.document_count}</td>
                    <td className="num">{c.open_review_items || "—"}</td>
                    <td className="num">{c.report_count || "—"}</td>
                    <td className="subtle">{formatDate(c.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="subtle" style={{ marginTop: 8 }}>
              {cases.data.total} case(s)
            </p>
          </div>
        )}
      </Card>
    </AppShell>
  );
}
