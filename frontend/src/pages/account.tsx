import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppShell, PageHead } from "@/components/layout/AppShell";
import { Badge, Card, EmptyState, ErrorState, LoadingBlock, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { formatDate, humanize } from "@/lib/format";

export default function AccountPage() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: 0 });
  const tokens = useQuery({ queryKey: ["tokens"], queryFn: api.tokens, retry: 0 });
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: api.sessions, retry: 0 });
  const [name, setName] = useState("");
  const [days, setDays] = useState(90);
  const [fresh, setFresh] = useState<string | null>(null);
  const create = useMutation({ mutationFn: () => api.createToken(name.trim(), days), onSuccess: (r) => { setFresh(r.token); setName(""); void qc.invalidateQueries({ queryKey: ["tokens"] }); } });
  const revoke = useMutation({ mutationFn: api.revokeToken, onSuccess: () => qc.invalidateQueries({ queryKey: ["tokens"] }) });
  const kill = useMutation({ mutationFn: api.revokeSession, onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }) });
  const killOthers = useMutation({ mutationFn: api.revokeOtherSessions, onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }) });
  const exportMine = useMutation({ mutationFn: api.exportMine, onSuccess: (d) => saveBlob(new Blob([JSON.stringify(d, null, 2)], { type: "application/json" }), "my-data.json") });

  return (
    <AppShell title="My account">
      <PageHead title="My account" description={me.data ? <>Signed in as <strong>{me.data.user_id}</strong> ({humanize(me.data.role)}).</> : undefined} />
      <div className="stack">
        <Card title="Personal API tokens">
          <p className="subtle">Use a token to call the API from scripts: <code>Authorization: Bearer ipo_…</code>. A token never has more rights than you do.</p>
          <form className="row" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <input required placeholder="What is it for? e.g. nightly export" aria-label="Token name" value={name} onChange={(e) => setName(e.target.value)} style={{ maxWidth: 300 }} />
            <select aria-label="Lifetime" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[30, 90, 365].map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
            <button className="btn btn-primary" type="submit" disabled={create.isPending}>Create token</button>
          </form>
          {create.isError && <ErrorState error={create.error} />}
          {fresh && (
            <div style={{ marginTop: 12 }}>
              <Notice tone="positive" title="Copy it now. It cannot be shown again.">
                <code style={{ wordBreak: "break-all" }}>{fresh}</code>
                <div><button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => navigator.clipboard?.writeText(fresh)}>Copy</button></div>
              </Notice>
            </div>
          )}
          {tokens.isLoading && <LoadingBlock rows={2} />}
          {tokens.isError && <ErrorState error={tokens.error} />}
          {tokens.data && tokens.data.length === 0 && <EmptyState title="No tokens" />}
          {tokens.data && tokens.data.length > 0 && (
            <div className="table-wrap" style={{ marginTop: 12 }}>
              <table className="data">
                <thead><tr><th>Name</th><th>Starts with</th><th>Role</th><th>Expires</th><th>Last used</th><th /></tr></thead>
                <tbody>
                  {tokens.data.map((t) => (
                    <tr key={t.id}>
                      <td>{t.name}</td><td><code>{t.prefix}…</code></td><td>{humanize(t.role)}</td>
                      <td>{t.expires_at ? formatDate(t.expires_at) : "never"}</td><td>{t.last_used_at ? formatDate(t.last_used_at) : "—"}</td>
                      <td>{t.revoked_at ? <Badge tone="negative">Revoked</Badge> : <button className="btn btn-sm btn-ghost" onClick={() => revoke.mutate(t.id)}>Revoke</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Where you are signed in" actions={<button className="btn btn-sm" onClick={() => killOthers.mutate()}>Sign out everywhere else</button>}>
          {sessions.isError && <p className="subtle">Browser sessions are only listed when you signed in with Google.</p>}
          {sessions.data && sessions.data.length === 0 && <EmptyState title="No browser sessions" />}
          {sessions.data && sessions.data.length > 0 && (
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>Browser</th><th>Started</th><th>Last seen</th><th /></tr></thead>
                <tbody>
                  {sessions.data.map((s) => (
                    <tr key={s.id}>
                      <td>{s.user_agent ?? "unknown"}{s.current && <> <Badge tone="info" plain>This one</Badge></>}</td>
                      <td>{formatDate(s.created_at)}</td><td>{formatDate(s.last_seen_at)}</td>
                      <td>{!s.current && <button className="btn btn-sm btn-ghost" onClick={() => kill.mutate(s.id)}>Sign out</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Your data">
          <p className="subtle">Download everything this service holds about you (no secrets).</p>
          <button className="btn" onClick={() => exportMine.mutate()} disabled={exportMine.isPending}>Download my data</button>
        </Card>
      </div>
    </AppShell>
  );
}
