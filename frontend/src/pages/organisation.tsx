import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/router";
import { useState } from "react";
import { AppShell, PageHead } from "@/components/layout/AppShell";
import { Badge, Card, ErrorState, LoadingBlock, Notice, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { saveBlob } from "@/lib/download";

const EVENTS = ["case.created", "document.processed", "screening.completed", "review.signed_off", "comment.added"];

export default function OrganisationPage() {
  const qc = useQueryClient();
  const router = useRouter();
  const org = useQuery({ queryKey: ["org"], queryFn: api.org, retry: 0 });
  const settings = useQuery({ queryKey: ["org-settings"], queryFn: api.orgSettings, retry: 0 });
  const usage = useQuery({ queryKey: ["usage"], queryFn: api.usage, retry: 0 });
  const hooks = useQuery({ queryKey: ["webhooks"], queryFn: api.webhooks, retry: 0 });
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>(["screening.completed"]);
  const [secret, setSecret] = useState<string | null>(null);
  const [confirm, setConfirm] = useState("");

  const rename = useMutation({ mutationFn: () => api.renameOrg(name.trim()), onSuccess: () => { setName(""); void qc.invalidateQueries(); } });
  const toggle = useMutation({ mutationFn: api.updateOrgSettings, onSuccess: () => qc.invalidateQueries({ queryKey: ["org-settings"] }) });
  const addHook = useMutation({ mutationFn: () => api.createWebhook(url.trim(), events), onSuccess: (r) => { setSecret(r.secret); setUrl(""); void qc.invalidateQueries({ queryKey: ["webhooks"] }); } });
  const delHook = useMutation({ mutationFn: api.deleteWebhook, onSuccess: () => qc.invalidateQueries({ queryKey: ["webhooks"] }) });
  const testHook = useMutation({ mutationFn: api.testWebhook });
  const exportAll = useMutation({ mutationFn: (files: boolean) => api.exportOrg(files), onSuccess: (b) => saveBlob(b, "organisation-export.zip") });
  const del = useMutation({ mutationFn: () => api.deleteOrg(confirm), onSuccess: () => { qc.clear(); void router.replace("/login"); } });

  return (
    <AppShell title="Organisation">
      <PageHead title={org.data?.name ?? "Organisation"} description="Settings for everyone in this organisation. Administrators only." />
      {org.isError && <ErrorState error={org.error} />}
      <div className="stack">
        {usage.data && (
          <div className="grid grid-4">
            <Stat label={`Cases`} value={usage.data.cases_total} />
            <Stat label={`Documents, last ${usage.data.period_days} days`} value={usage.data.documents_uploaded} hint={`${usage.data.pages_processed} pages`} />
            <Stat label={`Screenings, last ${usage.data.period_days} days`} value={usage.data.screenings_run} />
            <Stat label="Members" value={usage.data.members} />
          </div>
        )}
        <Card title="Name and rules">
          <form className="row" onSubmit={(e) => { e.preventDefault(); rename.mutate(); }}>
            <input placeholder={org.data?.name ?? "Organisation name"} aria-label="Organisation name" value={name} onChange={(e) => setName(e.target.value)} style={{ maxWidth: 300 }} />
            <button className="btn" type="submit" disabled={!name.trim() || rename.isPending}>Rename</button>
          </form>
          {settings.data && (
            <div className="stack" style={{ marginTop: 14 }}>
              <label className="row">
                <input type="checkbox" checked={toggle.isPending && toggle.variables?.four_eyes !== undefined ? toggle.variables.four_eyes : settings.data.four_eyes} onChange={(e) => toggle.mutate({ four_eyes: e.target.checked })} />
                <span><strong>Four eyes.</strong> The person who ran a screening cannot also sign it off.</span>
              </label>
              <label className="row">
                <input type="checkbox" checked={toggle.isPending && toggle.variables?.webhooks_enabled !== undefined ? toggle.variables.webhooks_enabled : settings.data.webhooks_enabled} onChange={(e) => toggle.mutate({ webhooks_enabled: e.target.checked })} />
                <span><strong>Send webhooks.</strong> Turn off to pause every endpoint at once.</span>
              </label>
            </div>
          )}
        </Card>
        <Card title="Webhooks">
          {hooks.isLoading && <LoadingBlock rows={2} />}
          {hooks.data && !hooks.data.enabled && <Notice tone="caution">Webhooks are not switched on for this server (the operator sets <code>WEBHOOK_SIGNING_KEY</code>).</Notice>}
          {hooks.data?.enabled && (
            <>
              <form className="stack" onSubmit={(e) => { e.preventDefault(); addHook.mutate(); }}>
                <input type="url" required placeholder="https://example.com/hooks/ipo-engine" aria-label="Endpoint URL" value={url} onChange={(e) => setUrl(e.target.value)} />
                <div className="row">
                  {EVENTS.map((ev) => (
                    <label key={ev} className="row">
                      <input type="checkbox" checked={events.includes(ev)} onChange={(e) => setEvents(e.target.checked ? [...events, ev] : events.filter((x) => x !== ev))} />
                      <code>{ev}</code>
                    </label>
                  ))}
                </div>
                <div><button className="btn btn-primary" type="submit" disabled={addHook.isPending || events.length === 0}>Add endpoint</button></div>
              </form>
              {addHook.isError && <ErrorState error={addHook.error} />}
              {secret && (
                <div style={{ marginTop: 12 }}>
                  <Notice tone="positive" title="Signing secret. It cannot be shown again (rotate to get a new one).">
                    <code style={{ wordBreak: "break-all" }}>{secret}</code>
                  </Notice>
                </div>
              )}
              <ul className="plain-list" style={{ marginTop: 12 }}>
                {hooks.data.items.map((h) => (
                  <li key={h.id} className="row" style={{ justifyContent: "space-between", padding: "6px 0" }}>
                    <span><code>{h.url}</code> {h.active ? <Badge tone="positive" plain>On</Badge> : <Badge tone="neutral" plain>Off</Badge>} <span className="subtle">{h.events.join(", ")}</span></span>
                    <span className="row">
                      <button className="btn btn-sm" onClick={() => testHook.mutate(h.id)}>Send test</button>
                      <button className="btn btn-sm btn-ghost" onClick={() => { if (window.confirm("Delete this endpoint?")) delHook.mutate(h.id); }}>Delete</button>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
        <Card title="Your organisation's data">
          <div className="row">
            <button className="btn" onClick={() => exportAll.mutate(false)} disabled={exportAll.isPending}>Export data (JSON)</button>
            <button className="btn" onClick={() => exportAll.mutate(true)} disabled={exportAll.isPending}>Export with the PDFs</button>
          </div>
          {exportAll.isError && <ErrorState error={exportAll.error} />}
        </Card>
        <Card title="Delete this organisation">
          <p className="subtle">Everyone is signed out at once and nobody can sign in. Your data is kept for a grace period set by the operator, then erased. Only an owner can do this. Type the organisation&apos;s exact name to confirm.</p>
          <div className="row">
            <input aria-label="Confirm organisation name" placeholder={org.data?.name} value={confirm} onChange={(e) => setConfirm(e.target.value)} style={{ maxWidth: 300 }} />
            <button className="btn btn-danger" disabled={confirm !== org.data?.name || del.isPending} onClick={() => del.mutate()}>Delete organisation</button>
          </div>
          {del.isError && <ErrorState error={del.error} />}
          <p className="subtle" style={{ marginTop: 8 }}>Dates of exports and changes are in the audit trail.</p>
        </Card>
      </div>
    </AppShell>
  );
}
