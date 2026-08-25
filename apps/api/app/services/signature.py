"""Who actually collects the signatures.

Two providers behind one interface. Self-hosted OpenSign where it is
configured, and the internal simulation where it is not. The simulation is not
a stub in the dismissive sense: it exercises the whole control path, binding to
an approved hash, refusing an unapproved one, and completing through the same
webhook. What it does not do is put a document in front of a person outside
this organisation, which is the only part OpenSign adds.

Cancellation is part of the interface because a signature request that is void
here and live at the provider is worse than no integration at all.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ProviderRefused(RuntimeError):
    """The signature provider would not accept the request."""


@dataclass
class SignatureIssued:
    provider: str
    external_reference: str
    signing_urls: dict[str, str] = field(default_factory=dict)
    detail: str = ""


class SignatureProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def issue(
        self, document_name: str, document_hash: str, signers: list[dict], pdf: bytes | None
    ) -> SignatureIssued: ...

    def cancel(self, external_reference: str, reason: str) -> str: ...

    def state_of(self, external_reference: str) -> dict | None:
        """Where a request has got to, for a provider that cannot call back.

        Optional. A provider that pushes completion does not implement it, and
        the sweep asks the question of whoever answers.
        """
        del external_reference
        return None


class InternalProvider:
    """The built-in simulation.

    It issues a reference and nothing else leaves the platform. Completion
    arrives through the same signed webhook a real provider would call, so the
    archive path is the one that runs in production.
    """

    name = "internal"

    def available(self) -> bool:
        return True

    def issue(
        self,
        document_name: str,
        document_hash: str,
        signers: list[dict],
        pdf: bytes | None,
    ) -> SignatureIssued:
        # The arguments are part of the interface every provider implements.
        # This one reaches nothing, so it uses none of them, and says so here
        # rather than by silently dropping them from the signature.
        del document_name, document_hash, signers, pdf
        return SignatureIssued(
            provider=self.name,
            external_reference=f"SIG-{uuid.uuid4().hex[:12]}",
            detail=(
                "Issued internally. No external signing service is configured, so "
                "nothing was sent to the signers."
            ),
        )

    def cancel(self, external_reference: str, reason: str) -> str:
        del external_reference, reason
        return "Cancelled. Nothing had been sent, so there is nothing to withdraw."


class OpenSignProvider:
    """Self-hosted OpenSign, Parse Server behind a small REST surface.

    DocuSeal was configured here first and could not do the job. Its free
    self-hosted edition answers 404 with a link to its pricing page on every
    route that accepts a document, from PDF, DOCX or HTML, and its Alpine image
    ships no converter, so nothing could reach it and nothing could be turned
    into something signable. OpenSign is AGPL-3.0 with no feature gate in the
    self-hosted build and carries LibreOffice.

    Three calls per request, and each is there for a reason.

    The document is converted from the .docx the platform rendered, not from a
    file uploaded beside it, because the .docx is built from the blocks the
    content hash was computed over. Convert anything else and the counterparty
    signs something the approval did not bind to.

    Parse authenticates cloud functions as a user rather than by API key, so
    the platform holds one account on the signing service and the session it
    returns is cached until it is refused. A session per signature request
    would be a login per agreement.
    """

    name = "opensign"

    def __init__(self) -> None:
        self._session: str | None = None
        self._identity: tuple[str, str] | None = None

    def available(self) -> bool:
        return bool(settings.opensign_email and settings.opensign_password)

    def _root(self) -> str:
        return settings.opensign_base_url.rstrip("/")

    def _origin(self) -> str:
        """The server root, without the Parse mount.

        The converter is an ordinary Express route on the server itself rather
        than a Parse function, so it sits above the mount point.
        """
        root = self._root()
        return root.rsplit("/", 1)[0] if root.endswith("/app") else root

    def _headers(self, session: str | None = None) -> dict[str, str]:
        headers = {"X-Parse-Application-Id": settings.opensign_app_id}
        if session:
            headers["X-Parse-Session-Token"] = session
        return headers

    def _login(self, force: bool = False) -> str:
        if self._session and not force:
            return self._session
        try:
            response = httpx.post(
                f"{self._root()}/login",
                json={
                    "username": settings.opensign_email,
                    "password": settings.opensign_password,
                },
                headers={**self._headers(), "Content-Type": "application/json"},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderRefused(
                f"The signing service would not accept the platform's credentials: {exc}"
            ) from exc

        token = response.json().get("sessionToken")
        if not token:
            raise ProviderRefused("The signing service returned no session.")
        self._session = token
        return token

    def _who(self, session: str) -> tuple[str, str]:
        """The account this platform signs as, and its extended record.

        Parse keeps the login and the application's own user profile in two
        classes, and the document creation function wants both. Read once per
        session rather than per request.
        """
        if self._identity:
            return self._identity
        try:
            me = httpx.get(
                f"{self._root()}/users/me", headers=self._headers(session), timeout=30.0
            )
            me.raise_for_status()
            user_id = me.json()["objectId"]

            # Through the function the service provides rather than by
            # querying the class. Its cloud functions are registered in
            # lowercase whatever the file calls them, which Parse matches
            # exactly, and the casing is not consistent between them:
            # getUserDetails is registered as written, createdocumentfromapp
            # and declinedoc are lowered. Each name here is the one the server
            # registers, not the one its file is called.
            #
            # The class itself denies a session query outright, and reaching
            # for the master key to get round that would hand every document
            # on the service to this one integration.
            found = httpx.post(
                f"{self._root()}/functions/getUserDetails",
                json={},
                headers={**self._headers(session), "Content-Type": "application/json"},
                timeout=30.0,
            )
            found.raise_for_status()
            profile = (found.json() or {}).get("result") or {}
            if not profile.get("objectId"):
                raise ProviderRefused(
                    "The signing service has no profile for the platform's account. "
                    "It needs one before it will accept a document."
                )
        except httpx.HTTPError as exc:
            raise ProviderRefused(f"The signing service would not identify us: {exc}") from exc

        self._identity = (user_id, profile["objectId"])
        return self._identity

    def _to_pdf(self, session: str, document_name: str, docx: bytes) -> str:
        """The .docx as a stored PDF, converted by the signing service.

        A signature is applied to a PDF. Converting here rather than asking
        anybody to attach one keeps the signed document derived from the same
        blocks the content hash was computed over: attach a PDF made elsewhere
        and the counterparty signs something the approval never bound to.

        The service stores the result and answers with a signed URL, so there
        is no separate upload. It authenticates by session header rather than
        by the Parse headers the rest of the API uses, which is its own
        convention and not a mistake in the call.
        """
        try:
            response = httpx.post(
                f"{self._origin()}/docxtopdf",
                files={
                    "file": (
                        f"{document_name}.docx",
                        docx,
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document",
                    )
                },
                headers={"sessiontoken": session},
                timeout=300.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderRefused(f"The document could not be converted: {exc}") from exc

        url = (response.json() or {}).get("url")
        if not url:
            raise ProviderRefused("The converter stored no document.")
        return str(url)

    def _contact(self, session: str, tenant: str | None, signer: dict) -> dict:
        """A signer as a record the service can point at.

        Signers cannot be inline objects. The document's after-save hook walks
        them to build the access list and reads objectId off each one, so a
        plain {name, email} crashes the hook, and the crash takes the Node
        process with it: the API answered 201 while the server behind it died.
        Each signer is saved to the contact book first and referenced.
        """
        email = signer.get("email")

        # Look first. The service refuses a duplicate rather than answering
        # with the record that already exists, and the same person signs more
        # than one agreement, so creating blind fails on the second one.
        object_id = self._find_contact(session, email)

        if object_id is None:
            try:
                response = httpx.post(
                    f"{self._root()}/functions/savecontact",
                    json={
                        "name": signer.get("name") or email,
                        "email": email,
                        **({"tenantId": tenant} if tenant else {}),
                    },
                    headers={**self._headers(session), "Content-Type": "application/json"},
                    timeout=60.0,
                )
                response.raise_for_status()
                contact = (response.json() or {}).get("result") or {}
                object_id = contact.get("objectId") or (contact.get("contact") or {}).get(
                    "objectId"
                )
            except httpx.HTTPError as exc:
                # Two requests for the same new signer can race, and the loser
                # is told the contact exists. Looking again answers it.
                object_id = self._find_contact(session, email)
                if object_id is None:
                    raise ProviderRefused(
                        f"The signer {email} could not be recorded: {exc}"
                    ) from exc

        if not object_id:
            raise ProviderRefused(f"The signing service returned no record for {email}.")
        return {
            "__type": "Pointer",
            "className": "contracts_Contactbook",
            "objectId": object_id,
        }

    def _find_contact(self, session: str, email: str | None) -> str | None:
        """The contact record for this address, if the account already has one."""
        if not email:
            return None
        try:
            response = httpx.get(
                f"{self._root()}/classes/contracts_Contactbook",
                params={
                    "where": json.dumps({"Email": email}, separators=(",", ":")),
                    "limit": 1,
                },
                headers=self._headers(session),
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        results = (response.json() or {}).get("results") or []
        return results[0].get("objectId") if results else None

    def _tenant(self, session: str) -> str | None:
        """The service's own grouping for this account, where it reports one.

        Optional, and treated as optional. It only tags the contact records
        this integration creates; nothing about sending a document depends on
        it. The service answers an empty result here even with a tenant set on
        the profile, which is its own lookup to worry about, and refusing to
        send an agreement over a tag would be the wrong thing to fail on.
        """
        try:
            response = httpx.post(
                f"{self._root()}/functions/gettenant",
                json={},
                headers={**self._headers(session), "Content-Type": "application/json"},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("The signing service did not report a tenant: %s", exc)
            return None
        found = (response.json() or {}).get("result") or {}
        tenant = found.get("objectId") or (found.get("tenant") or {}).get("objectId")
        return str(tenant) if tenant else None

    def issue(
        self, document_name: str, document_hash: str, signers: list[dict], pdf: bytes | None
    ) -> SignatureIssued:
        if pdf is None:
            raise ProviderRefused(
                "The signing service needs the document itself, and none was rendered."
            )

        wanted = [s for s in signers if s.get("email")]
        if not wanted:
            raise ProviderRefused("No signer with an email address was supplied.")

        session = self._login()
        user_id, profile_id = self._who(session)
        tenant = self._tenant(session)
        contacts = [self._contact(session, tenant, signer) for signer in wanted]
        url = self._to_pdf(session, document_name, pdf)

        payload = {
            "document": {
                "Name": document_name,
                "URL": url,
                "ExtUserPtr": {
                    "__type": "Pointer",
                    "className": "contracts_Users",
                    "objectId": profile_id,
                },
                "CreatedBy": {
                    "__type": "Pointer",
                    "className": "_User",
                    "objectId": user_id,
                },
                "SendinOrder": False,
                "SentToOthers": True,
                "NotifyOnSignatures": True,
                "Signers": contacts,
                # Carried so a completion callback can be matched back to the
                # document that was approved, rather than by name.
                "Note": f"content_hash={document_hash}",
            }
        }

        try:
            response = httpx.post(
                f"{self._root()}/functions/createdocumentfromapp",
                json=payload,
                headers={**self._headers(session), "Content-Type": "application/json"},
                timeout=120.0,
            )
            if response.status_code in (401, 403):
                session = self._login(force=True)
                response = httpx.post(
                    f"{self._root()}/functions/createdocumentfromapp",
                    json=payload,
                    headers={**self._headers(session), "Content-Type": "application/json"},
                    timeout=120.0,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderRefused(f"The signing service refused the request: {exc}") from exc

        created = response.json().get("result", {})
        reference = str(created.get("objectId") or uuid.uuid4().hex[:12])
        return SignatureIssued(
            provider=self.name,
            external_reference=f"OS-{reference}",
            signing_urls={},
            detail=f"Sent to {len(wanted)} signers through OpenSign.",
        )

    def placement_session(self) -> dict | None:
        """A session on the signing service, for a browser rather than for us.

        The placement screen is theirs and reads its session from the browser's
        own storage, which is per-origin: a page on this platform cannot write
        into theirs. Serving their client through this origin and seeding the
        session here is what removes the second login, and this is the part
        the server has to hand over.

        The session belongs to the platform's single account, so what it
        grants is exactly what this integration already has. It is not a
        credential for the person placing the fields, and the platform's own
        audit trail is what names them.
        """
        session = self._login()
        try:
            me = httpx.get(
                f"{self._root()}/users/me", headers=self._headers(session), timeout=30.0
            )
            me.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Could not open a placement session: %s", exc)
            return None

        user = me.json()
        return {
            "session_token": session,
            "app_id": settings.opensign_app_id,
            "server_url": settings.opensign_base_url.rstrip("/"),
            "user": user,
        }

    def state_of(self, external_reference: str) -> dict | None:
        """What the signing service now says about one request.

        Polled rather than pushed, and not by preference. The self-hosted
        image carries no outbound webhook: the feature exists on the hosted
        service and there is no dispatcher anywhere in the container, so
        nothing will ever call this platform to say a document was signed.
        Waiting for a callback that cannot arrive would leave every executed
        agreement unrecorded.

        Polling is also the safer half of the trade. A missed callback is
        silent and permanent; a missed poll is retried in ten minutes.
        """
        document = external_reference.removeprefix("OS-")
        session = self._login()
        try:
            response = httpx.post(
                f"{self._root()}/functions/getDocument",
                json={"docId": document},
                headers={**self._headers(session), "Content-Type": "application/json"},
                timeout=60.0,
            )
            if response.status_code in (401, 403):
                session = self._login(force=True)
                response = httpx.post(
                    f"{self._root()}/functions/getDocument",
                    json={"docId": document},
                    headers={**self._headers(session), "Content-Type": "application/json"},
                    timeout=60.0,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Could not read %s from the signing service: %s", document, exc)
            return None

        found = (response.json() or {}).get("result") or {}
        if not found:
            return None

        if found.get("IsCompleted"):
            status = "completed"
        elif found.get("IsDeclined"):
            status = "declined"
        else:
            status = "sent"

        return {
            "status": status,
            "certificate": {
                "provider": self.name,
                "signed_url": found.get("SignedUrl"),
                "certificate_url": found.get("CertificateUrl"),
                "audit_trail": found.get("AuditTrail") or [],
                "completed_at": found.get("updatedAt"),
                "signers": found.get("Signers") or [],
            },
        }

    def cancel(self, external_reference: str, reason: str) -> str:
        document = external_reference.removeprefix("OS-")
        session = self._login()
        try:
            response = httpx.post(
                f"{self._root()}/functions/declinedoc",
                json={"docId": document, "reason": reason},
                headers={**self._headers(session), "Content-Type": "application/json"},
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # The platform's own record is already void. Saying the provider
            # still shows it as live is more use than a failure.
            logger.warning("OpenSign would not withdraw %s: %s", external_reference, exc)
            return (
                "Cancelled here. The signing service still shows it as live and may "
                "need withdrawing there."
            )
        return "Withdrawn at the signing service."


PROVIDERS: dict[str, SignatureProvider] = {
    "internal": InternalProvider(),
    "opensign": OpenSignProvider(),
}


def selected() -> SignatureProvider:
    provider = PROVIDERS.get(settings.dsnlai_signature_provider)
    if provider is None or not provider.available():
        return PROVIDERS["internal"]
    return provider
