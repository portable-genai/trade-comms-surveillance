# Security FAQ

For AppSec and security architecture. Every answer names the file that is the evidence, so the
review can read the control rather than the claim.

### Who is the actor on a decision, and can a caller assert it?

A server-verified `Principal`, always. The request schema has no `actor` field: the audit actor
and the review maker both come from the identity adapter, and every client-supplied actor,
tenant, role, ACL and authorization header is discarded at the browser boundary
(`ui/lib/embed-policy.mjs`). Under the `gcp` profile the adapter verifies the IAP-injected
assertion against the configured audience, against IAP's own key set and against the issuer
(`adapters/gcp/identity.py`); an unset or emptied `TRADECOMMS_IAP_AUDIENCE` REFUSES every caller,
because `audience=None` means google-auth does not verify the audience at all and would accept
any Google-signed token from any project.

### How is tenant isolation enforced?

Server-side, and split deliberately between the store and the domain.
`CaseStorePort.list_for_subject` takes the tenant and MUST filter on it IN THE STORE, so a query
can never span tenants; `CaseStorePort.get` is a raw fetch by id that does NOT filter, and
`domain/kernel.authorize_tenant` compares the stored case's tenant to the VERIFIED principal's
and denies with 403, not 404. Keeping the second check in the domain means every driving surface
inherits it and no single adapter becomes the only place the boundary exists. A client-supplied
tenant is never passed into either method.

### What happens if the profile variable goes missing in production?

The process still binds the SDK-free adapters (the alternative is importing cloud SDKs that are
not installed), but nobody chose them, so every relaxation is withdrawn: the seeded dev personas
refuse to construct, no service-to-service scheme is selected, the dev CORS allowlist and the
`X-Dev-Persona` header are gone, the interactive docs are not registered, and the loopback
exposure guard refuses every route to any non-loopback peer. An emptied or mis-capitalised value
raises AT IMPORT, so the process fails to boot rather than serving on a posture nobody chose
(`config.py`, `tests/unit/test_profile_single_source.py`).

### Does setting the service-to-service token open anything?

No, and this is enforced rather than intended. The exposure guard's posture is derived from the
identity BINDING (the adapter declares `VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`), never
from a credential. `TRADECOMMS_S2S_TOKEN` authenticates a calling SERVICE and no end user.
`tests/unit/test_end_user_auth_posture.py` walks the guard's argument through the constants it
names and fails the build if a credential reappears at any depth, because it did once: setting
the token switched the guard off for the end-user routes it was protecting.

### Can a half-built managed profile be served by accident?

No. Six managed operations in this repo are construction-only placeholders that raise (the three
Firestore case-store methods, the BigQuery market-data window, the managed comms-transcript feed
and the `conflicts-gifts-pad-register` reference snapshot). `src/trade_comms_surveillance/managed_readiness.py` lists them
by name; `assert_managed_profile_ready` refuses to let a `gcp` or `platform` process start when
the bound adapter map selects one of them, and it is called both from the API preflight
(`api/app.py`) and from the container command in the Dockerfile, so it runs before Uvicorn does.
The same fact is mirrored in Terraform: `infra/terraform/managed_readiness.tf` fails the
`managed_profile_is_implemented_before_serving` check whenever `production_edge_enabled` is true,
so the plan describes the hardened edge and refuses to authorise it.

### This system reads recorded employee communications. How is that handled?

It is the most sensitive data surface here, and it is handled in four places rather than one:

- **Redaction before the audit write.** `domain/surveillance_service.py` calls `redact` on the
  summary before the `AuditEvent` is constructed, and the alert-intake path does the same. No raw
  identifier reaches the WORM record.
- **Redaction before anything leaves the process.** `adapters/_review_payload.py` masks against
  EVERY jurisdiction's rows, because the `human-review-console` is a shared sink; `agent/tools.py` masks a
  tool result before it returns.
- **A hit carries a cue, not a person.** `CommsHit` records the matched conduct phrase and its
  turn index, not the surrounding text, so a flagged case does not drag the conversation with it.
- **Nothing content-shaped reaches a trace.** Span attributes in
  `surveillance_service.assess` are structural only. A trace backend has no redaction stage, a
  wider read audience and no retention rule written against a regulator's requirement.

The pattern set and its ORDER are this vertical's (`domain/pii.py`, national rows first,
universal rows last), drawn from the shared `pii-kit`. The `pii_safety` eval metric holds this
at `>= 0.99`, scored two ways (the pack scan plus an independent planted-literal oracle), and
`tests/unit/test_not_falsely_green.py` proves the metric can go red. Note that the deterministic
comms scan runs identically on a redacted or a raw transcript, so redaction costs no detection.

### Can a model exfiltrate or invent anything?

There is no model. No generation port, no narration port, no prompt anywhere in the tree; the
case narrative is a string builder. That is the whole answer today, and
[`../model-card.md`](../model-card.md) records the eight boundary rules any future narration
adapter would have to satisfy, starting with `agent-guardrail-gateway` prompt-injection screening (rule R1) because a
recorded-comms transcript is free text written by the people under surveillance.

### How is the audit trail protected?

Append-only and hash-chained, AND externally anchored. The chain catches an edit, a deletion or a
reorder; only the anchor catches a TRUNCATED TAIL, because dropping the newest rows leaves a
shorter chain that verifies perfectly. `audit_anchor_path` (`TRADECOMMS_AUDIT_ANCHOR`) writes the
chain head to a file on another volume, and `tests/unit/test_audit_anchor.py` proves the
detection, proves the control case goes UNDETECTED without an anchor, and proves an append after
truncation refuses rather than re-anchoring. Under the managed profile the sink is a locked Cloud
Logging bucket (`infra/terraform/logging_worm.tf`), which provides non-rewritability itself.

### What about supply chain?

Both lockfiles are committed and pin every dependency exactly; the catalog commons, including
`speech-lexicon-kit`, are pinned to 40-character COMMIT shas rather than tags, because a
re-pushed tag changes what installs with no diff in the lockfile. The base image is
digest-pinned, Actions are SHA-pinned, dependabot covers pip, docker, github-actions and npm, and
`pip-audit` plus `npm audit --audit-level=high` are HARD CI failures.
`tests/unit/test_repo_artifacts.py` asserts each of these from inside the repo, and it asks git
whether each pinned sha is a COMMIT object rather than an annotated tag object, which a regular
expression cannot tell apart.

### What is deliberately out of scope?

- **Login.** This repo authenticates nobody itself: the platform in front of it does, and the UI
  forwards the assertion without parsing or trusting a parsed copy.
- **Real-time streaming speech to text.** Post-trade review is batch; streaming belongs to the
  real-time verticals, which is why the speech ports are re-exported rather than bound.
- **The restricted list itself.** Owned by `conflicts-gifts-pad-register`; this repo reads a dated snapshot.
- **The review queue and the STOR filing.** Owned by `human-review-console` and by a human; this repo produces
  recommendations and routes them.
- **Network egress control.** VPC-SC governs access to Google APIs across perimeters, not
  arbitrary internet egress. The private-egress rule that lets this service reach the `conflicts-gifts-pad-register` feed
  and the `human-review-console` and nothing else is an adopter network decision, called out in
  `COMPLIANCE.md` P-01.
