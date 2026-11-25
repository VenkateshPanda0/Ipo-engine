import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import { useRouter } from "next/router";
import { useState } from "react";
import { Card, Notice } from "@/components/ui";
import { api } from "@/lib/api";
import { setApiKey } from "@/lib/auth";

/** Only a path on this site may be returned to after sign-in. */
export function safeNext(value: unknown): string {
  return typeof value === "string" && value.startsWith("/") && !value.startsWith("//") && !value.includes("\\") ? value : "/";
}

export default function LoginPage() {
  const router = useRouter();
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers, retry: 0 });
  const [token, setToken] = useState("");
  const [bad, setBad] = useState<string | null>(null);
  const next = safeNext(router.query.next);
  const error = typeof router.query.error === "string" ? router.query.error : null;

  async function useToken(e: React.FormEvent) {
    e.preventDefault();
    setApiKey(token.trim());
    try {
      await api.me();
      await router.replace(next);
    } catch {
      setApiKey(null);
      setBad("That token was not accepted.");
    }
  }

  return (
    <div className="content" style={{ maxWidth: 480, margin: "10vh auto" }}>
      <Head>
        <title>Sign in · IPO Engine</title>
      </Head>
      <h1>Sign in</h1>
      <p className="muted">IPO Engine reads offer documents and screens them against a versioned ruleset. Decision support only.</p>
      <div className="stack">
        {error && <Notice tone="negative" title="Could not sign you in">{error}</Notice>}
        {providers.data?.google && (
          <Card title="Your Google account">
            <a className="btn btn-primary" href={api.googleLoginUrl(next)}>Continue with Google</a>
            <p className="subtle" style={{ marginTop: 8 }}>
              {providers.data.signup === "invite" ? "Access is by invitation. Ask an administrator of your organisation." : "Anyone with a verified Google address can create an account."}
            </p>
          </Card>
        )}
        <Card title="An API token or key">
          <form className="stack" onSubmit={useToken}>
            <input type="password" autoComplete="off" aria-label="API token" placeholder="ipo_… or an API key" value={token} onChange={(e) => setToken(e.target.value)} />
            {bad && <Notice tone="negative">{bad}</Notice>}
            <button className="btn" type="submit" disabled={!token.trim()}>Use for this tab</button>
          </form>
        </Card>
        {providers.isError && <Notice tone="caution">The API is not reachable, or authentication is off (then no sign-in is needed: open the dashboard).</Notice>}
      </div>
    </div>
  );
}
