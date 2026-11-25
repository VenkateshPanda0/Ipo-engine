import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AppShell, PageHead } from "@/components/layout/AppShell";
import { Badge, Card, EmptyState, ErrorState, LoadingBlock, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, humanize } from "@/lib/format";

const ROLES = ["viewer", "analyst", "reviewer", "admin"];

export default function TeamPage() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: 0 });
  const isAdmin = me.data?.role === "admin";
  const members = useQuery({ queryKey: ["members"], queryFn: api.members, retry: 0 });
  const invitations = useQuery({ queryKey: ["invitations"], queryFn: api.invitations, enabled: isAdmin, retry: 0 });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("analyst");
  const [link, setLink] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["members"] }).then(() => qc.invalidateQueries({ queryKey: ["invitations"] }));
  const invite = useMutation({ mutationFn: () => api.invite(email.trim(), role), onSuccess: (r) => { setLink(r.link); setEmail(""); void refresh(); } });
  const change = useMutation({ mutationFn: (v: { id: string; role: string }) => api.changeRole(v.id, v.role), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => api.removeMember(id), onSuccess: refresh });
  const revoke = useMutation({ mutationFn: (id: string) => api.revokeInvitation(id), onSuccess: refresh });

  return (
    <AppShell title="Team">
      <PageHead title="Team" description="People in your organisation and what each may do. Everyone here sees the same cases." />
      <div className="stack">
        <Card title="Members">
          {members.isLoading && <LoadingBlock />}
          {members.isError && <ErrorState error={members.error} onRetry={() => members.refetch()} />}
          {members.data && (
            <div className="table-wrap">
              <table className="data">
                <thead><tr><th>Person</th><th>Role</th><th>Status</th>{isAdmin && <th />}</tr></thead>
                <tbody>
                  {members.data.map((m) => (
                    <tr key={m.user_id}>
                      <td>{m.name ? `${m.name} · ` : ""}{m.email}{m.is_owner && <> <Badge tone="info" plain>Owner</Badge></>}</td>
                      <td>
                        {isAdmin ? (
                          <select aria-label={`Role of ${m.email}`} value={m.role} onChange={(e) => change.mutate({ id: m.user_id, role: e.target.value })} disabled={m.user_id === me.data?.user_id}>
                            {ROLES.map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
                          </select>
                        ) : humanize(m.role)}
                      </td>
                      <td>{m.status === "active" ? <Badge tone="positive">Active</Badge> : <Badge tone="negative">{humanize(m.status)}</Badge>}</td>
                      {isAdmin && (
                        <td>
                          {m.user_id !== me.data?.user_id && (
                            <button className="btn btn-sm btn-ghost" onClick={() => { if (window.confirm(`Remove ${m.email}? Their tokens and sessions stop working at once.`)) remove.mutate(m.user_id); }}>Remove</button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {(change.isError || remove.isError) && <ErrorState error={change.error ?? remove.error} />}
        </Card>
        {isAdmin && (
          <Card title="Invite someone">
            <form className="row" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}>
              <input type="email" required placeholder="name@company.com" aria-label="Email address" value={email} onChange={(e) => setEmail(e.target.value)} style={{ maxWidth: 300 }} />
              <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES.map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
              </select>
              <button className="btn btn-primary" type="submit" disabled={invite.isPending}>Create invitation</button>
            </form>
            {invite.isError && <ErrorState error={invite.error} />}
            {link && (
              <div style={{ marginTop: 12 }}>
                <Notice tone="positive" title="Send this link to the person. It is shown only now.">
                  <code style={{ wordBreak: "break-all" }}>{link}</code>
                  <div><button className="btn btn-sm" style={{ marginTop: 8 }} onClick={() => navigator.clipboard?.writeText(link)}>Copy</button></div>
                </Notice>
              </div>
            )}
            <h3 style={{ marginTop: 18 }}>Invitations</h3>
            {invitations.data && invitations.data.length === 0 && <EmptyState title="No invitations yet" />}
            {invitations.data && invitations.data.length > 0 && (
              <div className="table-wrap">
                <table className="data">
                  <thead><tr><th>Address</th><th>Role</th><th>State</th><th>Expires</th><th /></tr></thead>
                  <tbody>
                    {invitations.data.map((i) => (
                      <tr key={i.id}>
                        <td>{i.email}</td><td>{humanize(i.role)}</td><td>{humanize(i.state)}</td><td>{formatDate(i.expires_at)}</td>
                        <td>{i.state === "pending" && <button className="btn btn-sm btn-ghost" onClick={() => revoke.mutate(i.id)}>Withdraw</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
      </div>
    </AppShell>
  );
}
