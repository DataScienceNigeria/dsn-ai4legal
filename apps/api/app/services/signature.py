"""Who actually collects the signatures.

Two providers behind one interface. DocuSeal where it is configured, and the
internal simulation where it is not. The simulation is not a stub in the
dismissive sense: it exercises the whole control path, binding to an approved
hash, refusing an unapproved one, and completing through the same webhook.
What it does not do is put a document in front of a person outside this
organisation, which is the only part DocuSeal adds.

Cancellation is part of the interface because a signature request that is void
here and live at the provider is worse than no integration at all.
"""

from __future__ import annotations

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


class DocuSealProvider:
    """DocuSeal, through its submissions API.

    The document is sent as the base64 PDF the platform generated, so what the
    counterparty signs is byte-identical to the copy whose hash was approved.
    Sending a template identifier instead would let the provider assemble
    something the approval never bound to.
    """

    name = "docuseal"

    def available(self) -> bool:
        return bool(settings.docuseal_api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Auth-Token": settings.docuseal_api_key,
            "Content-Type": "application/json",
        }

    def issue(
        self, document_name: str, document_hash: str, signers: list[dict], pdf: bytes | None
    ) -> SignatureIssued:
        import base64

        if pdf is None:
            raise ProviderRefused(
                "DocuSeal needs the document itself, and none was rendered."
            )

        submitters = [
            {
                "email": signer.get("email"),
                "name": signer.get("name"),
                "role": signer.get("party", "signer"),
            }
            for signer in signers
            if signer.get("email")
        ]
        if not submitters:
            raise ProviderRefused("No signer with an email address was supplied.")

        body = {
            "send_email": True,
            "documents": [
                {
                    "name": document_name,
                    "file": base64.b64encode(pdf).decode("ascii"),
                }
            ],
            "submitters": submitters,
            "metadata": {"content_hash": document_hash},
        }

        try:
            response = httpx.post(
                f"{settings.docuseal_base_url.rstrip('/')}/submissions",
                json=body,
                headers=self._headers(),
                timeout=60.0,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ProviderRefused(f"DocuSeal refused the request: {exc}") from exc

        entries = payload if isinstance(payload, list) else payload.get("submitters", [])
        reference = str(
            (entries[0].get("submission_id") if entries else None)
            or (payload.get("id") if isinstance(payload, dict) else None)
            or uuid.uuid4().hex[:12]
        )
        return SignatureIssued(
            provider=self.name,
            external_reference=f"DS-{reference}",
            signing_urls={
                str(entry.get("email")): str(entry.get("embed_src") or entry.get("slug") or "")
                for entry in entries
                if isinstance(entry, dict) and entry.get("email")
            },
            detail=f"Sent to {len(submitters)} signers through DocuSeal.",
        )

    def cancel(self, external_reference: str, reason: str) -> str:
        # DocuSeal archives a submission rather than recording why, so the
        # reason stays on the platform's own record and is not sent on.
        del reason
        submission = external_reference.removeprefix("DS-")
        try:
            response = httpx.delete(
                f"{settings.docuseal_base_url.rstrip('/')}/submissions/{submission}",
                headers=self._headers(),
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # The platform record is authoritative, so the local cancellation
            # stands. Saying the provider still holds it is the honest answer.
            logger.warning("DocuSeal would not archive %s: %s", submission, exc)
            return (
                "Cancelled here, but DocuSeal did not confirm. Check the submission "
                "at the provider before treating the link as dead."
            )
        return "Cancelled, and the submission is archived at DocuSeal."


PROVIDERS: dict[str, SignatureProvider] = {
    "internal": InternalProvider(),
    "docuseal": DocuSealProvider(),
}


def selected() -> SignatureProvider:
    provider = PROVIDERS.get(settings.dsnlai_signature_provider)
    if provider is None or not provider.available():
        return PROVIDERS["internal"]
    return provider
