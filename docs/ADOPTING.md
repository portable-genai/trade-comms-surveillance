# Adopting this repo as your base

This repository (Cmp1, Trade Comms Surveillance) is a **common base** that a bank, broker or
other regulated firm forks to build its own **post-trade market-abuse surveillance engine**: a
service that replays a dated order and trade window against a restricted-list snapshot, scores
four abuse patterns deterministically, scans the recorded comms for conduct cues, links accounts
by trading and comms proximity, and assigns a close, escalate or file-STOR disposition that a
human signs. It ships a reusable hexagonal core (a pure-stdlib domain, typed ports, three
swappable adapter profiles, a green offline gate) plus a fully worked MAR / MAS SFA / FCA COBS
reference calibration you can keep, retune, or replace with your own.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and topology),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding an adapter, adding a port), the
> [`faq/`](faq/) directory, [`model-card.md`](model-card.md) (why there is no model in the
> path, and where a narration seam would go),
> [`practices-audit.md`](practices-audit.md) (the per-check verdict).

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and the surveillance vertical
is a physical module split with an enforced dependency direction (practices-audit check A7).
`domain/kernel.py` owns the vertical-neutral contracts and imports nothing from the vertical, so
you can import it without loading a line of market-abuse logic; `domain/models.py` holds only the
Cmp1 artifacts.

| Layer | Where | For a new surveillance vertical |
|---|---|---|
| **Vertical-neutral machinery** | `domain/kernel.py` (`Citation`, `AuditEvent`, `Severity`, `Decision`, `Disposition`, `utcnow`), every Protocol in `ports/`, the container wiring in `config.py` | keep untouched |
| **Policy (your numbers and words)** | the threshold pack at `src/trade_comms_surveillance/rulepacks/surveillance_thresholds.yaml` (already adopter-owned and selectable by path), the cue phrases in `domain/lexicon.py`, the `_SEVERITY_KEYWORDS` and `_BAND_DISPOSITION` tables in `domain/alert_intake_service.py`, the jurisdiction rows in `domain/pii.py`, the metric thresholds in `eval/run_eval.py` | change deliberately (see section 4) |
| **Vertical (the artifacts themselves)** | the Cmp1 models in `domain/models.py` (`Order`, `Trade`, `MarketWindow`, `RestrictedReference`, `AbuseSignal`, `CommsHit`, `ProximityEdge`, `SurveillanceCase`), the four detectors in `domain/abuse_patterns.py`, `domain/comms_scan.py`, `domain/collusion_graph.py`, the orchestrators (`domain/surveillance_service.py`, `pipeline.py`), the local fixture book replay and the eval golden set | rewrite for your patterns |

If your product is another *replay a dated window, score it deterministically, cite it, escalate
it* gate, most of the hexagon, the three profiles, the fail-closed pack loader, the eval gate and
the Hrz7 review routing transfer directly; you replace the detectors and the reference feeds, and
retune the pack.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): the vertical-neutral machinery listed above, `ports/`
  (including the `speech-lexicon-kit` re-export in `ports/comms.py`), `tests/contract/`, the eval
  harness mechanics (`eval/run_eval.py`), the CI workflows, the hexagon wiring (`config.py`
  `Container`) and the deploy stack in `infra/terraform/`.
- **Adopter-owned** (yours; expect to edit): `config/settings.yaml` *values*, your own threshold
  pack file, the lexicon phrases, the local fixture book and the golden dataset,
  `adapters/onprem/*`, UI theming and branding, `infra/terraform/terraform.tfvars`, and the
  regulator crosswalk section of `COMPLIANCE.md`.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the package name (`trade_comms_surveillance`, which is also the
console script), the `TRADECOMMS_` env prefix (including the bare `TRADECOMMS` that
`infra/terraform/render.tf.json` carries as `render_env_prefix`, so Terraform sets the same
variable names on the Cloud Run service), the cloud resource stem (`cmp1-svc`, the Terraform
`name_prefix`) and the distribution / git id in one pass. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_surveillance --env-prefix ACME \
    --resource acme-surv --dry-run

# Apply:
python scripts/rename_fork.py --package acme_surveillance --env-prefix ACME \
    --resource acme-surv --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

`--dist` defaults to the `--resource` value; pass it explicitly when your git id differs from
your resource stem. `--resource` is validated against the same
`^[a-z][a-z0-9-]{2,18}$` regex the Terraform `name_prefix` variable enforces, so a stem the stack
would refuse fails here instead of at plan time. `--package` must be a valid snake_case Python
identifier. Add `--include-docs` to sweep Markdown prose too; without it the script leaves `.md`
files alone so a code rename stays deterministic. The script skips itself, so the renamer is not
left half-rewritten, and it renames `src/trade_comms_surveillance/` last, after the file contents
are rewritten. The catalog id `Cmp1` is left alone unless you pass `--catalog-id`, so a fork
stays traceable to the entry it descends from. The script deliberately does NOT touch the human
decisions below.

## 4. The human decisions (the script can't make these)

1. **Region / residency.** The build defaults to `asia-southeast1` (MAS / Singapore), chosen once
   and shared: `config/settings.yaml:region`, `infra/terraform/render.tf.json:render_region` and
   the Terraform `region` / `allowed_regions` pair. Set all of them to your in-country region,
   and re-run the residency tests in `infra/terraform/production_edge.tftest.hcl`, which refuse a
   region outside the allowlist at plan time. See [`runbook.md`](runbook.md).
2. **Identity / IdP.** This repo owns no login flow: the `gcp` profile verifies the IAP-injected
   assertion at the edge, `local` uses seeded dev personas, and `onprem` is a client IdP
   placeholder. Wire your issuer on the deployed service (auth is configured ON the service, not
   in this code) and set `TRADECOMMS_IAP_AUDIENCE`. An unset or emptied audience refuses every
   caller rather than verifying without one.
3. **The threshold pack (your detection calibration).** This is the one policy surface that is
   ALREADY configuration rather than code. `rulepacks/surveillance_thresholds.yaml` carries the
   four detectors' numbers (insider `abnormal_return`, spoofing `cancel_ratio_z` plus
   `resting_ms_floor`, wash `min_quantity`, front-running `window_ms`) and the regulator
   instrument each rule cites; point `surveillance_pack.path` (`TRADECOMMS_PACK_PATH`) at your
   own file. The shipped numbers are illustrative, not any firm's real calibration. Keep the
   fail-closed loader behaviour: a missing file, an unknown detector, a missing threshold, a rule
   citing an undefined citation id or a rule with no citation all refuse to start, because a
   surveillance gate on a silently empty pack waves abuse through.
4. **The comms lexicon (your cue phrases).** `domain/lexicon.py` holds the three families
   (tipping, collusion, off-channel) as pack DATA in this repo rather than in the shared
   `speech-lexicon-kit`, because a cue list is reviewed vertical policy that must not need a
   release of a shared package to change. The kit matches; you own the words. The shipped phrases
   are obviously illustrative.
5. **Policy numbers your compliance function owns.** The `_SEVERITY_KEYWORDS` and
   `_BAND_DISPOSITION` tables in `domain/alert_intake_service.py` (the manual-alert path's
   severity bands), the disposition tiering in `domain/surveillance_service.py` (a CRITICAL
   fired signal or a corroborated tipping cue recommends a STOR; anything else fired escalates),
   the proximity weighting in `domain/collusion_graph.py`, the jurisdiction rows and their ORDER
   in `domain/pii.py`, and the eval thresholds in `eval/run_eval.py`
   (`disposition_accuracy`, `review_safety`, `groundedness`, `pii_safety`). Unlike the detector
   thresholds these are still module-level rather than in a `policy:` settings block
   (practices-audit check B4); change them deliberately and add a test that pins your values.
6. **Reference data is fictional.** The offline market-data adapter is a deterministic fictional
   book replay with seeded abuse episodes (`SPOOF.SG`, `INSIDE.SG` and friends), the restricted
   reference and comms feeds are fixture corpora, and `eval/datasets/golden_cases.jsonl` uses
   obviously fake accounts and `.example` domains. Replace them with your own synthetic data.
   **Do not run against real order flow or real recorded comms without your own security, legal,
   privacy and works-council sign-off.** Recorded employee communications are among the most
   sensitive data a firm holds.
7. **Eval golden set.** Rebuild `eval/datasets/golden_cases.jsonl` for your calibration: a fork
   inherits a green gate that measures the WRONG thresholds until you do. The gate structure and
   the strict `pii_safety >= 0.99`, `review_safety == 1.0` and `groundedness == 1.0` metrics are
   generic; the golden cases are yours.
8. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001),
   `infra/terraform/` (Org Policy, CMEK, a dry-run-first VPC-SC perimeter, the locked WORM log
   bucket) and the loopback-by-default binding before you expose anything. The WORM lock is
   irreversible: confirm `retention_days` before the first apply. Note that
   `infra/terraform/managed_readiness.tf` deliberately REFUSES to authorise the serving edge
   while `src/trade_comms_surveillance/managed_readiness.py` still lists construction-only
   managed adapters, and the container command runs the same preflight before Uvicorn starts.
   Emptying that tuple is part of your adoption work, not a flag to flip.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches* are
owned by sibling platform services, and you should integrate rather than rebuild them (see
[`faq/features-faq.md`](faq/features-faq.md) for the full map). The `gcp` profile's adapters are
the seams those integrations switch into:

- **Rgc11** conflicts, gifts and PAD register: the restricted-list, blackout and MNPI reference
  data this engine scores against, over `RestrictedReferencePort`
  (`adapters/gcp/restricted_reference.py`, an A2A client). The reference data is Rgc11's; this
  repo reads a dated snapshot and never keeps a second register.
- **Hrz3** agent registry: this agent publishes its A2A card at
  `/.well-known/agent-card.json`; register it rather than inventing a discovery mechanism.
- **Hrz4** AI-quality / model-risk gate: owns promotion. `eval/run_eval.py --mode gate` is the
  client half (`TRADECOMMS_QUALITY_URL`) and refuses to run off the managed profile; the offline
  smoke mode mirrors the thresholds but never promotes.
- **Hrz5** observability plus immutable WORM audit: audit events and trace spans go to it via
  `AuditSinkPort` and `ObservabilityTracerPort`. The managed tracer exports OTLP to the Hrz5
  collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and to Cloud Trace when it is not. Spans
  carry STRUCTURAL attributes only, never a subject, an instrument or a transcript snippet.
- **Hrz7** human-review / maker-checker console: every consequential case is routed to it over
  the shared `review-kit` (rule R8); you wire your endpoint (`HRZ_HUMAN_REVIEW_URL`), you do
  not re-implement the queue. A STOR is filed by a human from there, never by this service.

The speech boundary is also not this repo's to own: the transcription and diarization ports and
the transcript types come from the pinned `speech-lexicon-kit` and are re-exported through
`ports/comms.py`, so a citation of "turn 7" means the same thing here as in every other repo that
reads recorded comms. Streaming speech to text is deliberately out of scope; post-trade review is
batch.

The guardrail gateway (Hrz1) is **not** integrated, and neither is the enterprise knowledge base
(Hrz2). Neither is engaged today because no model is in the path at all. Hrz1 becomes mandatory
the moment a narration adapter is added and a transcript reaches it: see rule R1 in
[`../COMPLIANCE.md`](../COMPLIANCE.md) and [`model-card.md`](model-card.md).

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Set the region in all three places (settings, `render.tf.json`, tfvars) and re-ran the
      Terraform residency tests.
- [ ] Wired your IdP audience on the deployed service (this repo owns no login flow).
- [ ] Wrote your own threshold pack and pointed `TRADECOMMS_PACK_PATH` at it, keeping the
      fail-closed loader and the mandatory citation per detector.
- [ ] Replaced the cue phrases in `domain/lexicon.py` with your reviewed conduct vocabulary.
- [ ] Pointed `RestrictedReferencePort` at Rgc11 (or your own restricted-list source) and bound
      your real market-data and comms feeds.
- [ ] Owned the remaining policy numbers (alert severity bands, disposition tiering, proximity
      weighting, PII jurisdictions, eval thresholds) with your compliance function.
- [ ] Replaced the fictional book replay and every fixture corpus with your own synthetic data,
      and obtained sign-off before pointing it at real recorded comms.
- [ ] Rebuilt the eval golden set for your calibration.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, `retention_days`, bind address) and
      decided how you will close out `managed_readiness.py`.
- [ ] Wired your Hrz7 review endpoint and confirmed that STOR filing stays a human act there.
- [ ] Read [`model-card.md`](model-card.md) before adding any narration seam.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
