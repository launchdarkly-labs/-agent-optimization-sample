"""Probe GPTZero with your own written replies and see the FULL breakdown.

Shows three things per text so you can judge which signal has a usable gradient:
  - class_probabilities  (human/ai/mixed — often discrete 0/1)
  - completely_generated_prob  (continuous 0..1)
  - what detector.score() currently returns (the value the optimizer judge sees)

Usage (run from the repo root so .env loads):
  uv run python <this file>                      # interactive: paste a reply, Ctrl-D to score, repeat
  uv run python <this file> "a one-line reply"   # score args directly
  echo "some reply" | uv run python <this file>  # score piped stdin as one document
  uv run python <this file> file1.txt file2.txt  # score each file
"""

import json
import os
import sys
import urllib.request

# Make the repo importable so .env (AI_LIKENESS_API_KEY) loads exactly as the app does.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env import load_env  # noqa: E402

load_env()

URL = os.environ.get("AI_LIKENESS_API_URL", "https://api.gptzero.me/v2/predict/text")
KEY = os.environ.get("AI_LIKENESS_API_KEY")


def probe(text: str) -> dict:
    req = urllib.request.Request(
        URL,
        data=json.dumps({"document": text[:10000]}).encode(),
        headers={
            "x-api-key": KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "agent-optimization-sample/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return (data.get("documents") or [{}])[0]


def detector_score(doc: dict) -> float:
    """Reuse detector.py's own extraction so this shows exactly what the judge gets."""
    import detector
    return detector._api_score_from_doc(doc)


def show(label: str, text: str) -> None:
    if not text.strip():
        return
    doc = probe(text)
    print("=" * 70)
    print(f"{label}: {text[:80]!r}{'…' if len(text) > 80 else ''}")
    print(f"  class_probabilities      : {doc.get('class_probabilities')}")
    print(f"  completely_generated_prob: {doc.get('completely_generated_prob')}")
    print(f"  predicted_class          : {doc.get('predicted_class')}")
    thr = os.environ.get("AI_LIKENESS_THRESHOLD", "0.5")
    print(f"  -> detector.score() value: {detector_score(doc)}   (judge sees this; pass needs <= {thr})")


def main() -> None:
    if not KEY:
        sys.exit("AI_LIKENESS_API_KEY not set (check .env in the repo root).")

    args = sys.argv[1:]
    files = [a for a in args if os.path.isfile(a)]
    inline = [a for a in args if not os.path.isfile(a)]

    if files:
        for path in files:
            with open(path) as f:
                show(path, f.read())
        return
    if inline:
        for i, text in enumerate(inline, 1):
            show(f"arg {i}", text)
        return
    if not sys.stdin.isatty():
        show("stdin", sys.stdin.read())
        return

    # Interactive: paste a reply, finish with Ctrl-D; blank entry quits.
    print("Paste a reply, then Ctrl-D to score. Empty + Ctrl-D to quit.\n")
    n = 0
    while True:
        try:
            text = sys.stdin.read()
        except KeyboardInterrupt:
            break
        if not text.strip():
            break
        n += 1
        show(f"reply {n}", text)
        print("\n(paste another, or Ctrl-D on empty to quit)\n")


if __name__ == "__main__":
    main()
