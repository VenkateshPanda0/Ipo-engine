import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import { useRouter } from "next/router";
import { Card, ErrorState, LoadingBlock, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { humanize } from "@/lib/format";

export default function InvitePage() {
  const router = useRouter();
  const token = typeof router.query.token === "string" ? router.query.token : "";
  const preview = useQuery({ queryKey: ["invite", token], queryFn: () => api.invitationPreview(token), enabled: !!token, retry: 0 });
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers, retry: 0 });
  return (
    <div className="content" style={{ maxWidth: 480, margin: "10vh auto" }}>
      <Head>
        <title>Invitation · IPO Engine</title>
      </Head>
      <h1>You have been invited</h1>
      {!token && <Notice tone="negative">This link has no invitation in it.</Notice>}
      {preview.isLoading && token && <LoadingBlock rows={2} />}
      {preview.isError && <Notice tone="negative" title="This invitation is not valid">It may have expired, been used already, or been withdrawn. Ask the person who invited you for a new one.</Notice>}
      {preview.data && (
        <Card title={preview.data.organisation}>
          <p>
            Join as <strong>{humanize(preview.data.role)}</strong> with the address <strong>{preview.data.email}</strong>.
          </p>
          {providers.data?.google ? (
            <a className="btn btn-primary" href={api.googleLoginUrl("/", token)}>Continue with Google</a>
          ) : providers.isError ? (
            <ErrorState error={providers.error} />
          ) : (
            <Notice tone="caution">Google sign-in is not set up on this server. Ask your administrator for an API token instead.</Notice>
          )}
        </Card>
      )}
    </div>
  );
}
