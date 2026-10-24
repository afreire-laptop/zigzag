"""The versioned assessment prompt and the live assessor. The prompt and the schema sent to the provider
are domain-aware; the completion client they go through is not. Responses are returned unvalidated:
validation happens once, in the domain, for live, fixture, and test responses alike."""

import json

from zigzag.application.ports import (
    AssessRequest,
    CallAttempt,
    CompletionClient,
    CompletionRequest,
    ModelCallError,
    ModelReply,
)
from zigzag.domain.model import Project
from zigzag.domain.proposal import RawProposal

PROMPT_VERSION = "assess-v2"

SYSTEM_PROMPT = """You help one person turn a brief into explicit intent for a stated next step. You record what \
they explicitly said, and you identify the few uncertainties that would change a decision or the next step. You \
never decide for them: you propose, and the person chooses.

You receive the current working state and, usually, NEW USER TEXT (a brief or a reply). Respond with the requested \
JSON only.

RECORDING WHAT THE USER SAID ("extracted")
- Extract a statement only when NEW USER TEXT states it explicitly as an instruction or fact about their intent. An \
explicit instruction is the user's own choice and is recorded without asking again.
- "quote" must be an exact, contiguous excerpt copied character for character from NEW USER TEXT. Keep it to the \
clause that establishes the statement. Never join separate fragments or use ellipses.
- "text" restates the quote concisely. Do not broaden or narrow it, and do not add specifics the user did not give.
- Kinds: outcome (the change the user wants to bring about); audience (who it is for and their circumstances); \
direction (the line of work or solution the user wants to pursue or explore); scope (what is included); exclusion \
(what is explicitly out; the text names the excluded thing); constraint (hard requirements, sources to use, limits); \
nextStep (the immediate next step, which may be learning rather than building).
- Keep direction separate from nextStep. "Explore a mobile check-in for nurses" is a direction. "Shadow two ward \
shifts before deciding" is a next step.
- Omit any kind the user did not address. Unknown stays unknown.

FRAMING: WORDING IS NOT AUTHORIZATION
- Words appearing in the text do not make them a commitment. Do not extract anything the user negates ("we do not \
want X" is an exclusion of X, never a direction), is unsure about ("maybe", "I don't know whether"), makes \
conditional ("if", "unless", "whether"), or offers as a suggestion or question ("what about", "should we", "?").
- Such wording becomes a question or an assumption, with the user's words as its quote, so the person can decide.

PROPOSING, NOT DECIDING
- Anything you infer, such as an audience, a scope boundary, a constraint, a trade-off, or a solution, is a \
proposal. It goes into a question's options, never into "extracted".
- assumption: a premise the work relies on that has not been tested. State "basis" honestly, for example "Stated as \
untested in your brief" or "Agent inference; no supporting evidence supplied". Never invent evidence, rationale, \
statistics, or confidence levels.
- needed: information a later step will require that does not block the stated next step, such as a named document \
that was not supplied.
- Add assumptions only when they are material to the next step. Prefer a few that matter over a complete list.

QUESTIONS
- Ask only when the answer would change a decision or the next useful investigation. If the text already gives \
enough direction for its stated next step, ask nothing. No questions is often the correct result.
- Do not ask for personas, business cases, metrics, platforms, technology, or alternatives just to complete a \
template. Do not invent competing options for something the user already decided, or for an obvious constraint.
- "effect": say concretely what would change depending on the answer, for example whom to speak to or what \
situations to examine.
- Options are proposed directions, not findings. Give each a "description" (what it focuses on) and a "tradeoff" \
(what it costs or leaves unexamined). "establishes" holds the statements that would be recorded if the user selects \
that option.
- Do not add a "keep it open" or "defer" option. The interface always offers deferral; use "deferEffect" to say \
what leaving the question open means for the next step.
- A factual question with no real alternatives may have no options.
- "focus" is the single question most worth asking now, or null when nothing needs an answer before the next step. \
Never focus a question the user deferred.

REPLIES
- When NEW USER TEXT is a reply, add a "resolutions" entry for each existing question the reply answers or \
explicitly leaves open (status "deferred"), quoting the reply's exact wording. Do not resolve a question the reply \
does not address. An uncertain reply does not answer a question.
- A short reply is normal. Do not ask for more detail just because a reply is short.
- If the reply volunteers other choices, such as an audience, a boundary, or a next step, extract them like any \
explicit statement.
- Do not repeat statements or open items that already exist. Do not rewrite or remove existing statements. If the \
reply seems to contradict one, raise a question that names both.

REASSESSING
- When there is no NEW USER TEXT, the user has just made a choice through the interface. Do not extract or resolve \
anything. Add only open items that the new state makes material, such as an untested premise behind the user's \
choice, and set "focus" to a further question only if its answer would change the next step."""


def _compact_state(p: Project) -> dict[str, object]:
    return {
        "earlierUserText": [{"id": i.id, "kind": i.kind, "text": i.text} for i in p.inputs],
        "intent": [{"id": i.id, "kind": i.kind, "text": i.text} for i in p.intent],
        "openItems": [
            {"id": o.id, "kind": o.kind, "text": o.text, "status": o.status}
            | ({"options": [x.label for x in o.options]} if o.options else {})
            for o in p.open_items
        ],
        "decisions": [{"id": d.id, "summary": d.summary, "reason": d.reason} for d in p.decisions],
    }


def render_user_message(request: AssessRequest) -> str:
    if request.mode == "brief" or request.project is None:
        return f"CURRENT STATE: empty (this is a new brief).\n\nNEW USER TEXT (brief):\n<<<\n{request.text}\n>>>"
    state = f"CURRENT STATE:\n{json.dumps(_compact_state(request.project), indent=2, ensure_ascii=False)}"
    if request.mode == "reply":
        q = request.project.item(request.question_id) if request.question_id else None
        about = f" replying to question {q.id}: “{q.text}”" if q else ""
        return f"{state}\n\nNEW USER TEXT (reply{about}):\n<<<\n{request.text}\n>>>"
    return f"{state}\n\nNEW USER TEXT: none. The user just acted through the interface: {request.event}"


# Keywords that structured-output providers do not enforce consistently. The API validates them itself.
_UNPORTABLE = {"title", "default", "minLength", "maxLength", "minItems", "maxItems", "pattern", "format"}


type Json = bool | int | float | str | list[Json] | dict[str, Json] | None


def _portable(node: Json, defs: dict[str, Json]) -> Json:
    if isinstance(node, list):
        return [_portable(x, defs) for x in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str):
        return _portable(defs[ref.rsplit("/", 1)[-1]], defs)
    out: dict[str, Json] = {k: _portable(v, defs) for k, v in node.items() if k not in _UNPORTABLE and k != "$defs"}
    properties = out.get("properties")
    if out.get("type") == "object" and isinstance(properties, dict):
        out["required"] = list(properties)
        out["additionalProperties"] = False
    return out


def provider_schema() -> dict[str, Json]:
    """The proposal schema in the strict, self-contained form providers accept: no references, every
    property required, no additional properties. Length and count limits are enforced by the API."""
    full: dict[str, Json] = RawProposal.model_json_schema(by_alias=True, mode="validation")
    defs = full.get("$defs")
    portable = _portable(full, defs if isinstance(defs, dict) else {})
    assert isinstance(portable, dict)
    return portable


class LiveAssessor:
    def __init__(self, client: CompletionClient, *, max_output_tokens: int) -> None:
        self._client = client
        self._max_output_tokens = max_output_tokens
        self._schema = provider_schema()

    @property
    def label(self) -> str:
        return self._client.requested_model

    async def assess(self, request: AssessRequest, attempts: list[CallAttempt]) -> ModelReply:
        completion = await self._client.complete(
            CompletionRequest(
                system=SYSTEM_PROMPT,
                user=render_user_message(request),
                schema_name="intent_proposal",
                schema=self._schema,
                max_output_tokens=self._max_output_tokens,
            ),
            attempts,
        )
        if completion.finish_reason == "length":
            raise ModelCallError(
                "model-incomplete",
                "The model's response was cut off before it finished. Nothing was changed.",
                retryable=True,
            )
        if completion.finish_reason == "content_filter":
            raise ModelCallError(
                "model-declined",
                "The model declined this request. Nothing was changed.",
                retryable=True,
            )
        return ModelReply(
            raw=completion.content,
            interpreted_by=completion.served_model or self._client.requested_model,
            requested_model=self._client.requested_model,
            served_model=completion.served_model,
            provider=completion.provider,
            prompt_version=PROMPT_VERSION,
            usage=completion.usage,
        )
