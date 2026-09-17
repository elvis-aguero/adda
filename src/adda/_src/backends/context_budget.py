"""Client-side context trimming for OpenAI-compatible backends.

WHY THIS EXISTS, AND WHY ONLY HERE
    ``create_react_agent`` runs a whole tool loop inside ONE adda turn, and
    nothing bounded it: a strategizer turn in the oracle-bench campaign reached
    ~30,600 tokens. On a provider with a large window that is merely expensive.
    On Ollama it is fatal AND misdiagnosable — the server truncates the
    transcript to ``num_ctx`` from the FRONT, evicting the original user turn,
    and its qwen3.8 renderer then rejects the request with
    ``500 no user query found in messages``. adda's ``UserlessPayloadError``
    guard cannot see it: the payload leaves here with a valid user turn, and
    eviction happens server-side afterwards.

    The Claude backend deliberately does NOT use this. The Claude SDK compacts
    automatically and does it better than a truncation heuristic can, so
    trimming there would replace a good mechanism with a worse one. That makes
    the two backends behave differently under pressure, which is a real
    confound for any cross-model comparison — so the resolved window, its
    source, and every trim event are RECORDED. The asymmetry is declared, not
    hidden, and an analysis can condition on it.

THE ONE INVARIANT
    The first user turn is never evicted. Dropping the oldest message is
    exactly what the server does wrong; reproducing it here would turn a
    provider bug into ours. It is pinned, and the newest messages are kept
    around it.

TOKEN COUNTING IS DELIBERATELY PESSIMISTIC
    There is no tokenizer here that is right for every served model —
    tiktoken is wrong for Qwen, and the point is to stay under a limit rather
    than to report a true count. ``_CHARS_PER_TOKEN`` is set BELOW the usual
    ~4 so the estimate runs high and the trim fires early. An estimate that is
    too low is a 500; an estimate that is too high costs a little context.
"""
from __future__ import annotations

__all__ = [
    "DEFAULT_CONTEXT_WINDOW",
    "MAX_OUTPUT_TOKENS_CEILING",
    "TrimReport",
    "estimate_tokens",
    "resolve_max_output_tokens",
    "trim_to_budget",
]

#: Used only when neither the setting nor the server can say. Small on
#: purpose: under-trimming fails the run, over-trimming costs context.
DEFAULT_CONTEXT_WINDOW = 8192

#: Pessimistic on purpose — see the module docstring.
_CHARS_PER_TOKEN = 3.0

#: Share of the window left for the model's own reply plus per-message
#: framing the estimate does not see.
_RESPONSE_HEADROOM = 0.25

#: A single message may not occupy more than this share of the budget. One
#: ReadNote of a transcript can otherwise exceed the whole window by itself,
#: which no message-granularity trim can fix.
_MAX_SINGLE_MESSAGE_SHARE = 0.4

#: Absolute ceiling on ONE reply, whatever the window allows. A 262144-token
#: window permits a ~65k-token reply, which at the ~18 tok/s an L40S sustains
#: for a 27B model is over an hour of generation inside a single agent turn
#: (observed: one strategizer request past 26k tokens and still climbing after
#: 25 minutes, zero delegations, the run's whole budget gone). No legitimate
#: reply from these agents is this long; a reply approaching it is a loop.
MAX_OUTPUT_TOKENS_CEILING = 8192

#: Never cap below this, however small the window: a cap under one long
#: tool-call argument turns a runaway into a truncated, unparseable call.
_MIN_OUTPUT_TOKENS = 512

_TRUNCATION_NOTE = "\n\n[... {n} characters dropped by adda context trimming]"


class TrimReport:
    """What a trim did, for telemetry. Cheap enough to always construct."""

    __slots__ = ("dropped", "truncated", "before", "after", "budget")

    def __init__(self, *, dropped: int = 0, truncated: int = 0,
                 before: int = 0, after: int = 0, budget: int = 0) -> None:
        self.dropped = dropped          # whole messages removed
        self.truncated = truncated      # messages whose content was cut
        self.before = before            # estimated tokens in
        self.after = after              # estimated tokens out
        self.budget = budget

    @property
    def fired(self) -> bool:
        return bool(self.dropped or self.truncated)

    def as_dict(self) -> dict:
        return {"dropped": self.dropped, "truncated": self.truncated,
                "tokens_before": self.before, "tokens_after": self.after,
                "budget": self.budget}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"TrimReport({self.as_dict()})"


def resolve_max_output_tokens(window: int, explicit: int = 0) -> int | None:
    """Tokens one reply may generate. ``None`` means deliberately uncapped.

    ``explicit > 0`` wins outright. ``explicit < 0`` is the escape hatch: it
    restores the unbounded behaviour on purpose, which is a thing an
    experiment may want and a thing a default may not be.

    Otherwise the cap is derived from the window, because the trim already
    reserves ``_RESPONSE_HEADROOM`` of it for the reply. Leaving the server
    free to generate the whole window makes that reservation a fiction: the
    input is trimmed to make room for a reply that is then allowed to overrun
    it anyway. Deriving both from one constant is what keeps them consistent,
    and the ceiling keeps a very large window from meaning "no bound at all".
    """
    if explicit > 0:
        return explicit
    if explicit < 0:
        return None
    derived = int(window * _RESPONSE_HEADROOM)
    return max(_MIN_OUTPUT_TOKENS, min(MAX_OUTPUT_TOKENS_CEILING, derived))


def _text_of(msg) -> str:
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for c in content:
            if isinstance(c, dict):
                out.append(str(c.get("text") or c.get("content") or ""))
            else:
                out.append(str(c))
        return " ".join(out)
    return str(content)


def estimate_tokens(msg) -> int:
    """Pessimistic token estimate for one message or string.

    Tool calls are counted too: an AIMessage carrying a large tool-call
    argument has almost no ``content`` but is not free on the wire.
    """
    n = len(_text_of(msg))
    calls = getattr(msg, "tool_calls", None) or []
    for c in calls:
        n += len(str(c))
    return int(n / _CHARS_PER_TOKEN) + 4      # per-message framing


def _is_tool_message(msg) -> bool:
    return msg.__class__.__name__ == "ToolMessage"


def _has_tool_calls(msg) -> bool:
    return bool(getattr(msg, "tool_calls", None))


def _truncate(msg, max_tokens: int):
    """Cut one oversized message's text, keeping its head and tail.

    The head carries what the call was; the tail carries the result. The
    middle of a 30k-token directory listing is the part worth losing.
    """
    text = _text_of(msg)
    keep = max(200, int(max_tokens * _CHARS_PER_TOKEN))
    if len(text) <= keep:
        return msg, False
    head = keep // 2
    tail = keep - head
    dropped = len(text) - keep
    new = (text[:head] + _TRUNCATION_NOTE.format(n=dropped) + text[-tail:])
    try:
        return msg.model_copy(update={"content": new}), True
    except Exception:                       # pragma: no cover - non-pydantic
        try:
            copied = type(msg)(content=new)
        except Exception:
            return msg, False
        return copied, True


def trim_to_budget(messages: list, *, context_window: int,
                   reserve_tokens: int = 0) -> tuple[list, TrimReport]:
    """Return messages that fit, plus a report of what it took.

    Keeps the first user turn (pinned) and as many of the NEWEST messages as
    fit. A kept tail never starts on a ToolMessage whose parent AIMessage was
    dropped — an orphan tool result is a malformed request in its own right,
    which would trade one provider error for another.
    """
    budget = int((context_window - reserve_tokens) * (1 - _RESPONSE_HEADROOM))
    before = sum(estimate_tokens(m) for m in messages)
    report = TrimReport(before=before, after=before, budget=budget)
    if budget <= 0 or before <= budget or not messages:
        return list(messages), report

    # 1. cap any single oversized message first — one giant tool result can
    #    exceed the whole budget, which dropping other messages cannot fix.
    cap = max(1, int(budget * _MAX_SINGLE_MESSAGE_SHARE))
    capped = []
    was_truncated: set[int] = set()
    for m in messages:
        if estimate_tokens(m) > cap:
            m, did = _truncate(m, cap)
            if did:
                was_truncated.add(id(m))
        capped.append(m)

    # 2. pin the first user turn: evicting it is the server bug we are here
    #    to avoid, so it is never a candidate for removal.
    pin_at = next((i for i, m in enumerate(capped)
                   if m.__class__.__name__ == "HumanMessage"), None)
    pinned = [capped[pin_at]] if pin_at is not None else []
    spent = sum(estimate_tokens(m) for m in pinned)

    # 3. walk backwards taking the newest that still fit
    tail: list = []
    for i in range(len(capped) - 1, -1, -1):
        if i == pin_at:
            continue
        cost = estimate_tokens(capped[i])
        if spent + cost > budget:
            break
        tail.append(capped[i])
        spent += cost
    tail.reverse()

    # 4. never open on an orphaned tool result
    while tail and _is_tool_message(tail[0]):
        spent -= estimate_tokens(tail.pop(0))

    kept = pinned + tail
    # Count only the truncations that SURVIVED. A message that was cut and
    # then dropped anyway was not truncated from the model's point of view,
    # and reporting it would overstate what the trim preserved.
    report.truncated = sum(1 for m in kept if id(m) in was_truncated)
    report.dropped = len(capped) - len(kept)
    report.after = sum(estimate_tokens(m) for m in kept)
    return kept, report
