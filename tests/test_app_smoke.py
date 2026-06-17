def test_app_imports_without_running_streamlit_main() -> None:
    import app

    assert hasattr(app, "main")
    assert hasattr(app, "handle_intervention_event")
