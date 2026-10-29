"""Pure inbound validation; creation remains gated until live contract tests."""

from .compatibility import profile_supported


def validate_profile(name: str, panel_version: str) -> None:
    if not profile_supported(name, panel_version):
        raise ValueError("unsupported profile/version tuple")
