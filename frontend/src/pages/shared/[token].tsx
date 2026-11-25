import { useRouter } from "next/router";
import { useEffect } from "react";
import { API_BASE_URL } from "@/lib/api";

/** A share link opens the standalone report page served by the API (no sign-in needed). */
export default function SharedRedirect() {
  const router = useRouter();
  const token = typeof router.query.token === "string" ? router.query.token : "";
  useEffect(() => {
    if (token) window.location.replace(`${API_BASE_URL}/api/v1/shared/${encodeURIComponent(token)}`);
  }, [token]);
  return <p className="muted" style={{ padding: 24 }}>Opening the shared report…</p>;
}
