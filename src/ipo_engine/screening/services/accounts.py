"""
Organisations, users, memberships and personal API tokens.

Everything here is database-backed and used only when ``ACCOUNTS_ENABLED`` is on. Secrets are never
stored: a personal token is shown once and only its SHA-256 is kept; a lookup compares digests in
constant time. A suspended user, a removed member or a revoked, expired or foreign token is refused
exactly like an unknown one, so the response never says which.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ipo_engine.screening.core.constants import DEFAULT_ORG_ID
from ipo_engine.screening.core.security import Principal, Role
from ipo_engine.screening.db.base import Database
from ipo_engine.screening.db.models import (
    ApiTokenRow,
    IdentityRow,
    InvitationRow,
    MembershipRow,
    OrganisationRow,
    UserRow,
)
from ipo_engine.screening.db.repositories import audit
from ipo_engine.screening.models.exceptions import DomainError, NotFoundError

TOKEN_PREFIX = "ipo_"
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
_SLUG = re.compile(r"[^a-z0-9]+")


class AccountError(DomainError):
    """A request about accounts that cannot be carried out."""

    error_code = "ACCOUNT_ERROR"


def now() -> datetime:
    return datetime.now(tz=UTC)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def normalise_email(email: str) -> str:
    value = email.strip().lower()
    if not _EMAIL.match(value):
        raise AccountError("That is not a valid email address.")
    return value


def slugify(name: str) -> str:
    return _SLUG.sub("-", name.lower()).strip("-")[:60] or "org"


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything stored here is UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class AccountService:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ----------------------------------------------------------- organisations
    def create_org(self, name: str, *, created_by: str | None = None) -> dict[str, Any]:
        name = name.strip()
        if not 1 <= len(name) <= 200:
            raise AccountError("An organisation name must be 1 to 200 characters.")
        with self._db.session() as s:
            base = slugify(name)
            slug, n = base, 1
            while s.execute(select(OrganisationRow.id).where(OrganisationRow.slug == slug)).first():
                n += 1
                slug = f"{base}-{n}"
            row = OrganisationRow(id=str(uuid4()), name=name, slug=slug, created_by=created_by)
            s.add(row)
            s.flush()
            audit(
                s, actor=created_by or "system", action="org.created",
                entity_type="organisation", entity_id=row.id, org_id=row.id,
            )  # fmt: skip
            return self._org_out(row)

    def get_org(self, org_id: str) -> dict[str, Any]:
        with self._db.session() as s:
            row = s.get(OrganisationRow, org_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError("organisation", org_id)
            return self._org_out(row)

    def rename_org(self, org_id: str, name: str, *, actor: str) -> dict[str, Any]:
        name = name.strip()
        if not 1 <= len(name) <= 200:
            raise AccountError("An organisation name must be 1 to 200 characters.")
        with self._db.session() as s:
            row = s.get(OrganisationRow, org_id)
            if row is None or row.deleted_at is not None:
                raise NotFoundError("organisation", org_id)
            row.name = name
            audit(
                s, actor=actor, action="org.renamed", entity_type="organisation",
                entity_id=org_id, org_id=org_id,
            )  # fmt: skip
            return self._org_out(row)

    @staticmethod
    def _org_out(row: OrganisationRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "status": row.status,
            "created_at": row.created_at,
        }

    # ------------------------------------------------------------------ users
    def get_or_create_user(self, email: str, *, name: str | None = None) -> dict[str, Any]:
        email = normalise_email(email)
        with self._db.session() as s:
            row = s.execute(select(UserRow).where(UserRow.email == email)).scalar_one_or_none()
            if row is None:
                row = UserRow(id=str(uuid4()), email=email, name=(name or "").strip() or None)
                try:
                    with s.begin_nested():  # a savepoint: losing a race must not poison the session
                        s.add(row)
                        s.flush()
                except IntegrityError:  # another request created this person a moment ago
                    row = s.execute(select(UserRow).where(UserRow.email == email)).scalar_one()
            return self._user_out(row)

    def get_user(self, user_id: str) -> dict[str, Any]:
        with self._db.session() as s:
            row = s.get(UserRow, user_id)
            if row is None:
                raise NotFoundError("user", user_id)
            return self._user_out(row)

    def set_user_status(self, user_id: str, status: str, *, actor: str) -> dict[str, Any]:
        """Suspend or reinstate an account everywhere (the kill switch)."""
        if status not in ("active", "suspended"):
            raise AccountError("Status must be 'active' or 'suspended'.")
        with self._db.session() as s:
            row = s.get(UserRow, user_id)
            if row is None:
                raise NotFoundError("user", user_id)
            row.status = status
            audit(
                s, actor=actor, action=f"user.{status}", entity_type="user", entity_id=user_id
            )  # fmt: skip
            return self._user_out(row)

    @staticmethod
    def _user_out(row: UserRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "email": row.email,
            "name": row.name,
            "status": row.status,
            "email_verified": row.email_verified,
            "created_at": row.created_at,
            "last_login_at": row.last_login_at,
        }

    # ------------------------------------------------------------ memberships
    def add_member(
        self, org_id: str, user_id: str, role: Role, *, actor: str, owner: bool = False
    ) -> dict[str, Any]:
        with self._db.session() as s:
            if s.get(OrganisationRow, org_id) is None:
                raise NotFoundError("organisation", org_id)
            if s.get(UserRow, user_id) is None:
                raise NotFoundError("user", user_id)
            row = s.execute(
                select(MembershipRow).where(
                    MembershipRow.org_id == org_id, MembershipRow.user_id == user_id
                )
            ).scalar_one_or_none()
            if row is None:
                row = MembershipRow(
                    id=str(uuid4()),
                    org_id=org_id,
                    user_id=user_id,
                    role=role.value,
                    is_owner=owner,
                )
                s.add(row)
                action = "member.added"
            else:
                if row.role == Role.ADMIN.value and role != Role.ADMIN:
                    self._require_another_admin(s, org_id)
                row.role = role.value
                row.is_owner = row.is_owner or owner
                action = "member.role_changed"
            s.flush()
            audit(
                s, actor=actor, action=action, entity_type="user", entity_id=user_id,
                org_id=org_id, details={"role": role.value},
            )  # fmt: skip
            return self._member_out(row)

    @staticmethod
    def _require_another_admin(s: Any, org_id: str) -> None:
        """Refuse a change that would leave the organisation with no admin."""
        admins = s.execute(
            select(func.count())
            .select_from(MembershipRow)
            .where(MembershipRow.org_id == org_id, MembershipRow.role == Role.ADMIN.value)
        ).scalar_one()
        if admins <= 1:
            raise AccountError("An organisation must keep at least one admin.")

    def members(self, org_id: str) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.execute(
                select(MembershipRow, UserRow)
                .join(UserRow, UserRow.id == MembershipRow.user_id)
                .where(MembershipRow.org_id == org_id)
                .order_by(UserRow.email)
            ).all()
            return [
                {**self._member_out(m), "email": u.email, "name": u.name, "status": u.status}
                for m, u in rows
            ]

    def remove_member(self, org_id: str, user_id: str, *, actor: str) -> None:
        """Remove a member and revoke every token they hold in this organisation."""
        with self._db.session() as s:
            row = s.execute(
                select(MembershipRow).where(
                    MembershipRow.org_id == org_id, MembershipRow.user_id == user_id
                )
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("member", user_id)
            if row.role == Role.ADMIN.value:
                self._require_another_admin(s, org_id)
            for tok in s.execute(
                select(ApiTokenRow).where(
                    ApiTokenRow.org_id == org_id,
                    ApiTokenRow.user_id == user_id,
                    ApiTokenRow.revoked_at.is_(None),
                )
            ).scalars():
                tok.revoked_at = now()
            s.delete(row)
            audit(
                s, actor=actor, action="member.removed", entity_type="user", entity_id=user_id,
                org_id=org_id,
            )  # fmt: skip

    def role_of(self, org_id: str, user_id: str) -> Role | None:
        with self._db.session() as s:
            value = s.execute(
                select(MembershipRow.role).where(
                    MembershipRow.org_id == org_id, MembershipRow.user_id == user_id
                )
            ).scalar_one_or_none()
            return Role(value) if value else None

    def is_owner(self, org_id: str, user_id: str) -> bool:
        with self._db.session() as s:
            return bool(
                s.execute(
                    select(MembershipRow.is_owner).where(
                        MembershipRow.org_id == org_id, MembershipRow.user_id == user_id
                    )
                ).scalar_one_or_none()
            )

    def organisations_of(self, user_id: str) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.execute(
                select(OrganisationRow, MembershipRow.role)
                .join(MembershipRow, MembershipRow.org_id == OrganisationRow.id)
                .where(MembershipRow.user_id == user_id, OrganisationRow.deleted_at.is_(None))
                .order_by(OrganisationRow.name)
            ).all()
            return [{**self._org_out(o), "role": r} for o, r in rows]

    @staticmethod
    def _member_out(row: MembershipRow) -> dict[str, Any]:
        return {
            "user_id": row.user_id,
            "org_id": row.org_id,
            "role": row.role,
            "is_owner": row.is_owner,
        }

    # -------------------------------------------------------- personal tokens
    def create_token(
        self,
        *,
        org_id: str,
        user_id: str,
        name: str,
        role: Role | None = None,
        days: int | None = 90,
        parent_token_id: str | None = None,
    ) -> dict[str, Any]:
        """Issue a token. The plaintext is in the result once and is never stored.

        A token minted by another token (``parent_token_id``) never outlives it and is revoked
        with it, so revoking a leaked token also ends whatever it created.
        """
        name = name.strip()
        if not 1 <= len(name) <= 100:
            raise AccountError("A token name must be 1 to 100 characters.")
        if days is not None and not 1 <= days <= 3650:
            raise AccountError("Token lifetime must be 1 to 3650 days.")
        member_role = self.role_of(org_id, user_id)
        if member_role is None:
            raise AccountError("Only a member of the organisation can hold a token for it.")
        granted = role or member_role
        if not Principal(user_id, member_role, True, org_id).has(granted):
            raise AccountError("A token cannot have a higher role than its owner.")
        secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
        with self._db.session() as s:
            expires_at = now() + timedelta(days=days) if days else None
            if parent_token_id is not None:
                parent = s.get(ApiTokenRow, parent_token_id)
                if parent is None or parent.revoked_at is not None:
                    raise AccountError("The token making this request is no longer valid.")
                cap = _aware(parent.expires_at)
                if cap is not None and (expires_at is None or expires_at > cap):
                    expires_at = cap
            row = ApiTokenRow(
                id=str(uuid4()),
                token_hash=hash_secret(secret),
                prefix=secret[: len(TOKEN_PREFIX) + 6],
                user_id=user_id,
                org_id=org_id,
                name=name,
                role=granted.value,
                expires_at=expires_at,
                parent_token_id=parent_token_id,
            )
            s.add(row)
            s.flush()
            audit(
                s, actor=user_id, action="token.created", entity_type="token", entity_id=row.id,
                org_id=org_id, details={"name": name, "role": granted.value},
            )  # fmt: skip
            return {**self._token_out(row), "token": secret}

    def list_tokens(self, user_id: str, org_id: str | None = None) -> list[dict[str, Any]]:
        with self._db.session() as s:
            stmt = select(ApiTokenRow).where(ApiTokenRow.user_id == user_id)
            if org_id:
                stmt = stmt.where(ApiTokenRow.org_id == org_id)
            rows = s.execute(stmt.order_by(ApiTokenRow.created_at.desc())).scalars().all()
            return [self._token_out(r) for r in rows]

    def revoke_token(self, token_id: str, *, user_id: str, org_id: str, actor: str) -> None:
        with self._db.session() as s:
            row = s.get(ApiTokenRow, token_id)
            if row is None or row.user_id != user_id or row.org_id != org_id:
                raise NotFoundError("token", token_id)
            if row.revoked_at is None:
                stamp = now()
                row.revoked_at = stamp
                audit(
                    s, actor=actor, action="token.revoked", entity_type="token",
                    entity_id=token_id, org_id=org_id,
                )  # fmt: skip
            # whatever this token minted (and what those minted) goes with it
            pending = [token_id]
            while pending:
                kids = (
                    s.execute(
                        select(ApiTokenRow).where(
                            ApiTokenRow.parent_token_id.in_(pending),
                            ApiTokenRow.revoked_at.is_(None),
                        )
                    )
                    .scalars()
                    .all()
                )
                for kid in kids:
                    kid.revoked_at = now()
                pending = [kid.id for kid in kids]

    def authenticate_token(self, presented: str) -> Principal | None:
        """The principal for a personal token, or None for anything that is not a live token."""
        if not presented.startswith(TOKEN_PREFIX):
            return None
        digest = hash_secret(presented)
        with self._db.session() as s:
            # one round trip for the token, its user, its organisation and the membership
            found = s.execute(
                select(
                    ApiTokenRow,
                    UserRow.status,
                    OrganisationRow.status,
                    OrganisationRow.deleted_at,
                    MembershipRow.role,
                )
                .join(UserRow, UserRow.id == ApiTokenRow.user_id)
                .join(OrganisationRow, OrganisationRow.id == ApiTokenRow.org_id)
                .outerjoin(
                    MembershipRow,
                    (MembershipRow.org_id == ApiTokenRow.org_id)
                    & (MembershipRow.user_id == ApiTokenRow.user_id),
                )
                .where(ApiTokenRow.token_hash == digest)
            ).first()
            if found is None:
                return None
            row, user_status, org_status, org_deleted, member = found
            if not hmac.compare_digest(row.token_hash, digest):
                return None
            expires = _aware(row.expires_at)
            if row.revoked_at is not None or (expires is not None and expires <= now()):
                return None
            if user_status != "active":
                return None
            if org_deleted is not None or org_status != "active":
                return None
            if member is None:
                return None
            last = _aware(row.last_used_at)
            if last is None or now() - last > timedelta(minutes=1):  # a write per request is costly
                row.last_used_at = now()
            # never above the member's current role, even if it was lowered after issue
            effective = min(Role(row.role), Role(member), key=_rank)
            return Principal(
                user_id=row.user_id,
                role=effective,
                authenticated=True,
                org_id=row.org_id,
                auth="token",
                token_id=row.id,
            )

    @staticmethod
    def _token_out(row: ApiTokenRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "prefix": row.prefix,
            "role": row.role,
            "org_id": row.org_id,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "last_used_at": row.last_used_at,
            "revoked_at": row.revoked_at,
        }

    # ------------------------------------------------------------ invitations
    def invite(
        self, org_id: str, email: str, role: Role, *, actor: str, days: int = 7
    ) -> dict[str, Any]:
        """Invite an email address. The link token is in the result once; only its hash is kept."""
        email = normalise_email(email)
        secret = secrets.token_urlsafe(32)
        with self._db.session() as s:
            if s.get(OrganisationRow, org_id) is None:
                raise NotFoundError("organisation", org_id)
            row = InvitationRow(
                id=str(uuid4()),
                org_id=org_id,
                email=email,
                role=role.value,
                token_hash=hash_secret(secret),
                created_by=actor,
                expires_at=now() + timedelta(days=days),
            )
            s.add(row)
            s.flush()
            audit(
                s, actor=actor, action="invitation.created", entity_type="invitation",
                entity_id=row.id, org_id=org_id, details={"role": role.value},
            )  # fmt: skip
            return {**self._invitation_out(row), "token": secret}

    def invitations(self, org_id: str) -> list[dict[str, Any]]:
        with self._db.session() as s:
            rows = s.execute(
                select(InvitationRow)
                .where(InvitationRow.org_id == org_id)
                .order_by(InvitationRow.created_at.desc())
            ).scalars()
            return [self._invitation_out(r) for r in rows]

    def revoke_invitation(self, org_id: str, invitation_id: str, *, actor: str) -> None:
        with self._db.session() as s:
            row = s.get(InvitationRow, invitation_id)
            if row is None or row.org_id != org_id:
                raise NotFoundError("invitation", invitation_id)
            if row.revoked_at is None and row.accepted_at is None:
                row.revoked_at = now()
                audit(
                    s, actor=actor, action="invitation.revoked", entity_type="invitation",
                    entity_id=invitation_id, org_id=org_id,
                )  # fmt: skip

    def _live_invitation(
        self, s: Any, token: str | None = None, *, invitation_id: str | None = None
    ) -> InvitationRow | None:
        if invitation_id is not None:
            row = s.get(InvitationRow, invitation_id)
        elif token:
            row = s.execute(
                select(InvitationRow).where(InvitationRow.token_hash == hash_secret(token))
            ).scalar_one_or_none()
        else:
            return None
        if row is None or row.revoked_at is not None or row.accepted_at is not None:
            return None
        if _aware(row.expires_at) <= now():  # type: ignore[operator]
            return None
        return row  # type: ignore[no-any-return]

    def invitation_id_for_token(self, token: str) -> str | None:
        with self._db.session() as s:
            row = self._live_invitation(s, token)
            return str(row.id) if row else None

    def invitation_preview(self, token: str) -> dict[str, Any] | None:
        """What an invitation link is for (organisation and role), or None if it is not live."""
        with self._db.session() as s:
            row = self._live_invitation(s, token)
            org = s.get(OrganisationRow, row.org_id) if row else None
            if row is None or org is None or org.deleted_at is not None:
                return None
            return {"organisation": org.name, "email": row.email, "role": row.role}

    @staticmethod
    def _invitation_out(row: InvitationRow) -> dict[str, Any]:
        state = (
            "accepted"
            if row.accepted_at
            else "revoked"
            if row.revoked_at
            else "expired"
            if _aware(row.expires_at) <= now()  # type: ignore[operator]
            else "pending"
        )
        return {
            "id": row.id,
            "email": row.email,
            "role": row.role,
            "state": state,
            "created_by": row.created_by,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
        }

    # ----------------------------------------------------------------- sign-in
    def sign_in(
        self,
        *,
        provider: str,
        subject: str,
        email: str,
        email_verified: bool,
        name: str | None,
        invitation_id: str | None,
        signup_open: bool,
    ) -> tuple[dict[str, Any], str]:
        """Resolve a verified identity to (user, organisation id) or refuse.

        Order: a known (provider, subject); else a user with that verified email (the identity is
        linked); else a live invitation for that email; else, only if sign-up is open, a new user
        with an organisation of their own. An unverified email is never trusted.
        """
        if not email_verified:
            raise AccountError("The identity provider has not verified that email address.")
        email = normalise_email(email)
        with self._db.session() as s:
            ident = s.execute(
                select(IdentityRow).where(
                    IdentityRow.provider == provider, IdentityRow.subject == subject
                )
            ).scalar_one_or_none()
            user = s.get(UserRow, ident.user_id) if ident else None
            if user is None:
                user = s.execute(select(UserRow).where(UserRow.email == email)).scalar_one_or_none()
            invite = (
                self._live_invitation(s, invitation_id=invitation_id) if invitation_id else None
            )
            if invite is not None and invite.email != email:
                raise AccountError("That invitation was sent to a different email address.")
            if user is None and invite is None and not signup_open:
                raise AccountError("No invitation for this account. Ask an administrator.")
            created = user is None
            if user is None:
                user = UserRow(id=str(uuid4()), email=email, name=name, email_verified=True)
                s.add(user)
                s.flush()
            if user.status != "active":
                raise AccountError("This account is suspended.")
            if ident is None:
                s.add(
                    IdentityRow(
                        id=str(uuid4()),
                        user_id=user.id,
                        provider=provider,
                        subject=subject,
                        email=email,
                    )
                )
            user.email_verified = True
            if not user.name and name:
                user.name = name
            if invite is not None:
                member = s.execute(
                    select(MembershipRow).where(
                        MembershipRow.org_id == invite.org_id, MembershipRow.user_id == user.id
                    )
                ).scalar_one_or_none()
                if member is None:
                    s.add(
                        MembershipRow(
                            id=str(uuid4()), org_id=invite.org_id, user_id=user.id, role=invite.role
                        )
                    )
                invite.accepted_at = now()
                audit(
                    s, actor=user.id, action="invitation.accepted", entity_type="invitation",
                    entity_id=invite.id, org_id=invite.org_id,
                )  # fmt: skip
            s.flush()
            memberships = s.execute(
                select(MembershipRow, OrganisationRow)
                .join(OrganisationRow, OrganisationRow.id == MembershipRow.org_id)
                .where(MembershipRow.user_id == user.id, OrganisationRow.deleted_at.is_(None))
                .order_by(MembershipRow.created_at)
            ).all()
            if not memberships and created and signup_open:
                org = OrganisationRow(
                    id=str(uuid4()),
                    name=f"{(name or email.split('@')[0])}'s organisation"[:200],
                    slug=f"u-{uuid4().hex[:12]}",
                    created_by=user.id,
                )
                s.add(org)
                s.flush()
                s.add(
                    MembershipRow(
                        id=str(uuid4()),
                        org_id=org.id,
                        user_id=user.id,
                        role=Role.ADMIN.value,
                        is_owner=True,
                    )
                )
                audit(
                    s, actor=user.id, action="org.created", entity_type="organisation",
                    entity_id=org.id, org_id=org.id,
                )  # fmt: skip
                org_id = org.id
            elif memberships:
                preferred = invite.org_id if invite else memberships[0][0].org_id
                org_id = preferred
            else:
                raise AccountError("This account does not belong to any organisation.")
            audit(
                s, actor=user.id, action="user.signed_in", entity_type="user", entity_id=user.id,
                org_id=org_id, details={"provider": provider},
            )  # fmt: skip
            return self._user_out(user), org_id


_ORDER = (Role.VIEWER, Role.ANALYST, Role.REVIEWER, Role.ADMIN)


def _rank(role: Role) -> int:
    return _ORDER.index(role)


__all__ = ["DEFAULT_ORG_ID", "AccountError", "AccountService", "hash_secret", "normalise_email"]
