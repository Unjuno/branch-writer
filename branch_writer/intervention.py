"""Intervention primitives for rewriting the latest assistant message."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class InterventionResult:
    """Result of applying an intervention to a message."""

    next_content: str
    prefix: str
    discarded: str
    insertion: str
    continuation: str


def validate_selection_start(content: str, selection_start: int) -> None:
    """Validate that selection_start is a valid slice boundary for content."""
    if not isinstance(selection_start, int):
        raise TypeError("selection_start must be an integer")

    if selection_start < 0:
        raise ValueError("selection_start must be greater than or equal to 0")

    if selection_start > len(content):
        raise ValueError("selection_start must be less than or equal to len(content)")


def split_at_selection(content: str, selection_start: int) -> tuple[str, str]:
    """Split content into prefix and discarded suffix at selection_start."""
    validate_selection_start(content, selection_start)
    return content[:selection_start], content[selection_start:]


def regenerate_from_here(
    content: str,
    selection_start: int,
    continuation: str,
) -> InterventionResult:
    """Discard content after selection_start and append a new continuation."""
    prefix, discarded = split_at_selection(content, selection_start)
    next_content = prefix + continuation
    return InterventionResult(
        next_content=next_content,
        prefix=prefix,
        discarded=discarded,
        insertion="",
        continuation=continuation,
    )


def insert_and_continue(
    content: str,
    selection_start: int,
    insertion: str,
    continuation: str,
) -> InterventionResult:
    """Insert user text at selection_start and append a new continuation."""
    prefix, discarded = split_at_selection(content, selection_start)
    next_content = prefix + insertion + continuation
    return InterventionResult(
        next_content=next_content,
        prefix=prefix,
        discarded=discarded,
        insertion=insertion,
        continuation=continuation,
    )
