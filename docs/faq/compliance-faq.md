# Compliance FAQ

For compliance, surveillance oversight, model risk and the second line. The mapping table with a
file reference on every row is [`../../COMPLIANCE.md`](../../COMPLIANCE.md); this page answers
the questions that come back after reading it.

### Is a fired signal defensible in front of a regulator?

That is the reason it is pure code. Each of the four detectors is an arithmetic rule over a dated
window, replayable from an explicit `as_of`: the same window plus the same restricted-list
snapshot yields the same signals, the same severity and the same disposition, byte for byte,
years later. No model participates. Three properties matter for a review:

- **The threshold is yours, and the citation is mandatory.** No detector carries a number of its
  own. Every threshold comes from the adopter-owned pack, and every rule in that pack must name
  the regulator instrument it derives from or the loader refuses to start. A fired signal
  therefore states both the calibration it used and the instrument it derives from.
- **The engine never learns a regulator's name.** It reads values and citations. Changing
  jurisdiction is a pack change, not an engine change.
- **Robust statistics, not a mean.** Baseline deviation uses a median / MAD z-score, so a single
  heavy manipulator cannot raise the bar that would have caught them.

The shipped calibration is illustrative and obviously synthetic, not any firm's real numbers.

### Who decides to file a STOR?

A human, always. `Disposition.FILE_STOR` is a RECOMMENDATION, and
`domain/surveillance_service.py` says so in the type's own docstring: the engine never files. A
consequential disposition sets `requires_human_review` and the call to `ReviewRouterPort.route`
happens in the same call that produced it (rule R8), on every surface, with
`tests/unit/test_review_routing.py` asserting the routing rather than the flag. A CRITICAL band
demands two approvals. Under the managed profile the router REFUSES when no console is
configured, so a deployment cannot swallow an escalation silently. The filing itself happens in
Hrz7, by a named person.

### How is the disposition tier decided?

Deterministic policy in one function. A CRITICAL fired signal, or a tipping cue corroborated by a
fired trading signal, recommends `FILE_STOR`. Any other fired signal, or a HIGH or CRITICAL comms
cue on its own, is `ESCALATE`. Nothing fired is `CLOSE`. Note the corroboration rule in the
middle: a tipping cue in a transcript is not by itself a filing recommendation, and a trading
signal is not either; the two together are. That is a policy choice your surveillance function
should review and can change.

### Where does the data live, and is residency enforced or just documented?

Enforced at deploy time. The region is chosen once (`asia-southeast1`) and shared by the runtime
and Terraform: `infra/terraform/variables.tf` validates the region against the residency
allowlist at plan, `org_policy.tf` pins `gcp.resourceLocations` to that region's location group,
and every regional resource (the CMEK key ring, the WORM log bucket, the Cloud Run service) is
created in it. `infra/terraform/production_edge.tftest.hcl` is the standing proof: its
`reject_region_outside_the_residency_allowlist` and `residency_defaults_are_in_country` runs fail
if the allowlist stops refusing or a resource drifts off region, and they run against a mocked
provider so they need no project and no credentials. Recorded employee communications and order
flow are among the most residency-sensitive data a firm holds, so this row usually gets read
first.

### What about key management and least privilege?

One REGIONAL CMEK key with a 90-day rotation, and an explicit key binding for EACH service agent
that encrypts under it, because CMEK does not cascade (`infra/terraform/kms.tf`). One serving
identity holding four roles, each traceable to a bound adapter, with `logging.logWriter` write
only so the process cannot read back the WORM trail it writes (`iam.tf`). Exportable
service-account keys are forbidden by org policy rather than merely avoided, and a key creation
raises an alert if one happens anyway (`org_policy.tf`, `monitoring.tf`).

### How long is the audit trail kept, and can it be edited?

180 days by default, and the variable refuses anything below 180. Surveillance retention
obligations commonly run to five years or more, so this is a floor to raise deliberately rather
than a default to accept. The Cloud Logging bucket is LOCKED by default, which is irreversible:
once applied, retention cannot be reduced and the bucket cannot be deleted for the full window,
not even with project-owner rights. Confirm `retention_days` before the first apply. DATA_READ
audit logging is enabled too, so a read of the evidence is itself recorded, which matters
particularly here: who looked at a colleague's transcripts is its own control question.

Offline the same guarantee is earned differently: the log is hash-chained AND externally
anchored, because a truncated tail leaves a shorter chain that verifies perfectly. The retention
schedule and the legal basis for the trail are adopter-owned.

### What personal data does this system process, and how is it minimised?

More than most systems in this catalog, because recorded employee communications are personal
data about identified individuals, gathered under a conduct mandate. Four controls apply and
they are described with their evidence in
[`security-faq.md`](security-faq.md): redaction before the audit write, redaction before any
outbound review payload or tool result, a `CommsHit` that carries only the matched cue phrase
and its turn index rather than surrounding text, and trace spans whose attributes are structural
only. The `pii_safety` metric holds redaction at `>= 0.99`, scored two ways, and is proved able
to go red. The deterministic comms scan runs identically on a redacted or a raw transcript, so
minimisation costs no detection. The lawful basis, the works-council or employee-representative
consultation and the retention schedule for the recordings themselves are adopter-owned and sit
outside this repo.

### What model-risk evidence exists?

[`../model-card.md`](../model-card.md), and its answer is short: **there is no model**. No
generation port, no narration port, no LLM seam, no prompt, no model SDK import. The case
narrative is a two-branch string builder, and the eval's `groundedness` metric holds it at `1.0`
by rejecting any number in the summary that is not a figure the engine produced. So there is no
model id to pin, no token budget to set and no kill switch to build.

What a second line should review instead is the deterministic policy: the threshold pack, the
lexicon phrases, the disposition tiering and the alert severity bands. The offline eval
(`eval/run_eval.py --mode smoke`) scores `disposition_accuracy`, `review_safety`, `groundedness`
and `pii_safety` on every change against the dataset's own expected outcomes, and every metric is
proved able to go red. If a narration adapter is ever proposed, the model card lists the eight
conditions it must satisfy first, and Hrz1 prompt-injection screening is one of them because a
transcript is free text written by the people under surveillance.

### Which regulations does this claim to satisfy?

None, on your behalf. The mapping in `COMPLIANCE.md` is to the CATALOG's own principles (P-01 to
P-13) and platform rules (R1 to R8), and the instruments the threshold pack cites (MAR Article 8
and Article 12, MAS SFA s197, FCA COBS 11.3) are there to make a fired signal traceable to a
rule, not to assert compliance with it. The crosswalk from those to your own control ids, and the
judgement that a detector is SUFFICIENT coverage for an obligation, is explicitly adopter-owned.
No row in that document should be quoted as regulatory assurance, and the second-line review of
the deterministic policy in `domain/` is firm-owned logic rather than a vendor default to inherit
unexamined.

### What is still open at go-live?

The `Partial` and `TODO (repo owner)` rows in `COMPLIANCE.md`, each of which names exactly what
is missing. The ones that need a risk acceptance if you go live without them: the six
construction-only managed operations in `src/trade_comms_surveillance/managed_readiness.py`
(which the container preflight and the Terraform serving-edge check currently refuse to let you
deploy past), rule R5 and P-08 (the Hrz4 metric bundle), P-10 (timeouts, circuit breaker and a
documented kill switch), the object-level tenant authorisation noted in the cross-cutting table,
and P-01's private-egress rule, which depends on your own network rather than on this repo.
