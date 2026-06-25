# agent-optimization-sample

Runnable companion code for the [agent optimization tutorial](https://docs.launchdarkly.com/tutorials/agent-optimization).

Optimizes an **email-reply drafter** to sound human, judged by **[GPTZero](https://gptzero.me/)** (an AI detector — not a language model) wired in *inverted* so the optimizer drives "AI-likeness" down. The run streams to the optimization's **Results** tab in LaunchDarkly and commits a recommended variation.

Think of this run as a **candidate generator**, not a training job (it changes the prompt, not model weights). It explores prompts against a GPTZero gate and commits a winner when one clears it. Whether that winner actually beats the baseline is a separate **side-by-side eval** over a dataset — done in LaunchDarkly, described in the tutorial, not in this repo.

**Who runs what:** the agent drafts on **Claude** (`claude-haiku-4-5-20251001`) and the optimizer that writes each new prompt also runs on **Claude**; AI-likeness is scored by **GPTZero**.

## Setup

```bash
uv sync
uv run python bootstrap.py     # seed/update the LaunchDarkly configs
```

Keys are read from `.env` (gitignored): `LD_SDK_KEY`, `LD_API_KEY`, `LD_PROJECT_KEY`, `ANTHROPIC_API_KEY` (the Claude agent and optimizer), and `AI_LIKENESS_API_KEY` ([GPTZero](https://app.gptzero.me/app/api)). `env.py` aliases the `LD_*` names to the `LAUNCHDARKLY_*` names the SDK expects.

`bootstrap.py` creates three objects. The two AI configs are created only if absent (so a committed winner is never clobbered); the optimization is **upserted**, so re-running applies any setting changes below.

| key | what |
|---|---|
| `email-agent` | the agent config whose instructions get optimized (seeded thin on purpose) |
| `ai-likeness` | inverted judge config — scored by GPTZero in code, not its prompt |
| `email-agent-opt` | the Agent optimization the run executes (one judge: AI-likeness) |

> One judge by design: the **New optimization** UI form attaches a single judge, so the run uses just AI-likeness to match what the UI supports.

## Run

```bash
OPTIMIZATION_KEY=email-agent-opt uv run python optimize_from_config.py
```

The command prints the Results-tab link — watch the run there. Each iteration drafts replies to all 10 sample messages at once, GPTZero scores each, and the gate is the **average** (averaging smooths GPTZero's large per-reply variance). The per-reply number is `1 - P(human)` (~0 = human, the goal; ~1 = AI), and GPTZero's full JSON is forwarded to the optimizer as the rationale so each rewrite is informed by it. On success the winner is auto-committed to `email-agent` as a new variation (**Variations** tab).

The threshold is a **generator gate**, not a verdict — the run's job is to surface a strong candidate, not to certify it. Confirm the candidate against the baseline with a side-by-side eval (see the tutorial).

Probe GPTZero on any draft: `uv run python gptzero_test.py "your draft reply"`.

## Settings

Baked into `email-agent-opt` at bootstrap time — change them by editing the optimization in the UI, or by re-running `bootstrap.py` with these set:

| var | default | what it does |
|---|---|---|
| `AI_LIKENESS_THRESHOLD` | `0.5` | gate: pass when the batch average ≤ this. Inverted, so **lower = stricter**. |
| `MAX_ATTEMPTS` | `10` | optimization iterations before stopping |
| `RESPONDENT_NAME` | `Jordan Lee` | signed into replies as a prompt variable, so no `[Your Name]` placeholders |
| `AUTO_COMMIT` | on | publish the winner as a variation on success; `0` to disable |

Run-time knobs (read by the callbacks on each run):

| var | default | what it does |
|---|---|---|
| `AGENT_MODEL` | `claude-haiku-4-5-20251001` | the Claude model the agent drafts with |
| `OPTIMIZER_MODEL` | `claude-haiku-4-5-20251001` | the Claude model that writes new prompts |

> GPTZero rates most LLM text as AI, so even a well-humanized reply rarely scores below ~0.5 — `0.5` is a demanding gate and a run may end with no commit. Raise it to commit more readily; lower it to push harder. For private use, swap `messages.py` for a local, gitignored input file.
