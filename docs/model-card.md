# Model card: Trade Comms Surveillance (Cmp1)

**There is no model in this system.** Not a stubbed one, not an unwired one: this repo has no
generation port, no narration port, no LLM port and no model seam of any kind. The pipeline is
deterministic end to end, and this card exists to record that fact precisely, and to say where a
narration seam would go and what it would have to satisfy before anyone added one.

Verify it rather than take it on trust: `ports/` declares audit, case store, comms, comms feed,
identity, market data, observability, restricted reference and review router, and nothing else.
`ports/comms.py` is the one that looks like it might be a model seam and is not: it re-exports
the shared speech boundary from `speech-lexicon-kit` rather than redeclaring it, and no
recogniser is bound in any profile. No module under `src/trade_comms_surveillance/` imports a
model SDK or builds a prompt.

## What produces every output, then

Pure stdlib, replayable from an explicit `as_of`:

- **The four abuse scores** come from one detector each in `domain/abuse_patterns.py`:
  `detect_insider_dealing` (abnormal return after a trade placed inside a blackout or MNPI
  window), `detect_spoofing_layering` (a robust median / MAD z-score of an account's
  cancellation ratio, gated by a resting-time floor), `detect_wash_trading` (self-crosses at or
  above a size floor) and `detect_front_running` (a proprietary order ahead of a client order
  inside a millisecond window). Every threshold arrives from the adopter-owned pack, never from
  an engine constant, and every fired signal cites the regulator instrument the rule derives
  from.
- **The comms hits** come from `domain/comms_scan.py`, which runs this repo's own lexicons
  through the `speech-lexicon-kit` matching kernel. Deterministic phrase matching, not
  classification. A hit carries the matched cue phrase and its turn index, never surrounding
  personal text.
- **The proximity edges** come from `domain/collusion_graph.py`: shared trading counterparties
  and comms co-occurrences, both COUNTED, never inferred. No embedding, no similarity model.
- **The severity and the disposition** come from `domain/surveillance_service.py`: the maximum
  severity across fired signals and comms hits, then a fixed tier. A CRITICAL fired signal, or a
  tipping cue corroborated by a fired trading signal, recommends `FILE_STOR`; any other fired
  signal or a HIGH comms cue is `ESCALATE`; nothing fired is `CLOSE`.
- **The manual-alert band** comes from `domain/alert_intake_service.py`: pure keyword rules over
  the analyst's free text, mapped to a disposition by a frozen table.

## The case narrative is composed, not generated

`_narrative` in `domain/surveillance_service.py` is a two-branch string builder. It emits either
`"<subject>/<instrument>: no pattern fired; closing."` or the disposition followed by
`"<pattern> score <s> vs <threshold>"` for each fired signal and `"comms:<lexicon>@turn<n>"` for
each hit. Every number in it is, by construction, a figure the engine produced.

That is not merely asserted: `eval/run_eval.py` scores a `groundedness` metric at a threshold of
`1.0` which tokenises every number in the summary and fails the case unless each one is a fired
signal's score, a fired signal's threshold or a comms hit's turn index. It is a fabrication
detector pointed at a string builder today, which sounds redundant and is not: it is the harness
that would keep a narration adapter honest on the day one is added.

## Where a narration seam would go, and what it would have to meet

The seam is `_narrative`, and only `_narrative`. `pipeline.py` already names the constraint in
code: the driving layer redacts comms transcripts with `pii-kit` before anything downstream
could reach a model (P-04), and the docstring on `_comms_hits` records that "a future
model-narration adapter must redact the transcript first". If you add one, these are the
boundary rules it inherits, none of which are optional:

1. **A `NarratorPort` Protocol in `ports/`, registered in all five places.** A port must appear
   in `ports/__init__.py` (`PORT_PROTOCOLS`), `config.DEFAULT_BINDINGS`, a `Container` accessor,
   `config/settings.yaml` and a `PortCase` in `tests/contract/canonical.py`, then bind in all
   three families; `tests/contract/test_port_parity.py` asserts set equality across the five. A
   model reached any other way is a model nobody can swap out or switch off.
2. **It narrates a case the engine has ALREADY decided.** It receives engine facts, never raw
   inputs to reason over. It must not be able to change a score, a severity, a disposition or
   `requires_human_review`, and the offline stub must produce identical consequential fields so
   the determinism the eval measures survives.
3. **Its reply is validated and DISCARDED on failure, never repaired.** The `groundedness`
   scorer above is the specification: every figure it cites must be one the engine produced.
   A failing reply falls back to the deterministic `_narrative`, which is grounded by
   construction.
4. **Untrusted text is screened first (rule R1).** A recorded-comms transcript is the most
   hostile input surface in this catalog: it is free text written by the people under
   surveillance. Bind the Hrz1 guardrail gateway for prompt-injection screening and output
   filtering, and fail closed to deterministic-only when the screen is unavailable.
5. **Redact before the model, not only before the audit write.** Redaction already runs before
   the audit write in `surveillance_service.assess` and before a review payload leaves the
   process in `adapters/_review_payload.py`. A model is a third boundary and needs its own call,
   for the same reason `agent/tools.py` masks tool results.
6. **Nothing content-shaped reaches a span.** `surveillance_service.assess` deliberately keeps
   trace attributes STRUCTURAL: a trace backend has no redaction stage, a wider read audience and
   no retention rule written against a regulator's requirement. A narration adapter must not
   put a prompt or a reply on a span.
7. **It is registered with Hrz4 before promotion (rule R5, P-08).** Add a managed-profile eval
   run that scores narrative groundedness against the same golden cases with the real model
   bound. Note that `adapters/gcp/evaluation.py` and `eval/run_eval.py` already record
   `gemini-3.5-flash` as the model a promotion verdict is keyed to; today that is bookkeeping for
   a model that makes no call, and it would become a real pin that must match what is bound.
8. **A STOR is still filed by a human.** `Disposition.FILE_STOR` is a RECOMMENDATION. It sets
   `requires_human_review` and routes to Hrz7 (rule R8) in the same call. No narration may change
   that, and no narration may be the thing a filing decision rests on.

## What this means for a model-risk review today

There is no model to review, no model id to pin, no token budget to set and no kill switch to
build, because there is nothing to switch off. What a second line should review instead is the
deterministic policy: the threshold pack, the lexicon phrases, the disposition tiering and the
alert severity bands, all of which are named in
[`ADOPTING.md`](ADOPTING.md) section 4 as adopter-owned. The offline eval
(`eval/run_eval.py --mode smoke`) scores `disposition_accuracy`, `review_safety`, `groundedness`
and `pii_safety` on every change against the dataset's own expected outcomes, and
`tests/unit/test_not_falsely_green.py` proves each metric can go red.

Note separately that the managed adapter family is construction-only for six operations
(`src/trade_comms_surveillance/managed_readiness.py`), which is a deployment fact rather than a
model-risk one; the API preflight, the container command and
`infra/terraform/managed_readiness.tf` all refuse the managed serving path while it is.
