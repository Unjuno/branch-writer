"""Chat message models and helpers for Branch Writer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

MessageRole = Literal["user", "assistant"]
MessageStatus = Literal["streaming", "complete", "error"]


@dataclass(slots=True)
class ChatMessage:
    """A single chat message in the Branch Writer conversation."""

    role: MessageRole
    content: str
    status: MessageStatus = "complete"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_openai_message(self) -> dict[str, str]:
        """Convert the message to the OpenAI-compatible chat format."""
        return {"role": self.role, "content": self.content}


def append_user_message(messages: list[ChatMessage], content: str) -> ChatMessage:
    """Append a user message and return it."""
    message = ChatMessage(role="user", content=content, status="complete")
    messages.append(message)
    return message


def append_assistant_message(
    messages: list[ChatMessage],
    content: str,
    status: MessageStatus = "complete",
) -> ChatMessage:
    """Append an assistant message and return it."""
    message = ChatMessage(role="assistant", content=content, status=status)
    messages.append(message)
    return message


def is_intervenable(messages: list[ChatMessage], message_id: str) -> bool:
    """Return whether the given message can be intervened on.

    v0 allows intervention only on the latest assistant message. User messages,
    older assistant messages, and errored assistant messages are frozen.
    """
    if not messages:
        return False

    latest = messages[-1]
    return (
        latest.id == message_id
        and latest.role == "assistant"
        and latest.status in {"complete", "streaming"}
    )


def frozen_messages_before_latest(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Return all messages except the latest one.

    This is used during intervention generation so that the discarded suffix of
    the latest assistant message is not accidentally included in the prompt.
    """
    if not messages:
        return []
    return messages[:-1]


def to_openai_messages(messages: list[ChatMessage], system_prompt: str = "") -> list[dict[str, str]]:
    """Convert chat history to OpenAI-compatible chat messages."""
    result = [message.to_openai_message() for message in messages]
    if system_prompt:
        result.insert(0, {"role": "system", "content": system_prompt})
    return result
