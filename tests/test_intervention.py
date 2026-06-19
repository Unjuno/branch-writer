import pytest

from branch_writer.intervention import (
    insert_and_continue,
    regenerate_from_here,
    split_at_selection,
    strip_continuation_overlap,
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


def test_regenerate_from_here_strips_repeated_boundary_text() -> None:
    result = regenerate_from_here(
        content="こんにちは！元気ですか？",
        selection_start=len("こんにちは！元"),
        continuation="元気ですか？",
    )

    assert result.prefix == "こんにちは！元"
    assert result.continuation == "気ですか？"
    assert result.next_content == "こんにちは！元気ですか？"


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


def test_insert_and_continue_strips_repeated_insert_boundary_text() -> None:
    result = insert_and_continue(
        content="私は",
        selection_start=len("私は"),
        insertion="openaiに",
        continuation="openaiについて聞いた。",
    )

    assert result.next_content == "私はopenaiについて聞いた。"


def test_strip_continuation_overlap_longest_match() -> None:
    assert strip_continuation_overlap("abcdef", "defghi") == "ghi"


def test_strip_continuation_overlap_without_match() -> None:
    assert strip_continuation_overlap("abcdef", "xyz") == "xyz"


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


# ── 絵文字・サロゲートペア・改行を含むテキスト ──


def test_emoji_selection_start() -> None:
    content = "Hello😀World"
    validate_selection_start(content, 7)
    prefix, discarded = split_at_selection(content, 7)
    assert prefix == "Hello😀W"
    assert discarded == "orld"


def test_surrogate_pair_selection_start() -> None:
    content = "a𝄞b"  # U+1D11E (MUSICAL SYMBOL G CLEF) — 4 UTF-8 bytes, 2 UTF-16 surrogates
    validate_selection_start(content, 2)
    prefix, discarded = split_at_selection(content, 2)
    assert prefix == "a𝄞"
    assert discarded == "b"


def test_newline_selection_start() -> None:
    content = "line1\nline2\nline3"
    # Select at the start of line2
    validate_selection_start(content, 6)
    prefix, discarded = split_at_selection(content, 6)
    assert prefix == "line1\n"
    assert discarded == "line2\nline3"


def test_mixed_emoji_newline() -> None:
    content = "😀\n🎉\n✨"
    # content by code points: 😀(1) \n(2) 🎉(3) \n(4) ✨(5) => len=5
    validate_selection_start(content, 3)
    prefix, discarded = split_at_selection(content, 3)
    assert prefix == "😀\n🎉"
    assert discarded == "\n✨"


# ── strip_continuation_overlap 追加ケース ──


def test_strip_overlap_prefix_and_insertion_preserved() -> None:
    """prefix + insertion が消えないことを確認"""
    prefix = "こんにちは！"
    insertion = "元"
    base = prefix + insertion
    raw = "元気ですか？"
    result = strip_continuation_overlap(base, raw)
    assert result == "気ですか？"
    assert base + result == "こんにちは！元気ですか？"


def test_strip_overlap_full_repeat() -> None:
    """完全に base が continuation に含まれる場合"""
    result = strip_continuation_overlap("abc", "abcdef")
    assert result == "def"


def test_strip_overlap_empty_base() -> None:
    assert strip_continuation_overlap("", "hello") == "hello"


def test_strip_overlap_empty_continuation() -> None:
    assert strip_continuation_overlap("hello", "") == ""


def test_strip_overlap_max_overlap_limit() -> None:
    """max_overlap=256 を超える重複は除去されない"""
    base = "a" * 300
    continuation = "a" * 300 + "b"
    result = strip_continuation_overlap(base, continuation)
    # max_overlap=256 の制限により、300字の重複のうち256字のみ除去 → 301 - 256 = 45字
    assert len(result) == 45
    assert result == "a" * 44 + "b"


def test_strip_overlap_japanese_emoji() -> None:
    """日本語＋絵文字の境界重複除去"""
    result = strip_continuation_overlap("スタート🎉", "🎉続き")
    assert result == "続き"


# ── regenerate_from_here / insert_and_continue 追加ケース ──


def test_regenerate_from_here_emoji() -> None:
    result = regenerate_from_here(
        content="Hello😀WorldFoo",
        selection_start=7,
        continuation="WorldBar",
    )
    assert result.next_content == "Hello😀WorldBar"
    assert result.prefix == "Hello😀W"


def test_insert_and_continue_emoji() -> None:
    result = insert_and_continue(
        content="Hello😀World",
        selection_start=7,
        insertion="🔥",
        continuation="🔥Beautiful",
    )
    assert result.next_content == "Hello😀W🔥Beautiful"
