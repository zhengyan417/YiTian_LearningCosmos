"""Per-specialist offline quality eval.

For each specialist (research / search / writer / coder) we run a small
golden set through ``agent.run`` and score the output with the LLM judge.
"""
