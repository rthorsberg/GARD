"""Unit tests for NetBox bootstrap CLI guards."""

from __future__ import annotations

from unittest.mock import patch

from gard.cli.netbox_bootstrap import bootstrap_device_types_cli
from gard.core.settings import Settings
from gard.integrations.netbox.devicetype_importer import BootstrapReport


def test_prod_url_without_confirm_exits_nonzero() -> None:
    settings = Settings(
        env="dev",
        netbox_url="https://netbox.example.com",
        netbox_token="test-token",
        netbox_verify_tls=False,
    )
    rc = bootstrap_device_types_cli([], settings=settings)
    assert rc == 2


def test_dry_run_never_calls_write_client() -> None:
    with patch("gard.cli.netbox_bootstrap.run_bootstrap") as run_mock:
        rc = bootstrap_device_types_cli(["--dry-run"])
    assert rc == 0
    run_mock.assert_not_called()


def test_prod_env_requires_confirm() -> None:
    settings = Settings(
        env="prod",
        netbox_url="http://127.0.0.1:18888",
        netbox_token="test-token",
        netbox_verify_tls=False,
    )
    rc = bootstrap_device_types_cli([], settings=settings)
    assert rc == 2


def test_confirm_allows_prod_env_with_mocked_bootstrap() -> None:
    settings = Settings(
        env="prod",
        netbox_url="http://127.0.0.1:18888",
        netbox_token="test-token",
        netbox_verify_tls=False,
    )
    fake_report = BootstrapReport(
        upstream_pin="abc123",
        netbox_url="http://127.0.0.1:18888",
    )
    with patch("gard.cli.netbox_bootstrap.run_bootstrap", return_value=fake_report):
        rc = bootstrap_device_types_cli(["--confirm"], settings=settings)
    assert rc == 0
