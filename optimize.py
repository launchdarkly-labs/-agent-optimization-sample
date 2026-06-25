"""Callbacks for the config-driven optimization run (optimize_from_config.py).

This module is not run directly. It supplies the two callbacks the SDK invokes:

  - handle_agent_call  : drafts replies (on Claude), and — when the SDK reuses the same
                         callback to generate the next set of instructions — runs that on the
                         optimizer model (also Claude).
  - handle_judge_call  : scores every candidate with GPTZero (detector.py), averaging
                         across a batch of replies; forwards GPTZero's full JSON to the optimizer.

Judges, thresholds, inputs, and model choices live in the saved `email-agent-opt` optimization
config in LaunchDarkly (created by bootstrap.py), not here.

Both the email agent and the prompt-writing optimizer run on Claude. Keys come from .env
(ANTHROPIC_API_KEY, AI_LIKENESS_API_KEY).
"""

import json
import os
import re

from ldai.tracker import TokenUsage
from ldai_optimizer import OptimizationResponse

import detector
from clients import anthropic_async
from messages import batch_prompt

AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-4-5-20251001")
OPTIMIZER_MODEL = os.environ.get("OPTIMIZER_MODEL", "claude-haiku-4-5-20251001")
AGENT_MAX_TOKENS = int(os.environ.get("AGENT_MAX_TOKENS", "2048"))
OPTIMIZER_MAX_TOKENS = int(os.environ.get("OPTIMIZER_MAX_TOKENS", "4096"))

# Prepended to the judge rationale each iteration so the prompt-writer gets concrete guidance
# on HOW to lower AI-likeness — not just the score.
HUMANIZE_TIPS = (
    "To lower AI-likeness, rewrite the agent's instructions so replies read like a real person "
    "dashed them off, not an assistant. The levers that move AI detectors most on short replies:\n"
    "- Contractions throughout (I'm, don't, you're, it's); write in the first person.\n"
    "- Vary sentence length a lot — mix very short sentences with longer ones, and allow the "
    "occasional fragment.\n"
    "- It's fine to open a sentence with And, But, or So, and to address the person directly ('you').\n"
    "- Let in the occasional natural filler (honestly, actually) or a brief parenthetical aside "
    "where the tone allows.\n"
    "- Be specific to the message and use casual time cues ('Saturday works', 'the other day').\n"
    "- BAN formal / AI-tell connectors (furthermore, moreover, additionally, consequently) and "
    "boilerplate openers ('I hope this email finds you well', 'Thank you for reaching out', "
    "'I'd be happy to', 'Please don't hesitate to reach out').\n"
    "- Match the sender's register (casual for a friend, brief and warm for a work contact), "
    "answer the actual question, and don't over-explain or over-hedge.\n"
    "- Sign off with {{respondent_name}}; never leave '[Your Name]'."
)

# Each turn the agent replies to ALL messages in one call and the judge averages GPTZero
# across them — averaging smooths GPTZero's large per-reply variance (one reply can swing
# 0.0–1.0) into a signal the optimizer can climb. The same batch_prompt() is the optimization's
# lone userInputOption, so the UI's recorded "User input" matches what the agent drafted.


def _extract_candidate(user_input: str) -> str:
    """Pull the candidate reply out of the SDK-built judge user message."""
    s = user_input or ""
    prefix = "Here is the response to evaluate: "
    if s.startswith(prefix):
        s = s[len(prefix):]
    return s.split("\n\nHere is the expected response:")[0].strip()


def _usage(inp, out) -> TokenUsage:
    """TokenUsage from input/output counts, defaulting None to 0."""
    inp, out = inp or 0, out or 0
    return TokenUsage(input=inp, output=out, total=inp + out)


async def _complete_anthropic(model: str, system: str, user: str,
                              max_tokens: int = AGENT_MAX_TOKENS) -> OptimizationResponse:
    """One Claude (Anthropic Messages API) call -> OptimizationResponse."""
    msg = await anthropic_async().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system or "",
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    u = getattr(msg, "usage", None)
    usage = _usage(getattr(u, "input_tokens", None), getattr(u, "output_tokens", None)) if u else None
    return OptimizationResponse(output=text, usage=usage)


def _parse_replies(text: str) -> list:
    """Extract the list of reply strings from the agent's output, tolerating code fences or
    stray prose around the JSON (cheaper models don't always return clean ```json``` -free)."""
    if not text:
        return []
    # Try the raw text, then the first {...} span (skips ```json fences / preamble).
    span = re.search(r"\{.*\}", text, re.DOTALL)
    for candidate in ([text, span.group(0)] if span else [text]):
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        replies = data.get("replies") if isinstance(data, dict) else None
        if isinstance(replies, list):
            return [r for r in replies if isinstance(r, str)]
    return []


async def handle_agent_call(key, config, context, is_evaluation=False) -> OptimizationResponse:
    """Draft a reply to every message in one call (on Claude); on a variation-generation
    call, run the meta-prompt on the optimizer (also Claude)."""
    instructions = config.instructions or ""

    # A variation-generation call: the SDK reuses this callback with a meta-prompt whose required
    # output names 'current_instructions' — a string a real email instruction never contains. It
    # arrives as the system prompt with an empty user, but Anthropic requires a non-empty user, so
    # put the meta-prompt in the user slot.
    if "current_instructions" in instructions:
        opt_model = OPTIMIZER_MODEL if OPTIMIZER_MODEL.startswith("claude") else AGENT_MODEL
        system, user = instructions, (context.user_input or "")
        if not user.strip():
            system, user = "", system
        return await _complete_anthropic(opt_model, system, user, max_tokens=OPTIMIZER_MAX_TOKENS)

    # Coerce to a Claude model: a stale config may still name a non-Claude model the Anthropic
    # API would 404 on. The optimization's modelChoices keep generated variations on Claude.
    name = config.model.name if config.model else None
    model = name if name and name.startswith("claude") else AGENT_MODEL
    user = context.user_input or batch_prompt()
    resp = await _complete_anthropic(model, instructions, user)
    replies = _parse_replies(resp.output)
    return OptimizationResponse(output=json.dumps({"replies": replies}), usage=resp.usage)


async def handle_judge_call(key, config, context, is_evaluation=True) -> OptimizationResponse:
    """Score every candidate with GPTZero, averaged across the batch (the run's only judge).

    Bypasses the judge config entirely — GPTZero is the scorer, not an LLM — and hands the
    optimizer the full per-reply GPTZero JSON in the rationale, so each rewrite is informed by it.
    """
    text = _extract_candidate(getattr(context, "user_input", "") or "")
    try:
        replies = [r for r in (json.loads(text) or {}).get("replies", [])
                   if isinstance(r, str) and r.strip()]
    except (ValueError, TypeError):
        replies = []
    if not replies:
        # An empty/degenerate draft must FAIL the inverted gate — scoring it (the detector
        # returns 0.0 for empty text) would read as a perfect pass.
        return OptimizationResponse(output=json.dumps(
            {"score": 1.0, "rationale": "empty or degenerate candidate"}))
    # One GPTZero call per reply in the batch. The judge only sees the replies (the response
    # to evaluate), not the original messages, so we report per-reply — GPTZero scores the
    # reply text alone anyway.
    results = []
    for reply in replies:
        try:
            s, raw = detector.score_with_response(reply)  # higher = more AI-like
        except Exception as e:
            # Never let a detector failure reach the SDK as score 0.0 (a perfect pass for
            # an inverted judge, silently disabling the gate). Fail the gate loudly instead.
            return OptimizationResponse(output=json.dumps(
                {"score": 1.0, "rationale": f"GPTZero detector failed: {e}"}))
        results.append({"reply": reply, "ai_likeness": s, "gptzero": raw})
    avg = round(sum(r["ai_likeness"] for r in results) / len(results), 4)
    # The gate is the AVERAGE. Hand the optimizer the full per-reply GPTZero JSON so it can
    # see which replies/sentences read as AI and revise. Goal: every reply classified 'human'.
    rationale = (
        f"{HUMANIZE_TIPS}\n\n"
        f"Average AI-likeness across {len(results)} replies = {avg} (lower is more human; "
        "goal: each reply classified 'human', i.e. 1 - P(human) near 0). Per-reply GPTZero "
        f"results:\n{json.dumps(results)}"
    )
    return OptimizationResponse(output=json.dumps({"score": avg, "rationale": rationale}))
