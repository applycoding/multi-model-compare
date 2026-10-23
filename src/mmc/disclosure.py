from __future__ import annotations


def mock_profile_active(profile: str) -> bool:
    return profile == "mock"


def vendor_disclosure_line(profile: str, vendors: list[str]) -> str:
    if mock_profile_active(profile):
        return "Mock mode: nothing is sent to any provider"
    ordered = ", ".join(sorted(set(vendors)))
    return ordered


def cli_run_disclosure(profile: str, vendors: list[str]) -> str:
    if mock_profile_active(profile):
        return "Mock mode: nothing is sent to any provider"
    return f"Sending prompt to: {', '.join(vendors)}"


def web_disclosure_prefix(profile: str) -> str:
    if mock_profile_active(profile):
        return "Mock mode:"
    return "Will be sent to:"
