def test_api_lifespan_does_not_invoke_netbox_bootstrap() -> None:
    """F9 bootstrap is CLI-only; API startup must not import bootstrap modules."""
    import inspect

    from gard.api import app as app_module

    source = inspect.getsource(app_module)
    assert "netbox_bootstrap" not in source
    assert "bootstrap-device-types" not in source
    assert "devicetype_importer" not in source
