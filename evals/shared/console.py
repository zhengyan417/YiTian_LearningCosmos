"""Colored console output helpers used by every eval runner.

Centralized so the routing / agent_quality / trace runners all print with the
same look and color thresholds — avoids each runner reinventing its own
formatter.
"""

import colorama
from colorama import (
    Fore,
    Style,
)


def init() -> None:
    """Initialize colorama. Idempotent — safe to call from every runner entry."""
    colorama.init()


def print_title(title: str) -> None:
    """Print a centered title bracketed by ``=`` rules."""
    print("\n" + "=" * 60)
    print(f"{Fore.CYAN}{Style.BRIGHT}{title.center(60)}{Style.RESET_ALL}")
    print("=" * 60 + "\n")


def print_info(message: str) -> None:
    """Print a green info bullet."""
    print(f"{Fore.GREEN}• {message}{Style.RESET_ALL}")


def print_warning(message: str) -> None:
    """Print a yellow warning."""
    print(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")


def print_error(message: str) -> None:
    """Print a red error line."""
    print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")


def print_success(message: str) -> None:
    """Print a green check line."""
    print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")


def color_by_score(value: float, *, warn: float = 0.7, good: float = 0.8) -> str:
    """Pick a color based on a 0..1 score.

    Args:
        value: The score to color (0..1).
        warn: At-or-above this counts as "warning" (yellow).
        good: At-or-above this counts as "good" (green).

    Returns:
        A colorama color code to prepend to a numeric display.
    """
    if value >= good:
        return Fore.GREEN
    if value >= warn:
        return Fore.YELLOW
    return Fore.RED
