"""Keep-alive infrastructure.

Optional supplementary layer — off by default. See
`.conductor/wakeup-mitigation/implementation/self-ping-layer.md`.
"""

from spectre.infrastructure.keepalive.self_ping import (
    start_self_ping_thread,
    stop_self_ping_thread,
)

__all__ = ["start_self_ping_thread", "stop_self_ping_thread"]
