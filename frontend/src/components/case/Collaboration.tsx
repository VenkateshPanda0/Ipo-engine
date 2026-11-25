import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card, ErrorState, LoadingBlock } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, humanize } from "@/lib/format";

/** Who is on the case, and the conversation about it. Shown when the server has accounts on. */
export function Collaboration({ caseId, assigneeId, companyName }: { caseId: string; assigneeId: string | null | undefined; companyName: string }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: 0 });
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers, retry: 0 });
  const enabled = !!providers.data?.accounts;
  const members = useQuery({ queryKey: ["members"], queryFn: api.members, retry: 0, enabled: enabled && me.data?.role !== "viewer" });
  const comments = useQuery({ queryKey: ["comments", caseId], queryFn: () => api.comments(caseId), retry: 0, enabled });
  const [body, setBody] = useState("");
  const [confirm, setConfirm] = useState("");
  const [erasing, setErasing] = useState(false);
  const canWrite = me.data?.role !== "viewer";
  const assign = useMutation({ mutationFn: (id: string | null) => api.assign(caseId, id), onSuccess: () => qc.invalidateQueries({ queryKey: ["case", caseId] }) });
  const post = useMutation({ mutationFn: () => api.addComment(caseId, body.trim()), onSuccess: () => { setBody(""); void qc.invalidateQueries({ queryKey: ["comments", caseId] }); } });
  const del = useMutation({ mutationFn: (id: string) => api.deleteComment(caseId, id), onSuccess: () => qc.invalidateQueries({ queryKey: ["comments", caseId] }) });
  const erase = useMutation({ mutationFn: () => api.eraseCase(caseId, confirm), onSuccess: () => { window.location.assign("/cases"); } });

  if (!enabled) return null;
  return (
    <Card title="Team and discussion">
      <div className="stack">
        <label className="row">
          <span>Assigned to</span>
          <select aria-label="Assignee" value={assigneeId ?? ""} disabled={!canWrite || !members.data} onChange={(e) => assign.mutate(e.target.value || null)} style={{ maxWidth: 300 }}>
            <option value="">Nobody</option>
            {(members.data ?? []).map((m) => (
              <option key={m.user_id} value={m.user_id}>{m.name ?? m.email} ({humanize(m.role)})</option>
            ))}
          </select>
        </label>
        {assign.isError && <ErrorState error={assign.error} />}
        {comments.isLoading && <LoadingBlock rows={2} />}
        {comments.isError && <ErrorState error={comments.error} />}
        {comments.data && comments.data.length === 0 && <p className="subtle">No comments yet.</p>}
        {comments.data?.map((c) => (
          <div key={c.id} className="comment">
            <div className="subtle"><strong>{c.author}</strong> · {formatDate(c.created_at)}</div>
            <p style={{ whiteSpace: "pre-wrap", margin: "4px 0" }}>{c.body}</p>
            {(c.author_id === me.data?.user_id || me.data?.role === "admin") && <button className="btn btn-sm btn-ghost" onClick={() => del.mutate(c.id)}>Delete</button>}
          </div>
        ))}
        {canWrite && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); post.mutate(); }}>
            <textarea aria-label="Add a comment" rows={3} maxLength={5000} placeholder="Write a note for the team…" value={body} onChange={(e) => setBody(e.target.value)} />
            <div><button className="btn" type="submit" disabled={!body.trim() || post.isPending}>Comment</button></div>
            {post.isError && <ErrorState error={post.error} />}
          </form>
        )}
        {me.data?.role === "admin" && (
          <div>
            {!erasing ? (
              <button className="btn btn-sm btn-ghost" onClick={() => setErasing(true)}>Erase this case permanently…</button>
            ) : (
              <div className="stack">
                <p className="subtle">This deletes the case, its documents, its history and its reports for good. Type <strong>{companyName}</strong> to confirm.</p>
                <div className="row">
                  <input aria-label="Confirm company name" value={confirm} onChange={(e) => setConfirm(e.target.value)} style={{ maxWidth: 300 }} />
                  <button className="btn btn-danger" disabled={confirm !== companyName || erase.isPending} onClick={() => erase.mutate()}>Erase</button>
                  <button className="btn btn-ghost" onClick={() => setErasing(false)}>Cancel</button>
                </div>
                {erase.isError && <ErrorState error={erase.error} />}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
