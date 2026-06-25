"""Seed the LaunchDarkly configs this sample needs, then point you at the one run command.

Creates:
  - email-agent     (AI config, mode: agent)   the drafter whose instructions get optimized
  - ai-likeness     (AI config, mode: judge)   the AI-likeness judge — scored by GPTZero in
                                               code (handle_judge_call), not by its prompt
  - email-agent-opt (Agent optimization)       the saved optimization the Results tab runs

The two AI configs are created only if absent (so a committed winner is never clobbered); the
optimization is upserted, so re-running applies any setting changes here.

    uv run python bootstrap.py
    OPTIMIZATION_KEY=email-agent-opt uv run python optimize_from_config.py

Required env: LAUNCHDARKLY_API_KEY (REST token with AI Configs write permission).
Optional env: PROJECT_KEY, AGENT_KEY, AI_LIKENESS_JUDGE_KEY, OPTIMIZATION_KEY, AGENT_MODEL,
              OPTIMIZER_MODEL, RESPONDENT_NAME, MAX_ATTEMPTS, AI_LIKENESS_THRESHOLD, AUTO_COMMIT.
"""

import json
import os
import sys
import urllib.error
import urllib.request

from env import load_env
from messages import batch_prompt

load_env()

API_HOST = "https://app.launchdarkly.com"
PROJECT_KEY = os.environ.get("PROJECT_KEY", "default")


# LaunchDarkly app (UI) URLs. The REST API only returns API hrefs, not UI links, so we build
# these for the console output.
def _app_url() -> str:
    return os.environ.get("LD_APP_URL", API_HOST)


def _env() -> str:
    return os.environ.get("LD_ENV", "test")


def config_url(key: str) -> str:
    """The config's Variations tab (where an auto-committed winner lands)."""
    return f"{_app_url()}/projects/{PROJECT_KEY}/ai-configs/{key}/variations?env={_env()}&selected-env={_env()}"


def optimization_results_url(key: str) -> str:
    """The optimization's page (opens on its latest run's Results tab)."""
    return f"{_app_url()}/projects/{PROJECT_KEY}/ai/optimize-agent/{key}?env={_env()}&selected-env={_env()}"
AGENT_KEY = os.environ.get("AGENT_KEY", "email-agent")
AI_LIKENESS_JUDGE_KEY = os.environ.get("AI_LIKENESS_JUDGE_KEY", "ai-likeness")
OPTIMIZATION_KEY = os.environ.get("OPTIMIZATION_KEY", "email-agent-opt")
RESPONDENT_NAME = os.environ.get("RESPONDENT_NAME", "Jordan Lee")
# The agent and the prompt-writing optimizer both run on Claude by default (the optimizer model
# lives in optimize.py / OPTIMIZER_MODEL). judgeModel below is required by the API even though
# our only judge, AI-likeness, is scored by GPTZero, not an LLM — so it's never actually called.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-4-5-20251001")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", AGENT_MODEL)

# Deliberately thin baseline — the optimizer improves on it. Source of truth after creation is LD.
AGENT_INSTRUCTIONS = "You are an email assistant. Draft a reply to the email below."
# The AI-likeness judge is scored by GPTZero in code (handle_judge_call), NOT by this prompt —
# it's a never-used placeholder. What matters is isInverted=true (lower = more human).
AI_LIKENESS_JUDGE_SYSTEM = (
    "Placeholder. The AI-likeness score comes from the GPTZero detector in code "
    "(see detector.py / handle_judge_call), not from this prompt."
)


def _create_config(api_key: str, payload: dict) -> None:
    """Create one AI config if it doesn't already exist (this API 400s on duplicate, so GET first)."""
    key = payload["key"]
    base = f"{API_HOST}/api/v2/projects/{PROJECT_KEY}/ai-configs"

    get_req = urllib.request.Request(f"{base}/{key}", headers={"Authorization": api_key})
    try:
        urllib.request.urlopen(get_req, timeout=30)
        print(f"AI config '{key}' already exists in '{PROJECT_KEY}'. Skipping.")
        return
    except urllib.error.HTTPError as e:
        if e.code != 404:
            sys.exit(f"Failed to check for config '{key}' ({e.code}): {e.read().decode()}")

    req = urllib.request.Request(
        base, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": api_key, "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=30)
        print(f"Created {payload['mode']} config '{key}' in project '{PROJECT_KEY}'.")
    except urllib.error.HTTPError as e:
        sys.exit(f"Failed to create config '{key}' ({e.code}): {e.read().decode()}")


def _upsert_agent_optimization(api_key: str, payload: dict) -> None:
    """Create the Agent optimization, or PATCH it to match this payload if it already exists.

    The optimization is declarative: re-running bootstrap converges it to the settings here.
    The agent-optimizations PATCH wants the full writable object — exactly `payload`.
    """
    key = payload["key"]
    base = f"{API_HOST}/api/v2/projects/{PROJECT_KEY}/agent-optimizations"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}

    get_req = urllib.request.Request(f"{base}/{key}", headers={"Authorization": api_key})
    exists = True
    try:
        urllib.request.urlopen(get_req, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            exists = False
        else:
            sys.exit(f"Failed to check for optimization '{key}' ({e.code}): {e.read().decode()}")

    method, url, verb = ("PATCH", f"{base}/{key}", "Updated") if exists else ("POST", base, "Created")
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method=method, headers=headers)
    try:
        urllib.request.urlopen(req, timeout=30)
        print(f"{verb} agent optimization '{key}' in project '{PROJECT_KEY}'.")
    except urllib.error.HTTPError as e:
        sys.exit(f"Failed to {method} optimization '{key}' ({e.code}): {e.read().decode()}")


def main() -> None:
    api_key = os.environ.get("LAUNCHDARKLY_API_KEY")
    if not api_key:
        sys.exit("LAUNCHDARKLY_API_KEY is required")

    _create_config(api_key, {
        "key": AGENT_KEY,
        "name": "Email Agent",
        "description": "Email-reply drafter for the agent-optimization tutorial.",
        "mode": "agent",
        "defaultVariation": {
            "key": "baseline",
            "name": "Baseline",
            "model": {"modelName": AGENT_MODEL, "parameters": {}},
            "instructions": AGENT_INSTRUCTIONS,
        },
    })

    _create_config(api_key, {
        "key": AI_LIKENESS_JUDGE_KEY,
        "name": "AI-likeness Judge",
        "description": "AI-detection judge. Scored by GPTZero in code (handle_judge_call), not this prompt.",
        "mode": "judge",
        "evaluationMetricKey": "$ld:ai:judge:ai-likeness",
        "isInverted": True,  # lower is better (more human)
        "defaultVariation": {
            "key": "baseline",
            "name": "Baseline",
            "model": {"modelName": JUDGE_MODEL, "parameters": {}},
            "messages": [
                {"role": "system", "content": AI_LIKENESS_JUDGE_SYSTEM},
                {"role": "user", "content": "{{response_to_evaluate}}"},
            ],
        },
    })

    # The saved optimization the Results tab runs. It's a candidate GENERATOR: one judge
    # (AI-likeness, matching the UI's single-judge form) and a tunable threshold (default 0.5).
    # Whether the winner beats the baseline is decided by a separate side-by-side eval over the
    # dataset (see the tutorial), not by this gate.
    _upsert_agent_optimization(api_key, {
        "key": OPTIMIZATION_KEY,
        "aiConfigKey": AGENT_KEY,
        "maxAttempts": int(os.environ.get("MAX_ATTEMPTS", "10")),
        "judgeModel": JUDGE_MODEL,
        "modelChoices": [AGENT_MODEL],
        # sender_type gives the drafts tonal range; the optimizer must use every variable.
        "variableChoices": [
            {"sender_type": "friend", "respondent_name": RESPONDENT_NAME},
            {"sender_type": "professional contact", "respondent_name": RESPONDENT_NAME},
        ],
        "judges": [
            {"key": AI_LIKENESS_JUDGE_KEY, "threshold": float(os.environ.get("AI_LIKENESS_THRESHOLD", "0.5"))},
        ],
        # One combined input (reply to every message), recorded as the run's "User input" and the
        # same string the agent drafts against — so input and output match in the UI.
        "userInputOptions": [batch_prompt()],
        "autoCommit": os.environ.get("AUTO_COMMIT", "1").lower() in ("1", "true", "yes"),
        "label": "Email agent — human-sounding (GPTZero)",
    })

    print()
    print("Configs:")
    print(f"    email-agent: {config_url(AGENT_KEY)}")
    print(f"    ai-likeness: {config_url(AI_LIKENESS_JUDGE_KEY)}")
    print()
    print("Run the optimization (streams to the Results tab):")
    print(f"    OPTIMIZATION_KEY={OPTIMIZATION_KEY} uv run python optimize_from_config.py")
    print(f"    Results: {optimization_results_url(OPTIMIZATION_KEY)}")


if __name__ == "__main__":
    main()
