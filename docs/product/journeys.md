# zigzag — Three Journeys and a Minimal Contract

**Date:** 5 October 2026  
**Basis:** The revised zigzag Tenet v0.1, with six tenets.  
**Status:** Proposed behavior, ready for a small prototype.

These are fictional walkthroughs. All briefs, replies, interview notes, and approvals below are fixture data. They make no decisions about any existing project. Expected behavior is specified here; no implementation or user study has yet verified it.

## 1. A clear brief: preserve existing intent

### Input

> Frontend engineers need to understand the required changes for one component-library release without searching across documents. Explore a static migration guide for Button and Input. It will use our changelog and migration documentation. Exclude automated code changes, application scanning, and analytics. The next step is a design brief, not implementation. We have not tested whether a consolidated guide saves time.

This input contains enough direction for the stated next step. Missing release documentation will matter when writing the guide's actual content; it does not prevent a design brief.

### What the harness shows

| Current understanding | Basis |
| --- | --- |
| Outcome: make required migration changes easier to find. | Explicit brief. |
| Audience: frontend engineers upgrading one library release. | Explicit brief. |
| Direction: explore a static guide covering Button and Input. | Explicit brief. |
| Exclusions: code changes, application scanning, analytics. | Explicit brief. |
| Next step: prepare a design brief. | Explicit brief. |
| Uncertainty: a consolidated guide may not save time. | Explicitly untested in the brief. |
| Needed later: release-specific documentation. | Documents are named but not supplied in this fixture. |

The interface offers editing and final review. It asks **zero clarification questions**. It does not ask for a persona, a business case, alternative products, a platform choice, or a measurable target simply to complete a template.

### Illustrative user action and state change

The user reviews the brief and selects **Review and export**.

The supplied directions remain the current intent. Their source is the original brief; their rationale is recorded only where supplied. The exact revision is marked reviewed. The assumption remains untested, and the missing documents remain visible as a later dependency.

### Reviewed handoff

> Prepare a design brief for a static migration guide helping frontend engineers find the required Button and Input changes for one library release. Plan to use the changelog and migration documentation; these still need to be supplied before release-specific content can be written. Exclude automated code changes, application scanning, and analytics. The expected time saving is untested. This handoff supports design exploration; it does not select an implementation stack or commit to building the guide.

**What this journey proves if implemented correctly:** the product can preserve clear intent without adding discovery work. Review is useful even when there are no questions.

## 2. An ambiguous brief: expose a choice and permit deferral

### Input

> Help independent restaurants deal with operational incidents. It should be easy to use and give owners visibility. I don't know whether we need new software or a better process.

The input proposes a broad direction. It does not establish the primary user, the most important moment, or that a new product is needed.

### The question worth asking

> Which improvement should we investigate first? This changes whom we speak to and which incident situations we examine.

| Option | Focus | Trade-off to examine |
| --- | --- | --- |
| Coordination during service | How people respond while an incident is happening. | May introduce work during a busy period. |
| Owner visibility afterwards | How owners understand incidents and follow up. | May leave immediate coordination unchanged. |
| Keep the focus open | Investigate both before choosing. | Requires a broader discovery effort. |

These are proposed directions, not findings about restaurants. The user can choose, write a different direction, or defer. The agent does not preselect a consequential answer.

### Illustrative user reply

> Coordination during service first. Explore shift managers as the primary user. Owner reporting is outside this discovery round. Leave the channel undecided; I want interviews before deciding whether to build software.

This is one clarification question. The user volunteers an audience, boundary, deferral, and next step in their reply. The interface must also support shorter replies; it must not depend on receiving this much detail at once.

### State change

| Item | Result |
| --- | --- |
| Desired outcome | Explore better coordination during service. |
| Intended audience | Shift managers, selected as a discovery focus. Their suitability is unvalidated. |
| Scope | Incident coordination during service; owner reporting excluded from this round. |
| Channel and solution | Still open: existing tools, a process change, or new software. |
| Next step | Interviews before a software commitment. |
| Material assumption | Shift managers may have the authority and availability to coordinate incidents. Agent inference; no supporting evidence supplied. |

The agent does not now ask about SMS, dashboards, authentication, offline storage, or technical feasibility. Those answers do not yet change the selected next step.

### Reviewed handoff

After final review:

> Prepare an interview plan about incident coordination during restaurant service, focusing initially on shift managers. Examine current practices, who notices incidents, who can act, and whether managers can coordinate during busy periods. Owner reporting is outside this round. The suitability of managers as the primary user remains unvalidated. Keep the communication channel and the need for new software open. The next step is learning from interviews, not product implementation.

### If the user defers the focus instead

A reply such as “Keep both possibilities open; I need to understand current practices first” leaves the focus and primary user unresolved. The handoff can support broader discovery. The agent may suggest participants as suggestions, but cannot silently select managers or owners as the product's primary audience.

**What this journey proves if implemented correctly:** useful direction can emerge from one consequential question while other choices remain open. Deferral still produces a useful handoff.

## 3. A changing brief: resolve a conflict without erasing history

This continues journey 2's reviewed handoff. The existing decision excludes owner reporting from the current discovery round.

### New input

> Add owner notifications to this discovery round. Two managers I interviewed reported recurring connectivity loss during service. I want staff to be able to record incidents with no network available, and the remote owner to receive every report immediately, even while the restaurant has no working communication connection.

The interview statement is supplied testimony from a small sample. It provides context; it does not establish how common connectivity loss is across restaurants or validate a solution.

The explicit request reopens owner notifications. The agent can record that change without asking again. It cannot silently decide how to reconcile the two new requirements.

### What the harness shows

> Owner notifications are now part of this discovery round. There is a conflict in the requested behavior: if the restaurant has no working communication connection, it cannot immediately send a new report to the remote owner. Which expectation should we change?

| Option | Consequence |
| --- | --- |
| Keep recording possible without connectivity; notify later. | Remote visibility is delayed until communication becomes available. |
| Require a working connection for immediate notification. | Immediate notification is conditional on connectivity. |
| Leave the requirement open for investigation. | Neither behavior becomes a settled requirement. |

This explains a specific conflict in the supplied wording. It does not claim that offline capture and owner notifications are generally incompatible. The user can also correct the premise or propose another direction.

### Illustrative user reply

> Keep recording without connectivity. The owner can receive reports after connectivity returns. Include delayed owner notifications in the interviews. Keep the channel and technology open.

### Review diff

| Item | Previous reviewed version | New draft |
| --- | --- | --- |
| Owner reporting | Excluded from this discovery round. | Include delayed owner notifications in interviews. |
| Desired recording behavior | Unspecified. | Recording should remain possible without connectivity. |
| Remote delivery expectation | Unspecified. | Delivery can wait until connectivity returns. |
| Channel and technology | Open. | Still open. |
| Manager suitability | Unvalidated. | Still unvalidated. |
| Next step | Interview plan for coordination. | Extend that plan to examine connectivity and delayed notifications. |

The history records the replacement of the exclusion and the reason for the new trade-off when provided. The interview note remains attributed to the user. The previous reviewed handoff stays intact; the working revision is a draft until reviewed.

### Reviewed handoff

> Extend discovery into incident coordination during service and delayed owner notifications. The desired behavior is recording without connectivity, with reports reaching the remote owner after communication returns. Investigate whether this delay is acceptable and how recording would fit staff practices. Connectivity loss has been reported in two supplied interview accounts; prevalence and implementation feasibility remain unknown. Keep channel, technology, and the need for new software open. This direction updates the earlier exclusion of owner reporting. The next step remains interviews and investigation.

If the user defers the conflict, record both expectations as unresolved requests and direct the next step to clarifying them. They must not appear as two compatible, settled requirements in an implementation handoff.

**What this journey proves if implemented correctly:** new evidence and instructions can change scope without automatically settling a trade-off, choosing technology, or losing the prior decision.

## 4. The smallest data contract these journeys require

Use one project record. Its parts below describe information that must survive; they are not separate services, tables, or framework modules.

| Part | Minimum contents | Why it is needed |
| --- | --- | --- |
| `inputs` | Stable reference, supplied text or excerpt, origin, time added. External material includes its locator when available. | Distinguish a user instruction, reported evidence, and an agent inference. Preserve the original wording. |
| `intent` | Current outcome, audience/context, scope, constraints, and next step. Material statements reference the input or decision establishing them. Unknown fields may remain empty. | All three journeys need a readable current direction. |
| `openItems` | A question, assumption, proposal, or possible conflict; its basis, effect on the next step, and options when useful. | Deferral and uncertainty must survive review and export. |
| `decisions` | Human choice, source instruction/action, time, reason if supplied, and the earlier decision it replaces when applicable. | Preserve authority and the reason for changes. Group choices from one instruction when they belong together. |
| `revision` | Identifier for the saved working content. | A later change must not inherit an earlier review. |
| `review` | Reviewed revision, reviewer, and time. | Distinguish a reviewed handoff from a draft. In v0.1 the reviewer is the single local user; this is not verified enterprise identity. |

A source reference explains origin; it does not prove a claim. Support and limitations can initially be short notes alongside relevant statements or open items. These journeys do not require a confidence score or a separate evidence graph.

Proposed consequential changes stay in `openItems` until the user chooses. Direct user instructions can establish `intent` immediately and produce a decision note. Normalized wording must be inspectable and correctable. Final review covers the complete rendered handoff, including any material interpretations introduced during summarization.

Current intent is the source for the displayed brief and export. Decisions explain changes; the application need not reconstruct current state by replaying history. A decision and its corresponding intent change must be saved together.

Retain reviewed exports as fixed copies. For a first prototype, any saved content change makes the working revision a draft; presentation-only changes do not. This conservative rule avoids needing an automated classifier for “material change.” Refine it only if it creates observed review friction.

## 5. The smallest interaction set

Two surfaces are enough to test the proposed behavior:

1. **Working brief:** paste or edit input; inspect the current understanding and open items; answer a focused question with options, free text, or deferral. A conflict uses this same interaction with the conflicting statements shown together.
2. **Review and export:** read the whole handoff, see consequential changes from the last reviewed version, correct them, and mark this revision reviewed. Draft export remains available with an explicit draft label.

The question format adapts to the decision; it does not require a framework that generates interfaces. Use ordinary accessible controls. Compare options where useful and accept direct instructions through text.

The brief can move between draft and reviewed. “Researching” or “waiting for an answer” can be temporary UI states; these examples do not justify a larger persisted workflow state machine.

Export one complete handoff, with a readable version and structured data derived from the same revision. It includes the agreed direction, relevant decision reasons, exclusions, material uncertainties, next step, and review status. These examples do not yet justify separate product, design, and engineering context generators.

## 6. Checks for the first prototype

| Fixture | Expected clarification behavior | Essential check |
| --- | --- | --- |
| Clear brief | No clarification needed. | Existing directions remain intact; the untested benefit and missing later inputs survive export. |
| Ambiguous brief | Ask which improvement to investigate first. Reassess after the answer. | No audience, channel, or software commitment appears without a user choice; the defer branch leaves intent open. |
| Changing brief | Explain the specific conflict and ask which expectation changes. | Preserve the old exclusion, record the explicit revision, and avoid silently choosing a technical solution. |

The one-question paths above depend on the illustrative replies. They are examples, not universal turn limits.

Using only each handoff, a downstream reader should be able to identify the outcome, audience or unresolved audience, exclusions, assumptions, and next step. Journey 3 also requires the reader to explain why owner reporting is now included and why immediate delivery during an outage is not a settled requirement.

Check mechanically that drafts cannot be labeled reviewed, exports match their revision, references resolve, and a decision change is not saved without its matching intent update. Evaluate semantic faithfulness separately: schema validity cannot establish that a summary or inferred conflict is correct.

The prototype should first support journey 1 through export, then journey 2's choice and deferral, then journey 3's revision. Start with these supplied inputs. Add automated research only when a further fixture demonstrates a material question that available external evidence can answer.

**Design conclusion:** one editable intent record, explicit human choices, persistent open items, and a review tied to a revision are enough to prototype the core thesis. A richer ontology or orchestration layer must be justified by a concrete behavior these cannot support.
