from gard.integrations.netbox.auth import netbox_authorization_header


def test_v2_token_uses_bearer() -> None:
    assert netbox_authorization_header("nbt_abc123.secretpart") == "Bearer nbt_abc123.secretpart"


def test_v1_token_uses_token_prefix() -> None:
    assert netbox_authorization_header("legacy-plaintext") == "Token legacy-plaintext"
