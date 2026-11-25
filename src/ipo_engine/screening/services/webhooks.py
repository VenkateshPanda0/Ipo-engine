"""
Webhooks: tell another system when something happens, reliably and verifiably.

* Each organisation can register up to 10 HTTPS endpoints and choose the events they receive.
* Every delivery is signed: ``X-IPO-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">`` with
  the endpoint's secret. The secret is derived from the server's ``WEBHOOK_SIGNING_KEY`` and the
  endpoint's id and version, so the database holds no secrets; rotating bumps the version.
* Events go to an outbox first (queued right after the change that caused them, and never able to
  break it), then a dispatcher retries with backoff (1 min, 5 min, 30 min, 2 h, 12 h) and gives up
  after ``WEBHOOK_MAX_ATTEMPTS``, telling the organisation's admins.
* The payload carries identifiers and names, never extracted figures or document text.
* Targets are checked against SSRF (see ``network/webhook_http.py``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update

from ipo_engine.screening.core.config import Settings
from ipo_engine.screening.core.constants import DEFAULT_ORG_ID
from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import (
    CaseRow,
    DocumentRow,
    HumanReviewRow,
    MembershipRow,
    NotificationRow,
    OrganisationRow,
    ReportRow,
    WebhookDeliveryRow,
    WebhookRow,
)
from ipo_engine.screening.db.repositories import audit
from ipo_engine.screening.models.exceptions import NotFoundError
from ipo_engine.screening.services.accounts import AccountError, now

logger = logging.getLogger(__name__)

EVENTS = (
    "ping",
    "case.created",
    "document.processed",
    "screening.completed",
    "review.signed_off",
    "comment.added",
)
#: audited change -> webhook event
AUDIT_EVENTS = {
    "case.created": "case.created",
    "document.extracted": "document.processed",
    "document.failed": "document.processed",
    "report.created": "screening.completed",
    "human_review.decision": "review.signed_off",
    "comment.added": "comment.added",
}
MAX_PER_ORG = 10
BACKOFF = (60, 300, 1800, 7200, 43200)  # seconds before attempt 2, 3, ...
LEASE_S = 60


def sign(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def verify_signature(secret: str, header: str, body: bytes, *, tolerance_s: int = 300) -> bool:
    """For receivers (and our tests): check a signature header and that it is recent."""
    try:
        fields = dict(p.split("=", 1) for p in header.split(","))
        ts = int(fields["t"])
    except (ValueError, KeyError):
        return False
    if abs(now().timestamp() - ts) > tolerance_s:
        return False
    return hmac.compare_digest(sign(secret, ts, body), header)


class WebhookService:
    def __init__(
        self, db: Database, settings: Settings, sender: Any = None, resolver: Any = None
    ) -> None:
        self._db, self._settings = db, settings
        self._sender, self._resolver = sender, resolver

    # ---------------------------------------------------------------- plumbing
    @property
    def enabled(self) -> bool:
        return bool(self._settings.webhook_signing_key)

    def _secret(self, webhook_id: str, version: int) -> str:
        key = self._settings.webhook_signing_key
        if not key:
            raise AccountError("Webhooks are not enabled on this server (WEBHOOK_SIGNING_KEY).")
        mac = hmac.new(key.encode(), f"webhook:{webhook_id}:{version}".encode(), hashlib.sha256)
        return "whsec_" + mac.hexdigest()

    def _check_url(self, url: str) -> None:
        from ipo_engine.screening.network.http import HttpError
        from ipo_engine.screening.network.webhook_http import validate_target

        kwargs: dict[str, Any] = {"allow_private": self._settings.allow_private_webhook_targets}
        if self._resolver is not None:
            kwargs["resolver"] = self._resolver
        try:
            validate_target(url, **kwargs)
        except HttpError as exc:
            raise AccountError(str(exc)) from exc

    def _get_sender(self) -> Any:
        if self._sender is None:
            from ipo_engine.screening.network.webhook_http import PinnedSender

            self._sender = PinnedSender(allow_private=self._settings.allow_private_webhook_targets)
        return self._sender

    # ------------------------------------------------------------------ manage
    def create(self, org_id: str, url: str, events: list[str], *, actor: str) -> dict[str, Any]:
        if not self.enabled:
            raise AccountError("Webhooks are not enabled on this server (WEBHOOK_SIGNING_KEY).")
        url = url.strip()
        if len(url) > 500:
            raise AccountError("The webhook URL is too long.")
        events = sorted(set(events))
        unknown = [e for e in events if e not in EVENTS or e == "ping"]
        if unknown or not events:
            raise AccountError(
                f"Choose events from: {', '.join(e for e in EVENTS if e != 'ping')}."
            )
        self._check_url(url)
        with self._db.session() as s:
            count = s.execute(
                select(func.count()).select_from(WebhookRow).where(WebhookRow.org_id == org_id)
            ).scalar_one()
            if count >= MAX_PER_ORG:
                raise AccountError(f"An organisation can have at most {MAX_PER_ORG} webhooks.")
            row = WebhookRow(
                id=str(uuid4()), org_id=org_id, url=url, events=events, created_by=actor
            )
            s.add(row)
            s.flush()
            audit(
                s, actor=actor, action="webhook.created", entity_type="webhook", entity_id=row.id,
                org_id=org_id, details={"events": events},
            )  # fmt: skip
            return {**self._out(row), "secret": self._secret(row.id, row.secret_version)}

    def list_all(self, org_id: str) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.execute(
                select(WebhookRow)
                .where(WebhookRow.org_id == org_id)
                .order_by(WebhookRow.created_at)
            ).scalars()
            return [self._out(r) for r in rows]

    def update(
        self, webhook_id: str, org_id: str, *, actor: str, active: bool | None = None,
        events: list[str] | None = None, url: str | None = None,
    ) -> dict[str, Any]:  # fmt: skip
        if url is not None:
            self._check_url(url.strip())
        if events is not None and (
            not events or [e for e in events if e not in EVENTS or e == "ping"]
        ):
            raise AccountError("Choose events from the documented list.")
        with self._db.session() as s:
            row = self._row(s, webhook_id, org_id)
            if active is not None:
                row.active = active
            if events is not None:
                row.events = sorted(set(events))
            if url is not None:
                row.url = url.strip()
            audit(
                s, actor=actor, action="webhook.updated", entity_type="webhook",
                entity_id=webhook_id, org_id=org_id,
            )  # fmt: skip
            return self._out(row)

    def rotate(self, webhook_id: str, org_id: str, *, actor: str) -> dict[str, Any]:
        with self._db.session() as s:
            row = self._row(s, webhook_id, org_id)
            row.secret_version += 1
            audit(
                s, actor=actor, action="webhook.rotated", entity_type="webhook",
                entity_id=webhook_id, org_id=org_id,
            )  # fmt: skip
            return {**self._out(row), "secret": self._secret(row.id, row.secret_version)}

    def delete(self, webhook_id: str, org_id: str, *, actor: str) -> None:
        with self._db.session() as s:
            row = self._row(s, webhook_id, org_id)
            s.delete(row)
            audit(
                s, actor=actor, action="webhook.deleted", entity_type="webhook",
                entity_id=webhook_id, org_id=org_id,
            )  # fmt: skip

    def deliveries(self, webhook_id: str, org_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._db.session() as s:
            self._row(s, webhook_id, org_id)
            rows = s.execute(
                select(WebhookDeliveryRow)
                .where(WebhookDeliveryRow.webhook_id == webhook_id)
                .order_by(WebhookDeliveryRow.created_at.desc())
                .limit(limit)
            ).scalars()
            return [
                {
                    "id": d.id,
                    "event": d.event,
                    "status": d.status,
                    "attempts": d.attempts,
                    "last_status": d.last_status,
                    "last_error": d.last_error,
                    "created_at": d.created_at,
                    "delivered_at": d.delivered_at,
                }
                for d in rows
            ]

    def redeliver(self, webhook_id: str, delivery_id: str, org_id: str) -> None:
        with self._db.session() as s:
            self._row(s, webhook_id, org_id)
            d = s.get(WebhookDeliveryRow, delivery_id)
            if d is None or d.webhook_id != webhook_id:
                raise NotFoundError("delivery", delivery_id)
            d.status, d.attempts, d.next_attempt_at = "pending", 0, now()

    @staticmethod
    def _row(s: Any, webhook_id: str, org_id: str) -> WebhookRow:
        row = s.get(WebhookRow, webhook_id)
        if row is None or row.org_id != org_id:
            raise NotFoundError("webhook", webhook_id)
        return row  # type: ignore[no-any-return]

    @staticmethod
    def _out(row: WebhookRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "url": row.url,
            "events": row.events,
            "active": row.active,
            "secret_version": row.secret_version,
            "created_at": row.created_at,
        }

    # -------------------------------------------------------------------- emit
    def _queue(self, s: Any, org_id: str, event: str, data: dict[str, Any]) -> int:
        """Queue the event in the caller's transaction, once per interested endpoint."""
        # ids and enums arrive as UUID and Enum objects; the outbox stores plain JSON
        data = json.loads(json.dumps(data, default=lambda o: getattr(o, "value", str(o))))
        org = s.get(OrganisationRow, org_id)
        if org is not None and (org.settings or {}).get("webhooks_enabled") is False:
            return 0
        queued = 0
        for hook in s.execute(
            select(WebhookRow).where(WebhookRow.org_id == org_id, WebhookRow.active)
        ).scalars():
            if event != "ping" and event not in hook.events:
                continue
            payload = {
                "id": str(uuid4()),
                "event": event,
                "created_at": now().isoformat(),
                "organisation_id": org_id,
                "data": data,
            }
            s.add(
                WebhookDeliveryRow(
                    id=payload["id"], webhook_id=hook.id, org_id=org_id, event=event,
                    payload=payload, status="pending", next_attempt_at=now(),
                )
            )  # fmt: skip
            queued += 1
        return queued

    def emit(self, org_id: str, event: str, data: dict[str, Any]) -> int:
        """Queue an event in its own transaction (for events that are not an audited change)."""
        if not self.enabled:
            return 0
        try:
            with self._db.session() as s:
                return self._queue(s, org_id, event, data)
        except Exception:  # an event must never break the action that caused it
            logger.exception("webhook_emit_failed", extra={"event_name": event})
            return 0

    def on_audit(
        self,
        s: Any,
        *,
        action: str,
        entity_id: str,
        case_id: str | None,
        org_id: str | None,
        details: dict[str, Any],
    ) -> None:
        """Called for every audited change, inside its transaction: queue the matching event.

        The event row is written in the same transaction as the change and its audit record, so all
        three exist or none do: a crash between "committed" and "announced" cannot lose an event.
        """
        event = AUDIT_EVENTS.get(action)
        if event is None or not self.enabled:
            return
        try:
            data: dict[str, Any]
            if action == "case.created":
                case = s.get(CaseRow, case_id) if case_id else None
                data = {"case_id": case_id, "company_name": case.company_name if case else None}
            elif action in ("document.extracted", "document.failed"):
                doc = s.get(DocumentRow, entity_id)
                data = {
                    "document_id": entity_id,
                    "case_id": case_id,
                    "status": doc.status if doc else None,
                }
            elif action == "report.created":
                data = {
                    "case_id": case_id,
                    "report_id": entity_id,
                    "outcome": details.get("outcome"),
                }
            elif action == "comment.added":
                data = {"case_id": case_id, "comment_id": entity_id}
            else:  # human_review.decision: found through its report
                review = s.get(HumanReviewRow, entity_id)
                report_id = review.report_id if review else None
                owner = s.get(ReportRow, report_id) if report_id else None
                case_id = owner.case_id if owner else None
                data = {"report_id": report_id, "decision": details.get("decision")}
            if org_id is None and case_id is not None:
                org_id = s.execute(select(CaseRow.org_id).where(CaseRow.id == case_id)).scalar()
            if org_id is None:
                org_id = DEFAULT_ORG_ID  # a report made without a case belongs to the default one
            self._queue(s, org_id, event, data)
        except Exception:  # an event must never break the change that caused it
            logger.exception("webhook_outbox_failed", extra={"event_name": event})

    def ping(self, webhook_id: str, org_id: str) -> None:
        with self._db.session() as s:
            self._row(s, webhook_id, org_id)
        self.emit_to(webhook_id, org_id, "ping", {"message": "Test event from IPO Engine"})

    def emit_to(self, webhook_id: str, org_id: str, event: str, data: dict[str, Any]) -> None:
        with self._db.session() as s:
            self._row(s, webhook_id, org_id)
            payload = {
                "id": str(uuid4()), "event": event, "created_at": now().isoformat(),
                "organisation_id": org_id, "data": data,
            }  # fmt: skip
            s.add(
                WebhookDeliveryRow(
                    id=payload["id"], webhook_id=webhook_id, org_id=org_id, event=event,
                    payload=payload, status="pending", next_attempt_at=now(),
                )
            )  # fmt: skip

    # ---------------------------------------------------------------- dispatch
    def dispatch_due(self, limit: int = 20) -> int:
        """Send deliveries that are due. Returns how many were attempted."""
        if not self.enabled:
            return 0
        with self._db.session() as s:
            due = list(
                s.execute(
                    select(WebhookDeliveryRow.id)
                    .where(
                        WebhookDeliveryRow.status == "pending",
                        WebhookDeliveryRow.next_attempt_at <= now(),
                    )
                    .order_by(WebhookDeliveryRow.next_attempt_at)
                    .limit(limit)
                ).scalars()
            )
        done = 0
        for delivery_id in due:
            if self._attempt(delivery_id):
                done += 1
        return done

    def _attempt(self, delivery_id: str) -> bool:
        with self._db.session() as s:
            # claim: push the due time forward so no other dispatcher picks it up meanwhile
            claimed: Any = s.execute(
                update(WebhookDeliveryRow)
                .where(
                    WebhookDeliveryRow.id == delivery_id,
                    WebhookDeliveryRow.status == "pending",
                    WebhookDeliveryRow.next_attempt_at <= now(),
                )
                .values(next_attempt_at=now() + timedelta(seconds=LEASE_S))
            )
            if claimed.rowcount != 1:
                return False
            d = s.get(WebhookDeliveryRow, delivery_id)
            assert d is not None
            hook = s.get(WebhookRow, d.webhook_id)
            if hook is None or not hook.active:
                d.status, d.last_error = "failed", "endpoint is inactive or deleted"
                return True
            url, version, hook_id, org_id = hook.url, hook.secret_version, hook.id, d.org_id
            body = json.dumps(d.payload, separators=(",", ":"), sort_keys=True).encode()
            event, attempt = d.event, d.attempts + 1
        stamp = int(now().timestamp())
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "IPO-Engine-Webhook/1",
            "X-IPO-Event": event,
            "X-IPO-Delivery": delivery_id,
            "X-IPO-Signature": sign(self._secret(hook_id, version), stamp, body),
        }
        code: int | None = None
        error: str | None = None
        try:
            code = int(self._get_sender().send(url, body, headers))
            if not 200 <= code < 300:
                error = f"endpoint answered {code}"
        except Exception as exc:  # network errors, validation at send time
            error = str(exc)[:300] or type(exc).__name__
        with self._db.session() as s:
            d = s.get(WebhookDeliveryRow, delivery_id)
            assert d is not None
            d.attempts, d.last_status, d.last_error = attempt, code, error
            if error is None:
                d.status, d.delivered_at = "delivered", now()
            elif attempt >= self._settings.webhook_max_attempts:
                d.status = "failed"
                self._tell_admins(s, org_id, hook_id, url)
            else:
                wait = BACKOFF[min(attempt - 1, len(BACKOFF) - 1)]
                d.next_attempt_at = now() + timedelta(seconds=wait)
        return True

    @staticmethod
    def _tell_admins(s: Any, org_id: str, hook_id: str, url: str) -> None:
        host = url.split("/")[2] if "//" in url else url
        for admin_id in s.execute(
            select(MembershipRow.user_id).where(
                MembershipRow.org_id == org_id, MembershipRow.role == "admin"
            )
        ).scalars():
            s.add(
                NotificationRow(
                    id=str(uuid4()), user_id=admin_id, org_id=org_id, kind="webhook_failed",
                    title=f"Webhook to {host} keeps failing and was given up", link="/settings",
                )
            )  # fmt: skip


class WebhookDispatcher:
    """A background thread that sends due deliveries every few seconds."""

    def __init__(self, service: WebhookService, every_s: float = 5.0) -> None:
        self._svc, self._every = service, every_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="webhook-dispatcher", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(5)

    def _run(self) -> None:
        while not self._stop.wait(self._every):
            try:
                self._svc.dispatch_due()
            except Exception:
                logger.exception("webhook_dispatch_failed")
