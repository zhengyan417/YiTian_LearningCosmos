"""A2A protocol adapter layer (server / client / executor).

This package contains *only* the protocol machinery — no agent logic. Each
agent's domain code lives in its own package under ``app.agents.<name>``. The
coordinator (``app.agents.coordinator``) is the A2A *client* and reaches the
four specialist servers (``research`` / ``search`` / ``writer`` / ``coder``)
over the A2A protocol via ``a2a_specialist_client``.
"""
