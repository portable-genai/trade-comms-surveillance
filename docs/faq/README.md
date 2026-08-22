# FAQ index

Answers to the questions different teams ask when evaluating, adopting or reviewing this
repository as a common base for market-abuse and trade-comms surveillance engines. Each file is
written for a specific audience; skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | server-side identity, the exposure guard, tenant isolation, recorded-comms handling, secrets, supply chain, the audit chain |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | no-lock-in, the three profiles, the sovereign exit, data export |
| [features-faq.md](features-faq.md) | Product / risk / delivery | what the engine detects, what is deterministic, and the boundary with sibling catalog systems |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rename, upstream fixes, extension points, what stays open |
| [compliance-faq.md](compliance-faq.md) | Compliance / surveillance / second line | STOR posture, maker-checker, residency, retention, model-risk evidence |

These FAQs deliberately do **not** re-document capabilities owned by sibling systems in the GRC
catalog. Where a concern belongs to another repo (the restricted-list, blackout and MNPI register
Rgc11, the guardrail gateway Hrz1, the enterprise knowledge base Hrz2, the agent registry Hrz3,
the eval platform Hrz4, observability and WORM audit Hrz5, the human-review console Hrz7), the
FAQ points at it and explains the boundary rather than duplicating it. See
[features-faq.md](features-faq.md) for the full "what this repo owns vs what it integrates" map.

Authority order for anything these pages disagree with: [`SPEC.md`](../../SPEC.md), then
[`ARCHITECTURE.md`](../../ARCHITECTURE.md), then [`COMPLIANCE.md`](../../COMPLIANCE.md), then
[`README.md`](../../README.md). These pages restate; they do not decide.
