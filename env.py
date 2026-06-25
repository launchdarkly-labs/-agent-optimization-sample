"""Zero-dependency .env loader.

Import and call `load_env()` at the very top of an entrypoint, before reading
any os.environ keys. Reads the repo-local .env (regardless of cwd) and, for
convenience, aliases the short LD_* names used in this repo's .env to the
canonical LAUNCHDARKLY_* names the SDK examples use. Existing env vars win.
"""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))

# canonical name  <-  alias found in .env
_ALIASES = {
    "LAUNCHDARKLY_SDK_KEY": "LD_SDK_KEY",
    "LAUNCHDARKLY_API_KEY": "LD_API_KEY",
    "PROJECT_KEY": "LD_PROJECT_KEY",
}


def load_env(path: str = None) -> None:
    path = path or os.path.join(_HERE, ".env")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass

    for canonical, alias in _ALIASES.items():
        if not os.environ.get(canonical) and os.environ.get(alias):
            os.environ[canonical] = os.environ[alias]
