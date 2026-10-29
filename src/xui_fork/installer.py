"""Mutation gate: no upstream artifact or provisioning recipe is trusted yet."""


class InstallationNotReady(RuntimeError):
    pass


def require_release_artifacts() -> None:
    raise InstallationNotReady(
        "installation is gated: signed/pinned artifacts and isolated E2E restore are pending"
    )
