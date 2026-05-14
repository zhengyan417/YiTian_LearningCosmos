"""A2A multi-agent subsystem.

A Coordinator agent (an A2A client) routes user requests to four specialist
agents exposed as A2A servers — research, search, writer, and coder. The
servers are mounted onto the main FastAPI app; the coordinator reaches them
over the A2A protocol through a shared client.
"""
