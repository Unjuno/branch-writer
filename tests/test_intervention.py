import pytest

from branch_writer.intervention import (
    insert_and_continue,
    regenerate_from_here,
    split_at_selection,
    validate_selection_start,
)


def test_regenerate_from_here() -> None:
    result = regenerate_from_here(
        content="少女は扉を開けた。そこには父がいた。",
        selection_start=len("少女は扉を開けた。"),
        continuation="そこには誰もいなかった。",
    )

    assert result.prefix == "少女は扉を開けた。"
    assert result.discarded == "そこには父がいた。"
    assert result.next_content == "少女は扉を開けた。そこには誰もいなかった。"


def test_insert_and_continue() -> None:
    result = insert_and_continue(
        content="少女は扉を開けた。そこには父がいた。",
        selection_start=len("少女は扉を開けた。"),
        insertion="そこには古い手紙が落ちていた。",
        continuation="差出人の名前は消えていた。",
    )

    assert result.prefix == "少女は扉を開けた。"
    assert result.discarded == "そこには父がいた。"
    assert result.insertion == "そこには古い手紙が落ちていた。"
    assert result.next_content == (
        "少女は扉を開けた。"
        "そこには古い手紙が落ちていた。"
        "差出人の名前は消えていた。"
    )


def test_selection_start_zero() -> None:
    prefix, discarded = split_at_selection("abc", 0)

    assert prefix == ""
    assert discarded == "abc"


def test_selection_start_at_end() -> None:
    prefix, discarded = split_at_selection("abc", 3)

    assert prefix == "abc"
    assert discarded == ""


def test_selection_start_negative_is_error() -> None:
    with pytest.raises(ValueError):
        validate_selection_start("abc", -1)


def test_selection_start_too_large_is_error() -> None:
    with pytest.raises(ValueError):
        validate_selection_start("abc", 4)


def test_selection_start_must_be_integer() -> None:
    with pytest.raises(TypeError):
        validate_selection_start("abc", 1.5)  # type: ignore[arg-type]
