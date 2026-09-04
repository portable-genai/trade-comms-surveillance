# Adoption FAQ

For an engineering lead forking this repo as their firm's surveillance base. The step-by-step is
[`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?" questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the package name (`trade_comms_surveillance`, which is also the
console script), the `TRADECOMMS_` env prefix (including the bare token that
`infra/terraform/render.tf.json` carries as `render_env_prefix`, so Terraform sets the same
variable names on the service), the Terraform `name_prefix` resource stem (`cmp1-svc`) and the
distribution / git id in one pass. Preview with `--dry-run`, apply with `--yes`, then recreate
the venv, `make install`, and run `make gate`. `--resource` is validated against the same
`^[a-z][a-z0-9-]{2,18}$` regex the Terraform variable enforces, so a bad stem fails here rather
than at plan time. The catalog id `trade-comms-surveillance` is left alone unless you pass `--catalog-id`, so a fork
stays traceable to the entry it descends from. The script does the mechanical rename; the human
decisions (threshold pack, lexicon, region, IdP, feeds, eval golden set) are the checklist in
`ADOPTING.md`.

### If several firms fork this, how does each take upstream fixes?

Track upstream via **git tags**. The repo declares a core-vs-adopter-owned boundary
(`ADOPTING.md` section 2): upstream owns `domain/kernel.py`, `ports/` (including the
`speech-lexicon-kit` re-export), `tests/contract/`, the eval harness mechanics, CI and the
Terraform stack; you own `config/settings.yaml` values, your threshold pack file, the lexicon
phrases, the fixture book and golden set, `adapters/onprem/*`, UI theming and
`terraform.tfvars`. Rebase your adopter-owned changes onto each release rather than merging
`main` continuously, so conflicts stay in files you were told to expect.

### What do we have to supply that is not in this repo?

Five things, and the first four are not code here:

1. **Your calibration.** The shipped `rulepacks/surveillance_thresholds.yaml` numbers are
   illustrative. Which abnormal return is suspicious, which cancellation-ratio z-score is
   layering, and how large a self-cross matters are your surveillance function's to set.
2. **Your cue lexicon.** `domain/lexicon.py` ships three obviously illustrative families
   (tipping, collusion, off-channel). A real detection vocabulary is reviewed policy.
3. **The reference data.** `RestrictedReferencePort` reads the restricted-list, blackout and MNPI
   snapshot. Point it at `conflicts-gifts-pad-register` or at your own register. Do not keep a second one here.
4. **The feeds.** A real order and trade warehouse behind `MarketDataPort`, and a real recorded
   comms archive behind `CommsFeedPort`. Offline both are deterministic fictional fixtures.
5. **The review console.** An `human-review-console` deployment reachable at `HUMAN_REVIEW_URL`. The managed
   router REFUSES to swallow an escalation when this is empty, so a fork cannot ship rule R8
   unwired and green.

### The `gcp` adapters raise. How much work is that, really?

Six operations, listed by name in `src/trade_comms_surveillance/managed_readiness.py`: the three
Firestore case-store methods, the BigQuery market-data window, the managed comms-transcript feed
and the `conflicts-gifts-pad-register` reference snapshot. Two things follow. The container command and the API preflight
refuse to start a `gcp` process whose bindings select any of them, and
`infra/terraform/managed_readiness.tf` refuses to authorise the serving edge. That is
deliberate, and in a surveillance engine it is a safety control rather than tidiness: a market
data adapter that returned an empty window instead of raising would score every account as clean.
Empty the tuple and flip `managed_profile_implemented` in the same reviewed commit that lands the
adapters and their integration tests.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list and a contract test that enforces it. A port must be registered in
FIVE places or it runs with no enforcement at all: `ports/__init__.py` (`PORT_PROTOCOLS`),
`config.DEFAULT_BINDINGS`, a `Container` accessor, `config/settings.yaml`, and a `PortCase` in
`tests/contract/canonical.py`. Then bind it in all three families.
`tests/contract/test_port_parity.py` asserts set equality across the five. See
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md). This is also the route a narration seam would
have to take; [`../model-card.md`](../model-card.md) lists the other seven conditions.

### Can I retune detection without touching engine code?

For the detector thresholds, yes, and that is the point of the pack. `PatternThresholds` is
loaded from `rulepacks/surveillance_thresholds.yaml` (or your own file, selected by
`surveillance_pack.path` / `TRADECOMMS_PACK_PATH`) and passed into `score_window` as a parameter,
so retuning is a YAML diff a compliance officer can review. Loading is fail-closed: an unknown
detector, a missing threshold, a rule citing an undefined citation id or a rule with no citation
refuses to start.

What is NOT yet configuration: the `_SEVERITY_KEYWORDS` and `_BAND_DISPOSITION` tables in
`domain/alert_intake_service.py`, the disposition tiering in `domain/surveillance_service.py`,
the proximity weighting, the PII jurisdiction list and the eval thresholds. That is the open B4
item in [`../practices-audit.md`](../practices-audit.md). The pattern to follow already exists in
this repo, which is what makes closing it small.

### Does the gate run for my fork out of the box?

Yes. `make gate` is offline, credential-free and network-free (ruff, ruff format, mypy strict,
the whole suite except integration, and the eval), and the CI workflow references no `secrets.`,
so a fork's build is green immediately. You add secrets only when you wire the `gcp` profile.
Note the eval measures the REFERENCE pack and golden cases until you rebuild them for your own
calibration; that is an explicit adoption step, not a silent pass.

### Will the demo rot after I diverge?

It is guarded, and the guard is inside the gate. A demo step lives in `demo.STEPS` and in
`walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two equal, so a claim the
demo makes but nobody verifies cannot exist. The same test also asserts that every `*.py` in
`scripts/` is described in `scripts/README.md`, so the demo surface cannot silently grow an
undocumented tool. `make demo-selftest` runs the whole arc headless over the real loopback server
and exits non-zero when a claim stops being true; the hosted check runs it and
`make portability` on every pull request and every push to main. If you diverge, keep
the step keys and the `facts` dict the checks read.

### The eval reports 1.000. Should we believe it?

Only because each metric is proved able to report something else.
`tests/unit/test_not_falsely_green.py` wires `agent_eval_kit.assert_each_can_go_red`, which hands
each metric a planted mutant and fails the build if it still passes. A metric that cannot go red
is not a metric, and in surveillance a metric that cannot go red is a gate that waves abuse
through. The scores are also measured against the REFERENCE golden cases, which are synthetic:
rebuilding them for your calibration is adoption step 7.

### What is still open?

[`../practices-audit.md`](../practices-audit.md) carries the per-check verdict and the work list.
The three that matter most before production: implementing the six managed operations, exposing
the market-abuse engine on an HTTP route (today only the alert-intake path has one), and
registering this repo's metric bundle with `model-quality-gate` so `eval/run_eval.py --mode gate` has an
authority to ask. The Terraform stack is written, validated and tested against a mocked provider;
it has never been applied.
