# Features FAQ

For a product owner, a surveillance lead or a delivery manager deciding what this system does,
what it refuses to do, and where its responsibility ends.

### What does it actually detect?

Two paths, both deterministic.

**The market-abuse engine** (`pipeline.assess_instrument` over
`domain/surveillance_service.py`) replays one account and instrument window and produces a
`SurveillanceCase` in five steps:

1. **Market window** (`MarketDataPort`): a dated slice of orders, trades and quotes, so the
   engine scores a replayable window rather than reaching a live feed.
2. **Restricted reference** (`RestrictedReferencePort`): the restricted-list, blackout and MNPI
   snapshot effective at the same `as_of`.
3. **Four detectors** (`domain/abuse_patterns.py`): insider dealing (abnormal return after a
   trade inside a blackout or MNPI window), spoofing and layering (a robust median / MAD z-score
   of an account's cancellation ratio, gated by a resting-time floor), wash trading
   (self-crosses at or above a size floor) and front running (a proprietary order ahead of a
   client order inside a millisecond window). Each fired signal cites the named regulator
   instrument its rule derives from.
4. **Comms scan** (`domain/comms_scan.py` over `CommsFeedPort`): the recorded-comms transcripts
   for the case, matched against three cue families (tipping, collusion, off-channel).
5. **Proximity and disposition**: `domain/collusion_graph.py` scores account pairs by shared
   counterparties and comms co-occurrence, then the service takes the maximum severity and
   assigns a tier.

**The alert-intake path** (`domain/alert_intake_service.py`) is the compact companion: an analyst
logs a free-text conduct alert, pure keyword rules score it into a severity band, a frozen table
maps the band to a disposition, and the same redact-cite-escalate discipline applies. It exists
for the alert an analyst raises before there is a window to replay.

### What is deterministic, and what does a model write?

Everything is deterministic. **There is no model anywhere in this repo**: no generation port, no
narration port, no LLM seam, and no module that imports a model SDK or builds a prompt. Even the
case narrative is a two-branch string builder in `domain/surveillance_service.py`, and the eval's
`groundedness` metric holds it at `1.0` by rejecting any number in the summary that is not a
fired signal's score, a fired signal's threshold or a comms hit's turn index. See
[`../model-card.md`](../model-card.md), which records that fact precisely and says where a
narration seam would go and the eight boundary rules it would have to meet.

### What will it refuse to do?

- **It will not file a STOR.** `Disposition.FILE_STOR` is a RECOMMENDATION. It sets
  `requires_human_review` and is ROUTED to the Hrz7 console in the same call that produced it
  (rule R8). Filing is a human act, always.
- **It will not carry a threshold in the engine.** Every detector number comes from the
  adopter-owned pack, and the loader is fail-closed: a missing file, an unknown detector, a
  missing threshold, a rule citing an undefined citation id or a rule with no citation all refuse
  to start, because a surveillance gate on a silently empty pack waves abuse through.
- **It will not infer a relationship.** Proximity counts shared counterparties and comms
  co-occurrences. No embedding, no similarity score, nothing a case file cannot show its working
  for.
- **It will not put content on a trace.** Span attributes are structural only: never a subject,
  an instrument, a transcript snippet or a fired signal. A trace backend has no redaction stage
  and a wider read audience than the WORM trail.
- **It will not answer across tenants.** `CaseStorePort.list_for_subject` filters on the tenant
  in the store, and `get` is authorised in the domain against the VERIFIED principal's tenant
  with a 403, never a silent 404.
- **It will not answer without provenance.** Every case carries citations, starting with the
  market window itself.

### Which surfaces expose it, and what does each one drive?

Be precise here, because the two paths are not equally exposed:

- The **alert-intake path** is what the FastAPI app (`POST /v1/surveil`), the CLI
  (`trade_comms_surveillance alert`), the agent tool `assess_alert`, the embeddable `ui/`
  micro-frontend and the scripted demo drive.
- The **market-abuse engine** is driven by the CLI (`trade_comms_surveillance surveil
  <instrument>`), the agent tool `assess_window` and the eval harness. It has no HTTP route yet.

Both share `pipeline.py` or the domain service rather than reimplementing anything, and every
surface routes an escalation in the same call that produced it, so rule R8 does not hold on some
surfaces and not others. `verify_audit_trail` is the third agent tool; all three are advertised
on the A2A card at `/.well-known/agent-card.json`.

### What does this repo own, and what does it integrate?

| Concern | Owner | How this repo touches it |
|---|---|---|
| The abuse detectors, the comms scan, the proximity graph and the disposition | **this repo (Cmp1)** | the deterministic engines in `domain/`. Nothing else in the catalog computes them. |
| The surveillance cue lexicon | **this repo (Cmp1)** | `domain/lexicon.py`. The words are reviewed vertical policy and live here deliberately, so changing them needs no release of a shared package. |
| Restricted lists, blackout windows and MNPI reference | **Rgc11** conflicts, gifts and PAD register | read over `RestrictedReferencePort` as a dated snapshot. This repo scores against it; it does not keep a second register. |
| Transcription, diarization and the transcript types | **`speech-lexicon-kit`** (shared commons) | re-exported through `ports/comms.py` so a citation of "turn 7" means the same thing in every repo that reads recorded comms. The kit matches; this repo owns the words. Streaming speech to text is deliberately out of scope; post-trade review is batch. |
| Agent discovery and entitlements | **Hrz3** agent registry | this agent publishes a card; the registry owns discovery. |
| Model and agent promotion | **Hrz4** AI quality and model risk | `eval/run_eval.py --mode gate` asks Hrz4 (`TRADECOMMS_QUALITY_URL`); the offline smoke mode never promotes. |
| Traces and the immutable audit sink | **Hrz5** agent observability | `AuditSinkPort` and `ObservabilityTracerPort`; the managed tracer exports OTLP to the Hrz5 collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. |
| Case review, maker-checker and STOR filing | **Hrz7** human review console | `ReviewRouterPort` over the shared `review-kit` (`HUMAN_REVIEW_URL`). This repo produces recommendations; a human files from there. |
| Prompt-injection defence and output filtering | **Hrz1** agent guardrail gateway | not wired, and not engaged today because no model is in the path. It becomes mandatory the moment a narration adapter is added and a transcript could reach it (rule R1). |
| Grounded retrieval over an enterprise corpus | **Hrz2** enterprise knowledge base | not wired and not in the request path. The regulator instruments this engine cites come from the threshold pack, not from retrieval. |

### Can I demo it without a cloud project?

Yes, and the demo is code rather than a deck. `make demo` runs a presenter-paced walkthrough over
eight steps (opened, routine, escalation, redaction, review queue, audit, tamper, portability) on
its own loopback server; `make demo-selftest` runs the same arc headless and asserts every
narrated claim, so a claim that stops being true fails a build rather than a meeting;
`make demo-static` renders the same audit-first panels to static HTML for screenshots. The
offline market-data adapter is a deterministic fictional book replay with seeded abuse episodes,
so the detectors actually fire.

### What is not built yet?

The honest list is [`../practices-audit.md`](../practices-audit.md) and the `TODO (repo owner)`
rows in [`../../COMPLIANCE.md`](../../COMPLIANCE.md). The three that matter most for a production
decision: the managed adapter family is construction-only (six operations are listed in
`src/trade_comms_surveillance/managed_readiness.py`, and both the container preflight and the
Terraform serving edge refuse while they are), the market-abuse engine has no HTTP route yet, and
the Hrz4 metric bundle is not registered so `--mode gate` has no authority to ask.
