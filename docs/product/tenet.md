# zigzag tenet v0.1

**Status:** Current · **Revised:** 2026-10-05, after adversarial review · **Purpose:** a working foundation for product and architecture decisions · **Scope:** one person turning an idea or brief into reviewed intent

> zigzag helps people decide what to pursue and why, keeping evidence, assumptions, and human choices visible to downstream work.

## The problem and the boundary

An agent can turn an ambiguous brief into a convincing plan while silently choosing the audience, scope, or priorities. zigzag makes those choices visible and gives the user a useful way to resolve them.

The result is a concise account of the desired outcome, intended users and circumstances, scope and constraints, decisions and their reasons, and remaining uncertainty. Unknown information stays unknown. This account can inform a PRD, design brief, experiment, technical proposal, or coding agent.

Intent is reviewed for the immediate next step, which may be learning rather than building. It need not settle the whole project in advance.

v0.1 covers intake, selective clarification or research, human decisions, review, and export. It prepares the handoff and does not execute it; the receiving person or system remains responsible for following the handoff's boundaries. Research automation is added only where a demonstrated gap needs it. Collaboration, downstream execution, cross-project memory, and platform extensibility remain outside this release.

## Six tenets

### 1. Understand the situation enough to question the proposed solution.

Identify the desired outcome, who is involved, and what happens today, and keep these distinguishable from proposed features. If the user brings a solution, work from it and test its important premises. Do not force every project through discovery from the beginning.

### 2. Keep evidence, assumptions, and choices distinguishable.

Show where a material assertion came from and whether its support is missing or limited. A source may support an assertion without proving it. An AI suggestion remains a suggestion until selected. Accepting an assumption permits reliance on it; it does not validate it.

Use the detail needed to understand the decision. A complete classification of every sentence is unnecessary.

### 3. Let the human own changes to consequential intent.

The agent may organize context, investigate questions, propose options, and recommend a direction. It must obtain an explicit human choice before establishing or changing the intended outcome, primary audience, scope, hard constraints, or a material trade-off.

An explicit user instruction already counts as a choice: record it without asking again. Recommendations and silence do not count. Routine edits that preserve meaning can happen automatically; ambiguous changes remain proposals.

### 4. Make questions and alternatives earn the user's attention.

Ask when the answer would change a decision or the next useful investigation, and show what would change. Investigate factual gaps when available evidence can answer them; acknowledge when observation, an experiment, or specialist input is needed.

Offer alternatives when a real choice remains. Do not invent competing options for an existing commitment or an obvious constraint. Ask the smallest useful set of questions, then reassess. A fixed question count is a UX hypothesis to test, not a foundational rule.

### 5. Permit a useful handoff with unresolved uncertainty.

State what has been chosen, what remains open, and what the next step may rely on. Material assumptions must remain visible. If a gap prevents the intended next step, resolve it, narrow that step, or make learning the next step.

The agent flags possible conflicts; the human resolves their meaning and effect. Do not present mutually exclusive choices as simultaneously settled. A suspected conflict is not an automatic veto on further work. Drafts can be saved and shared with their status visible.

### 6. Preserve reasons and make revision explicit.

Keep enough context to explain a consequential choice: what was chosen, who chose it, why when known, and relevant evidence or acknowledged gaps. Do not invent a rationale when none was given.

When a choice changes, show the change and retain the previous decision. New evidence may prompt reconsideration; it must not silently replace the user's choice. A reviewed handoff identifies its version. Later material edits create a draft until reviewed again.

## The minimum experience

The experience runs understand → resolve what matters → review and hand off, repeating any part when needed:

1. The user supplies an idea or brief.
2. zigzag presents a short account of its understanding and the few uncertainties that matter.
3. The user corrects it or makes the necessary choices.
4. zigzag produces a reviewable handoff containing the agreed direction and remaining uncertainty.

The handoff has one final review; separate frame and decision approval gates are not required. Choices can be recorded along the way, through direct instructions or suitable controls. Review establishes the direction for a stated next step, not proof that the product will succeed.

A simple distinction must survive the whole experience:

| Item | Meaning |
| --- | --- |
| “Managers will adopt a separate incident tool.” | An assumption unless relevant evidence supports it. |
| “Explore managers as the first audience.” | A human choice about direction. |
| “Interview managers before committing to implementation.” | A next step that addresses the uncertainty. |

These are illustrative statements, not decisions about an existing project.

## Use prior work as guidance

Use Jobs to Be Done (JTBD) to examine progress and circumstances, product discovery to investigate risks and distinguish outcomes from solutions, divergence and convergence to explore real alternatives, and usability principles to make decisions understandable and recoverable. Questions about incentives, power, harm, and context matter when they could change a decision.

These are available perspectives, not mandatory stages, schema categories, or separate agents. A perspective shows its usefulness through a better question, option, or decision, and no project must complete every framework.

Selected foundations retained from the original research:

- [Cagan: discovery judgment](https://www.svpg.com/discovery-judgement/) — adjust effort to risk and consequence.
- [Torres: Opportunity Solution Trees](https://www.producttalk.org/opportunity-solution-trees/) — distinguish outcomes, opportunities, solutions, and tests.
- [Christensen Institute: Jobs to Be Done](https://www.christenseninstitute.org/theory/jobs-to-be-done/) — examine progress in particular circumstances.
- [Design Council: Framework for Innovation](https://www.designcouncil.org.uk/resources/framework-for-innovation/) — explore, focus, and revisit understanding.
- [Nielsen: usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) — make status and user control clear.

These references inform the choices here; they do not establish the effectiveness of zigzag.

## What architecture must preserve

There must be a consistent account of current intent, supporting context, unresolved issues, and human decisions. Views and exports must agree about what is current and whether it has been reviewed. The agent cannot silently promote a proposal into a human commitment.

This does not prescribe an epistemic graph, an event log, seven entity types, a workflow engine, or a generated-interface registry. Choose representation and controls from the first complete user journey. Add an abstraction only when a concrete behavior needs it and a simpler representation is insufficient.

## What must be demonstrated next

Walk three briefs through the experience before fixing the schema or component set. [journeys.md](journeys.md) walks through each one.

1. In a clear brief, existing choices carry through without needless questions.
2. In an ambiguous brief, a consequential choice becomes explicit and the user can defer it.
3. In a changing brief, conflicting constraints are examined, a prior choice is revised, and unresolved assumptions survive the handoff.

For each, verify that the agent introduces no unchosen consequential commitment, preserves uncertainty and decision changes, and exports an account that a downstream reader can interpret correctly. Ask that reader to identify the outcome, audience, exclusions, remaining assumptions, and permitted next step.

Also check whether the questions changed anything useful. Record failures before setting numerical quality targets. Passing examples is a starting point for evaluation, not proof of product value.

The foundation is sufficient when these behaviors are clear. Detailed taxonomies, persistence design, interaction types, research budgets, and release metrics belong to the next design work and must earn their complexity there.

---

## Adversarial review record

The review judged the core proposition worth retaining, and found the original draft's main weakness to be premature prescription. This revision makes the behavioral boundary explicit while leaving implementation decisions open.

The record explains the revision and adds no product requirements. References in parentheses, such as §3 and I11, point to the original draft.

| Finding | Why it mattered | Revision |
| --- | --- | --- |
| Architecture was embedded in doctrine (§§3, 4, 9). Seven entities, eight relationship types, several classification dimensions, and a UI registry were already prescribed. | Conceptual distinctions would likely become implementation obligations before evidence showed they were needed. | Preserve observable behavior; derive representation from concrete journeys. |
| The authority boundary was underspecified (§§2, 6). “Consequential” carried much of the policy without an operational test. | Implementers could either ask for everything or silently decide what mattered. | Name the affected commitments: outcome, audience, scope, hard constraints, and material trade-offs. Ambiguous changes stay proposals. |
| Attention protection conflicted with ceremony (§§4–6). Three gates, compulsory alternatives, and extensive records applied even to existing human decisions. | Correctly supplied intent could trigger unnecessary questioning or invented explanations. | Accept explicit instructions, use alternatives selectively, record missing rationale honestly, and review the final handoff once. |
| Epistemic categories overlapped (§3). Hypothesis and assumption were acknowledged to overlap; “approved” also applied to both claims and choices. | More classifications did not guarantee clearer reasoning. | Keep support, reliance, and human choice distinguishable without requiring a universal taxonomy. |
| Drafts were missing from an absolute rule (I11). All views and contexts were required to refer to an approved version. | Users need unapproved views to review work in the first place. | Permit labeled drafts; reviewed exports identify a specific version. |
| Conflict handling implied too much certainty (I8). Incompatible commitments could not be finalized, but semantic conflict detection was unspecified. | An agent's suspicion could become a veto; a missed contradiction could imply false assurance. | Surface possible conflicts for interpretation. Do not claim exhaustive detection or export acknowledged incompatible choices as settled. |
| A UX guess became an invariant (I6). Five initial questions was a hard requirement without supporting user evidence. | Question count could displace relevance and encourage round-based workarounds. | Minimize useful questions; determine budgets through evaluation. |
| “Before execution” invited excessive upfront certainty (§1), despite allowing experiments and evolving intent elsewhere. | Teams could read the doctrine as requiring project-wide commitment before learning through doing. | Review intent for the next step, which may be an experiment. zigzag's own execution boundary remains narrow. |
| Foundations became feature candidates (§§7–10). Numerous lenses, controls, history requirements, and proof obligations accumulated. | Breadth could take priority over testing the distinctive behavior. | Retain selected references, six tenets, and three end-to-end examples. Defer machinery until a concrete need appears. |
