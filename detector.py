"""AI-likeness detector for the optimization's "human-sounding" judge.

Scores a reply with GPTZero and returns a number in [0.0, 1.0] where higher = more
AI-like. Used as an inverted judge (lower is better), so the optimizer pushes drafts
toward sounding human.

The score is `1 - P(human)`: ~0 when GPTZero classifies the text as human (the goal),
~1 for AI or mixed text. `score_with_response()` also returns GPTZero's full JSON so the
optimizer can read the sentence-level detail and decide what to change.

Env:
    AI_LIKENESS_API_KEY  - your GPTZero API key (required). Get one at
                           https://app.gptzero.me/app/api
    AI_LIKENESS_API_URL  - override the endpoint (default: GPTZero predict endpoint)
"""

import json
import os
import urllib.request


def score(text: str) -> float:
    """Return AI-likeness in [0,1] (higher = more AI-like)."""
    return score_with_response(text)[0]


def score_with_response(text: str):
    """Return (score, raw_response): the AI-likeness number and GPTZero's full JSON.

    handle_judge_call hands raw_response verbatim to the optimizer as rationale — no
    parsing needed — so it can see sentence-level probabilities, predicted_class, etc.
    """
    data = _api_call(text)
    return _api_score_from_doc((data.get("documents") or [{}])[0]), data


def _api_call(text: str) -> dict:
    """POST the text to GPTZero and return its full JSON response."""
    key = os.environ.get("AI_LIKENESS_API_KEY")
    if not key:
        raise RuntimeError(
            "AI_LIKENESS_API_KEY is required. Get a GPTZero key at "
            "https://app.gptzero.me/app/api and set it in .env."
        )
    url = os.environ.get("AI_LIKENESS_API_URL", "https://api.gptzero.me/v2/predict/text")

    req = urllib.request.Request(
        url,
        data=json.dumps({"document": text[:10000]}).encode(),
        # A User-Agent is required: GPTZero's Cloudflare edge blocks the default
        # urllib agent with "error code: 1010" (a 403), which is not a key problem.
        headers={
            "x-api-key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "agent-optimization-sample/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _api_score_from_doc(doc: dict) -> float:
    """AI-likeness in [0,1] (higher = more AI) from a GPTZero document = `1 - P(human)`.

    This directly encodes the goal (a reply GPTZero classifies as 'human'): ~0 for
    confidently-human text, ~1 for AI or mixed. Preferred over `average_generated_prob`
    (the *fraction of sentences* flagged AI — coarse, and reads 1.0 even when predicted_class
    is 'human'), over `class_probabilities["ai"]` (a 3-class verdict pushes it to ~0 on
    "mixed" text), and over the deprecated `completely_generated_prob`.
    """
    probs = doc.get("class_probabilities") or {}
    if "human" in probs:
        return round(1.0 - float(probs["human"]), 4)
    if doc.get("average_generated_prob") is not None:
        return round(float(doc["average_generated_prob"]), 4)
    if doc.get("completely_generated_prob") is not None:
        return round(float(doc["completely_generated_prob"]), 4)
    # No probability available: trust predicted_class, and default to AI (1.0) so an empty or
    # garbled 200 response fails the inverted gate instead of passing as a perfect human score.
    return 0.0 if str(doc.get("predicted_class", "")).lower() == "human" else 1.0


if __name__ == "__main__":
    from env import load_env  # so the standalone demo picks up AI_LIKENESS_API_KEY from .env
    load_env()
    sample = (
        "I hope this email finds you well. I'd be happy to help you navigate the "
        "refund process. Rest assured, please don't hesitate to reach out."
    )
    try:
        print(f"AI-likeness score: {score(sample)}")
    except RuntimeError as e:
        print(e)
