import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Card, ErrorState, LoadingBlock, Notice } from "@/components/ui";
import { api, type ReaderItem } from "@/lib/api";

/** Rupees (as a decimal string) in ₹ crore with Indian digit grouping. */
export function crore(rupees: string): string {
  const n = Number(rupees) / 1e7;
  return Number.isFinite(n) ? n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
}

const kindLabel: Record<string, string> = {
  flag: "Flag",
  hidden_text: "Hidden text",
  related_party: "Related party",
  conflict: "Withheld",
  unchecked: "Not checked",
};
const kindTone: Record<string, "negative" | "caution" | "neutral"> = {
  flag: "negative",
  hidden_text: "negative",
  related_party: "negative",
  conflict: "caution",
  unchecked: "neutral",
};

function PageButton({ page, canPreview, onOpen }: { page: number; canPreview: boolean; onOpen: (page: number) => void }) {
  return canPreview ? (
    <button className="btn btn-sm btn-ghost" onClick={() => onOpen(page)}>p.{page}</button>
  ) : (
    <span className="subtle">p.{page}</span>
  );
}

function Item({ item, canPreview, onOpen }: { item: ReaderItem; canPreview: boolean; onOpen: (page: number) => void }) {
  return (
    <li style={{ margin: "10px 0" }}>
      <Badge tone={kindTone[item.kind] ?? "neutral"}>{kindLabel[item.kind] ?? item.kind}</Badge> {item.text}{" "}
      {item.page != null && <PageButton page={item.page} canPreview={canPreview} onOpen={onOpen} />}
      {item.section && <span className="subtle"> ({item.section})</span>}
      {item.evidence.length > 0 && (
        <ul className="tight subtle">
          {item.evidence.map(([page, text], i) => (
            <li key={i}>
              <span className="mono">{text}</span> <PageButton page={page} canPreview={canPreview} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * The reader's brief for a document: what to read first, with the page for every item.
 * It is a second, broader reading than the eligibility fields and never changes case data.
 */
export function ReaderBrief({ documentId, canPreview, onOpenPage }: { documentId: string; canPreview: boolean; onOpenPage: (page: number) => void }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["reader", documentId],
    queryFn: () => api.readerBrief(documentId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 3000 : false),
  });
  const start = useMutation({
    mutationFn: () => api.startReader(documentId),
    onSuccess: (data) => qc.setQueryData(["reader", documentId], data),
  });

  if (q.isLoading) return <LoadingBlock rows={4} />;
  if (q.isError || !q.data) return <ErrorState error={q.error} />;
  const { status, brief, error } = q.data;

  if (status !== "ready" || !brief)
    return (
      <Card title="Reader brief">
        <p className="muted">
          A broader reading of the whole document: issue size, annual figures, red flags, large related-party rows and
          figures the document&apos;s own tables disagree on, each with its page. A long filing takes a few minutes.
        </p>
        {status === "failed" && <Notice tone="negative" title="The reader failed">{error}</Notice>}
        {start.isError && <ErrorState error={start.error} />}
        {status === "running" ? (
          <p className="subtle" role="status">Reading the document…</p>
        ) : (
          <button className="btn btn-primary" onClick={() => start.mutate()} disabled={start.isPending || !canPreview}>
            {status === "failed" ? "Try again" : "Read the document"}
          </button>
        )}
        {!canPreview && <p className="subtle">The stored file has been deleted, so it cannot be read.</p>}
      </Card>
    );

  const [decisive, applicable] = brief.rules_checked;
  const [verified, total] = brief.numbers_verified;
  return (
    <div className="stack">
      <Notice tone="caution">Not investment advice. Automated reading of the document; check every figure on its page.</Notice>
      <Card title="Read first">
        {brief.read_first.length === 0 ? (
          <p>
            Nothing flagged and nothing withheld. That is <strong>not</strong> a clean bill of health: only {decisive} of{" "}
            {applicable} applicable rules could be evaluated.
          </p>
        ) : (
          <ol style={{ paddingLeft: 20, margin: 0 }}>
            {brief.read_first.map((item, i) => <Item key={i} item={item} canPreview={canPreview} onOpen={onOpenPage} />)}
          </ol>
        )}
      </Card>
      <div className="grid grid-2">
        <Card title="The issue (₹ crore)">
          {brief.issue.length === 0 ? (
            <p className="muted">No issue size is stated in a form that could be read (placeholders such as [●] are not read as figures).</p>
          ) : (
            <table className="data">
              <tbody>
                {brief.issue.map(([label, value, page]) => (
                  <tr key={label}>
                    <th>{label}</th>
                    <td className="num">{crore(value)}</td>
                    <td className="num"><PageButton page={page} canPreview={canPreview} onOpen={onOpenPage} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="Financials (₹ crore)">
          {brief.metrics.length === 0 ? (
            <p className="muted">No annual figures could be read with enough confidence.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <tbody>
                  {brief.metrics.map((m) => (
                    <tr key={m.label}>
                      <th>{m.label}</th>
                      {m.cells.map(([fy, value, page]) => (
                        <td key={fy} className="num">
                          <span className="subtle">{fy}</span> {crore(value)}{" "}
                          <PageButton page={page} canPreview={canPreview} onOpen={onOpenPage} />
                        </td>
                      ))}
                      <td className="num">{m.growth_pct != null ? `${Number(m.growth_pct) > 0 ? "+" : ""}${m.growth_pct}%` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      <Card title="How far to trust this">
        <p>
          {decisive} of {applicable} applicable rules could be evaluated. {verified} of {total} extracted numbers were found
          again on their cited page. A figure the document&apos;s tables disagreed on is listed above, not shown.
        </p>
        {brief.notes.map((n, i) => <p key={i} className="subtle">{n}</p>)}
        <p className="subtle">{brief.pages} pages read · {brief.sections.length} sections mapped · reader {q.data.reader_version}</p>
      </Card>
    </div>
  );
}
