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


def strip_continuation_overlap(base: str, continuation: str, max_overlap: int = 256) -> str:
    """Remove duplicated boundary text between base and continuation.

    Local LLMs often repeat the final character or phrase of the provided prefix
    when asked to continue text. If ``base`` ends with text that ``continuation``
    starts with, remove the duplicated continuation prefix before concatenation.
    """
    if not base or not continuation:
        return continuation

    max_len = min(len(base), len(continuation), max_overlap)
    for overlap_len in range(max_len, 0, -1):
        if base[-overlap_len:] == continuation[:overlap_len]:
            return continuation[overlap_len:]

    return continuation


def regenerate_from_here(
    content: str,
    selection_start: int,
    continuation: str,
) -> InterventionResult:
    """Discard content after selection_start and append a new continuation."""
    prefix, discarded = split_at_selection(content, selection_start)
    clean_continuation = strip_continuation_overlap(prefix, continuation)
    next_content = prefix + clean_continuation
    return InterventionResult(
        next_content=next_content,
        prefix=prefix,
        discarded=discarded,
        insertion="",
        continuation=clean_continuation,
    )


def insert_and_continue(
    content: str,
    selection_start: int,
    insertion: str,
    continuation: str,
) -> InterventionResult:
    """Insert user text at selection_start and append a new continuation."""
    prefix, discarded = split_at_selection(content, selection_start)
    base = prefix + insertion
    clean_continuation = strip_continuation_overlap(base, continuation)
    next_content = base + clean_continuation
    return InterventionResult(
        next_content=next_content,
        prefix=prefix,
        discarded=discarded,
        insertion=insertion,
        continuation=clean_continuation,
    )
