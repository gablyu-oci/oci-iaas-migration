"""OS compatibility checker for OCI migration.

Determines whether a discovered AWS resource's operating system is supported
on OCI, and provides the matching OCI platform image and any required
remediation steps.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Supported OS matrix
# Key: (normalised os name, major version string)
# Value: dict with oci_image (marketplace image name) and status
# ---------------------------------------------------------------------------
OCI_SUPPORTED_OS: dict[tuple[str, str], dict[str, Any]] = {
    # Oracle Linux
    ("oracle linux", "7"):  {"oci_image": "Oracle-Linux-7", "status": "compatible"},
    ("oracle linux", "8"):  {"oci_image": "Oracle-Linux-8", "status": "compatible"},
    ("oracle linux", "9"):  {"oci_image": "Oracle-Linux-9", "status": "compatible"},
    # RHEL
    ("rhel", "7"):  {"oci_image": "RHEL-7", "status": "compatible"},
    ("rhel", "8"):  {"oci_image": "RHEL-8", "status": "compatible"},
    ("rhel", "9"):  {"oci_image": "RHEL-9", "status": "compatible"},
    # Ubuntu
    ("ubuntu", "20.04"): {"oci_image": "Canonical-Ubuntu-20.04", "status": "compatible"},
    ("ubuntu", "22.04"): {"oci_image": "Canonical-Ubuntu-22.04", "status": "compatible"},
    ("ubuntu", "24.04"): {"oci_image": "Canonical-Ubuntu-24.04", "status": "compatible"},
    # CentOS (EOL path)
    ("centos", "7"): {
        "oci_image": "CentOS-7",
        "status": "compatible_with_remediation",
        "remediation": "CentOS 7 EOL - migrate to Oracle Linux 8 using centos2ol utility.",
    },
    # CentOS Stream
    ("centos stream", "8"): {"oci_image": "CentOS-Stream-8", "status": "compatible"},
    ("centos stream", "9"): {"oci_image": "CentOS-Stream-9", "status": "compatible"},
    # Windows Server
    ("windows server", "2016"): {"oci_image": "Windows-Server-2016-Standard", "status": "compatible"},
    ("windows server", "2019"): {"oci_image": "Windows-Server-2019-Standard", "status": "compatible"},
    ("windows server", "2022"): {"oci_image": "Windows-Server-2022-Standard", "status": "compatible"},
    # SUSE Linux Enterprise Server
    ("suse", "12"): {"oci_image": "SLES-12", "status": "compatible"},
    ("suse", "15"): {"oci_image": "SLES-15", "status": "compatible"},
    # Debian
    ("debian", "10"): {"oci_image": "Debian-10", "status": "compatible"},
    ("debian", "11"): {"oci_image": "Debian-11", "status": "compatible"},
    ("debian", "12"): {"oci_image": "Debian-12", "status": "compatible"},
}

# Aliases so that various AWS PlatformDetails strings resolve correctly
_OS_ALIASES: dict[str, str] = {
    "red hat enterprise linux": "rhel",
    "red hat": "rhel",
    "suse linux enterprise server": "suse",
    "sles": "suse",
    "microsoft windows server": "windows server",
    "windows": "windows server",
    "amazon linux": "oracle linux",  # closest OCI equivalent
}


def _normalise_os(raw: str) -> tuple[str, str]:
    """Extract (os_name, version) from a free-form OS string.

    Returns lowercased os name and the extracted major version (or minor
    for Ubuntu which uses ``YY.MM`` versioning).
    """
    text = raw.strip().lower()

    # Apply aliases
    for alias, canonical in _OS_ALIASES.items():
        if alias in text:
            text = text.replace(alias, canonical)
            break

    # Try to extract a version number (e.g. "8.6", "22.04", "2022")
    version_match = re.search(r"(\d+(?:\.\d+)?)", text)
    version = version_match.group(1) if version_match else ""

    # Determine the OS name portion (everything before the version)
    os_name = text
    if version_match:
        os_name = text[: version_match.start()].strip().rstrip("-_. ")

    # Strip trailing noise
    os_name = os_name.strip()

    # If we only have a bare platform name with no version, keep it as-is
    if not os_name and version:
        os_name = text.strip()

    return os_name, version


def check_os_compatibility(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Check whether a resource's OS is compatible with OCI.

    The function inspects several fields in ``raw_config`` (as returned by
    AWS EC2 describe-instances or similar) to determine the OS:

    1. ``PlatformDetails`` (e.g. "Red Hat Enterprise Linux")
    2. ``Platform`` (e.g. "windows" or absent for Linux)
    3. ``tags`` dict for an ``os`` or ``operating-system`` key

    Returns:
        Dict with keys: status, os_type, os_version, oci_image,
        remediation_steps.
    """
    os_raw: str = ""

    # Strategy 1: PlatformDetails (most informative)
    if raw_config.get("PlatformDetails"):
        os_raw = raw_config["PlatformDetails"]
    # Strategy 2: Platform field
    elif raw_config.get("Platform"):
        os_raw = raw_config["Platform"]
    # Strategy 3: tags
    else:
        tags = raw_config.get("tags") or raw_config.get("Tags") or {}
        if isinstance(tags, list):
            tags = {t.get("Key", ""): t.get("Value", "") for t in tags}
        for key in ("os", "operating-system", "OS", "OperatingSystem"):
            if tags.get(key):
                os_raw = tags[key]
                break

    if not os_raw:
        return {
            "status": "unknown",
            "os_type": None,
            "os_version": None,
            "oci_image": None,
            "remediation_steps": ["OS information not available. Manual review required."],
        }

    os_name, version = _normalise_os(os_raw)

    # Lookup in supported matrix
    lookup_key = (os_name, version)
    entry = OCI_SUPPORTED_OS.get(lookup_key)

    # For non-Ubuntu OSes, also try just the major version (e.g. "8" from "8.6")
    if entry is None and "." in version:
        major = version.split(".")[0]
        entry = OCI_SUPPORTED_OS.get((os_name, major))

    if entry is not None:
        remediation_steps: list[str] = []
        if entry.get("remediation"):
            remediation_steps.append(entry["remediation"])
        return {
            "status": entry["status"],
            "os_type": os_name,
            "os_version": version,
            "oci_image": entry["oci_image"],
            "remediation_steps": remediation_steps,
        }

    return {
        "status": "unknown",
        "os_type": os_name,
        "os_version": version,
        "oci_image": None,
        "remediation_steps": [
            f"OS '{os_name} {version}' not found in supported matrix. Manual review required."
        ],
    }
