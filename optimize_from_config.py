"""Run the email-agent optimization and stream it to the LaunchDarkly **Results** tab.

This is the one run command. Judges, inputs, thresholds, and model choices come from the
saved `email-agent-opt` Agent optimization (created by bootstrap.py). The callbacks in
optimize.py supply the behavior: the agent drafts on Claude, and the AI-likeness judge is
scored by GPTZero.

The run is a candidate generator: it explores prompts and commits a recommended variation.

Prereqs:
    uv run python bootstrap.py     # seeds the configs + the email-agent-opt optimization
    OPTIMIZATION_KEY=email-agent-opt uv run python optimize_from_config.py
"""

import asyncio
import logging
import os

from ldai_optimizer import OptimizationClient, OptimizationFromConfigOptions

from clients import ld_ai_client
from optimize import handle_agent_call, handle_judge_call

OPTIMIZATION_KEY = os.environ.get("OPTIMIZATION_KEY", "email-agent-opt")

# This flow's output lives in the LaunchDarkly UI (the optimization's Results tab), so keep
# the console quiet — silence the SDK's per-iteration INFO logging and just print the link.
logging.getLogger("ldai_optimizer").setLevel(logging.WARNING)


def optimization_results_url(key: str) -> str:
    """The optimization's page in the LaunchDarkly app (opens on its latest run's Results tab).

    The REST API only returns API hrefs, not UI links, so we build this one.
    """
    app = os.environ.get("LD_APP_URL", "https://app.launchdarkly.com")
    project = os.environ.get("PROJECT_KEY", "default")
    env = os.environ.get("LD_ENV", "test")
    return f"{app}/projects/{project}/ai/optimize-agent/{key}?env={env}&selected-env={env}"


async def main():
    url = optimization_results_url(OPTIMIZATION_KEY)
    options = OptimizationFromConfigOptions(
        project_key=os.environ.get("PROJECT_KEY", "default"),
        handle_agent_call=handle_agent_call,
        handle_judge_call=handle_judge_call,
    )
    print(f"Running optimization '{OPTIMIZATION_KEY}'. Follow it live in LaunchDarkly:")
    print(f"  {url}\n")
    await OptimizationClient(ld_ai_client()).optimize_from_config(OPTIMIZATION_KEY, options)
    print("\nDone. See every iteration and the recommended variation on the Results tab:")
    print(f"  {url}")


if __name__ == "__main__":
    asyncio.run(main())
