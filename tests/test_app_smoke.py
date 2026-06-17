def test_app_imports_without_running_streamlit_main() -> None:
    import app

    assert hasattr(app, "main")
    assert hasattr(app, "handle_intervention_event")


def test_estimate_tokens() -> None:
    from app import estimate_tokens

    assert estimate_tokens("Hello, world!") == 3
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 100) == 25
