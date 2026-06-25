"""Shared, lazily-created clients.

Importing this module loads .env but creates no clients and opens no connections, so importing
callbacks from optimize.py (e.g. in optimize_from_config.py) has no side effects. Clients are
built on first use.
"""

import os

from env import load_env

load_env()

_ld_ai = None
_anthropic_async = None


def ld_ai_client():
    """The LaunchDarkly AI client (initializes ldclient on first call)."""
    global _ld_ai
    if _ld_ai is None:
        import ldclient
        from ldclient.config import Config
        from ldai import LDAIClient

        ldclient.set_config(Config(os.environ["LAUNCHDARKLY_SDK_KEY"]))
        _ld_ai = LDAIClient(ldclient.get())
    return _ld_ai


def anthropic_async():
    """Async Anthropic client (the email agent and the optimizer both run on Claude). Reads ANTHROPIC_API_KEY."""
    global _anthropic_async
    if _anthropic_async is None:
        from anthropic import AsyncAnthropic

        _anthropic_async = AsyncAnthropic()
    return _anthropic_async
