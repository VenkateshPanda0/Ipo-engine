import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Card, ErrorState, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, humanize } from "@/lib/format";

/** Read-only links to one report for people without an account. Reviewers and admins only. */
export function ShareLinks({ reportId }: { reportId: string }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: 0 });
  const allowed = me.data?.role === "reviewer" || me.data?.role === "admin";
  const list = useQuery({ queryKey: ["shares", reportId], queryFn: () => api.shares(reportId), retry: 0, enabled: allowed });
  const [days, setDays] = useState(7);
  const [link, setLink] = useState<string | null>(null);
  const create = useMutation({ mutationFn: () => api.createShare(reportId, days), onSuccess: (r) => { setLink(r.link); void qc.invalidateQueries({ queryKey: ["shares", reportId] }); } });
  const revoke = useMutation({ mutationFn: (id: string) => api.revokeShare(reportId, id), onSuccess: () => qc.invalidateQueries({ queryKey: ["shares", reportId] }) });
  if (!allowed) return null;
  return (
    <Card title="Share a read-only copy">
      <p className="subtle">Anyone with the link can read this report, without signing in, until it expires or you withdraw it.</p>
      <form className="row" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <select aria-label="Link lifetime" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          {[1, 7, 30, 90].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}
        </select>
        <button className="btn" type="submit" disabled={create.isPending}>Create link</button>
      </form>
      {create.isError && <ErrorState error={create.error} />}
      {link && (
        <div style={{ marginTop: 12 }}>
          <Notice tone="positive" title="Copy the link now. It cannot be shown again.">
            <code style={{ wordBreak: "break-all" }}>{link}</code>
            <div><button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => navigator.clipboard?.writeText(link)}>Copy</button></div>
          </Notice>
        </div>
      )}
      {list.data && list.data.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="data">
            <thead><tr><th>State</th><th>Expires</th><th>Views</th><th /></tr></thead>
            <tbody>
              {list.data.map((s) => (
                <tr key={s.id}>
                  <td>{s.state === "live" ? <Badge tone="positive">Live</Badge> : <Badge tone="neutral">{humanize(s.state)}</Badge>}</td>
                  <td>{formatDate(s.expires_at)}</td><td>{s.views}</td>
                  <td>{s.state === "live" && <button className="btn btn-sm btn-ghost" onClick={() => revoke.mutate(s.id)}>Withdraw</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
