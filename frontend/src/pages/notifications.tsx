import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { AppShell, PageHead } from "@/components/layout/AppShell";
import { Badge, Card, EmptyState, ErrorState, LoadingBlock } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";

export default function NotificationsPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["notifications"], queryFn: () => api.notifications(false), retry: 0 });
  const mark = useMutation({ mutationFn: (id?: string) => api.markRead(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }).then(() => qc.invalidateQueries({ queryKey: ["notifications", "count"] })) });
  return (
    <AppShell title="Notifications">
      <PageHead title="Notifications" actions={<button className="btn" onClick={() => mark.mutate(undefined)} disabled={!list.data?.unread}>Mark all read</button>} />
      <Card>
        {list.isLoading && <LoadingBlock rows={3} />}
        {list.isError && <ErrorState error={list.error} />}
        {list.data && list.data.items.length === 0 && <EmptyState title="Nothing yet">You will be told here when a case is assigned to you or someone comments on yours.</EmptyState>}
        {list.data && list.data.items.length > 0 && (
          <ul className="plain-list">
            {list.data.items.map((n) => (
              <li key={n.id} className="row" style={{ justifyContent: "space-between", padding: "8px 0" }}>
                <span>
                  {!n.read && <Badge tone="attention" plain>New</Badge>}{" "}
                  {n.link ? <Link href={n.link} onClick={() => !n.read && mark.mutate(n.id)}>{n.title}</Link> : n.title}
                  <span className="subtle"> · {formatDate(n.created_at)}</span>
                </span>
                {!n.read && <button className="btn btn-sm btn-ghost" onClick={() => mark.mutate(n.id)}>Mark read</button>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}
