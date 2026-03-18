#!/usr/bin/env python3
"""
doc_loader.py - Returns relevant doc file paths for each translation type.

Adapted for backend use with underscore directory names.
"""

import argparse
import json
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
# shared/doc_loader.py -> parent is shared/ -> parent.parent is skills root
SKILLS_ROOT = Path(__file__).parent.parent.resolve()
DOCS_BASE = SKILLS_ROOT / "iam_translation" / "docs"
CFN_DOCS_BASE = SKILLS_ROOT / "cfn_terraform" / "docs"

# ── Core IAM docs (always returned for iam type) ──────────────────────────────
CORE_IAM_DOCS = [
    {
        "path": "oci-reference/permissions/20260306T012058Z__docs-oracle-com__verbs.md",
        "description": "OCI IAM verbs reference (inspect/read/use/manage)",
    },
    {
        "path": "oci-reference/permissions/20260306T012134Z__docs-oracle-com__resources.md",
        "description": "OCI resource-types and aggregate resource-types",
    },
    {
        "path": "oci-reference/policies/20260306T012045Z__docs-oracle-com__policy-syntax.md",
        "description": "OCI policy statement syntax and grammar",
    },
    {
        "path": "oci-reference/policies/20260306T012045Z__docs-oracle-com__how-policies-work.md",
        "description": "How OCI policies work (inheritance, evaluation order)",
    },
    {
        "path": "oci-reference/conditions/20260306T012135Z__docs-oracle-com__conditions.md",
        "description": "OCI policy conditions and condition keys",
    },
    {
        "path": "aws-reference/user-guide/20260306T011451Z__docs-aws-amazon-com__iam-json-policy-element-reference.md",
        "description": "AWS IAM JSON policy element reference",
    },
]

# ── Service-specific OCI docs ─────────────────────────────────────────────────
SERVICE_DOCS = {
    # AWS services that map to OCI Core Services (networking, compute, storage)
    "ec2": {
        "path": "oci-reference/permissions/20260306T012137Z__docs-oracle-com__details-for-the-core-services.md",
        "description": "OCI Core Services permissions (VCN, Compute, Block Storage)",
    },
    "vpc": {
        "path": "oci-reference/permissions/20260306T012137Z__docs-oracle-com__details-for-the-core-services.md",
        "description": "OCI Core Services permissions (VCN, Compute, Block Storage)",
    },
    "ebs": {
        "path": "oci-reference/permissions/20260306T012137Z__docs-oracle-com__details-for-the-core-services.md",
        "description": "OCI Core Services permissions (VCN, Compute, Block Storage)",
    },
    # S3 -> OCI Object Storage
    "s3": {
        "path": "oci-reference/permissions/20260306T012148Z__docs-oracle-com__details-for-object-storage-and-archive-storage.md",
        "description": "OCI Object Storage and Archive Storage permissions",
    },
    # IAM -> OCI IAM (without Identity Domains)
    "iam": {
        "path": "oci-reference/permissions/20260306T012059Z__docs-oracle-com__details-for-iam-without-identity-domains.md",
        "description": "OCI IAM permissions (without Identity Domains)",
    },
}

# ── CFN-specific docs ─────────────────────────────────────────────────────────
CFN_DOCS = [
    {
        "path": str(CFN_DOCS_BASE / "CF2TF-TOOL.md"),
        "description": "cf2tf tool usage and CloudFormation-to-Terraform mapping reference",
        "absolute": True,
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def resolve_doc(doc: dict) -> dict:
    """
    Resolve a doc entry to an absolute path. Entries with 'absolute': True
    are returned as-is. Others are resolved relative to DOCS_BASE.
    """
    if doc.get("absolute"):
        return {
            "path": doc["path"],
            "description": doc["description"],
            "exists": Path(doc["path"]).exists(),
        }
    abs_path = DOCS_BASE / doc["path"]
    return {
        "path": str(abs_path),
        "description": doc["description"],
        "exists": abs_path.exists(),
    }


def collect_examples() -> list:
    """
    Return all files found in oci-reference/examples/ under DOCS_BASE.
    """
    examples_dir = DOCS_BASE / "oci-reference" / "examples"
    results = []
    if examples_dir.is_dir():
        for p in sorted(examples_dir.iterdir()):
            if p.is_file():
                results.append({
                    "path": str(p),
                    "description": f"OCI policy example: {p.name}",
                    "exists": True,
                })
    return results


def deduplicate(docs: list) -> list:
    """Remove duplicate paths while preserving order."""
    seen = set()
    out = []
    for d in docs:
        if d["path"] not in seen:
            seen.add(d["path"])
            out.append(d)
    return out


def get_iam_docs(services: list = None) -> list:
    """
    Return resolved doc entries for IAM translation.
    Always includes core IAM docs + examples.
    Adds service-specific docs based on the services list.
    """
    docs = [resolve_doc(d) for d in CORE_IAM_DOCS]
    docs.extend(collect_examples())

    if services:
        for svc in services:
            svc_lower = svc.strip().lower()
            if svc_lower in SERVICE_DOCS:
                resolved = resolve_doc(SERVICE_DOCS[svc_lower])
                docs.append(resolved)

    return deduplicate(docs)


def get_cfn_docs() -> list:
    """
    Return resolved doc entries for CFN->Terraform translation.
    Includes CF2TF tool docs + core OCI IAM docs (for output IAM statements).
    """
    docs = []
    for d in CFN_DOCS:
        docs.append(resolve_doc(d))
    # CFN output often needs IAM policy knowledge too
    for d in CORE_IAM_DOCS:
        docs.append(resolve_doc(d))
    return deduplicate(docs)


def get_discovery_docs() -> list:
    """
    Return resolved doc entries for dependency discovery.
    Includes the core OCI IAM docs for service mapping context.
    """
    docs = [resolve_doc(d) for d in CORE_IAM_DOCS]
    docs.extend(collect_examples())
    return deduplicate(docs)


# ── Output formatters ─────────────────────────────────────────────────────────

def print_paths(docs: list):
    """Print newline-separated absolute paths (only existing files)."""
    for d in docs:
        if d["exists"]:
            print(d["path"])
        else:
            # Still print so callers know what was expected; add a comment marker
            print(f"# MISSING: {d['path']}", file=sys.stderr)


def print_json(docs: list):
    """Print JSON array of {path, description, exists} objects."""
    print(json.dumps(docs, indent=2))


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_iam(args):
    services = []
    if args.services:
        services = [s.strip() for s in args.services.split(",") if s.strip()]
    docs = get_iam_docs(services)
    if args.json:
        print_json(docs)
    else:
        print_paths(docs)


def cmd_cfn(args):
    docs = get_cfn_docs()
    if args.json:
        print_json(docs)
    else:
        print_paths(docs)


def cmd_discovery(args):
    docs = get_discovery_docs()
    if args.json:
        print_json(docs)
    else:
        print_paths(docs)


def cmd_list(args):
    """Always prints JSON list of {path, description} regardless of --json flag."""
    doc_type = args.type
    if doc_type == "iam":
        docs = get_iam_docs()
    elif doc_type == "cfn":
        docs = get_cfn_docs()
    elif doc_type == "discovery":
        docs = get_discovery_docs()
    else:
        print(f"ERROR: Unknown type '{doc_type}'", file=sys.stderr)
        sys.exit(1)
    print_json(docs)


# ── Argument parsing ──────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Return relevant reference doc paths for AWS->OCI migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_iam = subparsers.add_parser("iam", help="Get docs for IAM policy translation")
    p_iam.add_argument("--services", default=None,
                        help="Comma-separated list of AWS service names (e.g. ec2,s3,rds)")
    p_iam.add_argument("--json", action="store_true", help="Output JSON instead of plain paths")

    p_cfn = subparsers.add_parser("cfn", help="Get docs for CFN->Terraform translation")
    p_cfn.add_argument("--json", action="store_true", help="Output JSON instead of plain paths")

    p_disc = subparsers.add_parser("discovery", help="Get docs for dependency discovery")
    p_disc.add_argument("--json", action="store_true", help="Output JSON instead of plain paths")

    p_list = subparsers.add_parser("list", help="List docs as JSON for a given type")
    p_list.add_argument("--type", required=True, choices=["iam", "cfn", "discovery"],
                         help="Migration type to list docs for")

    return parser


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = build_parser()
    args = parser.parse_args()

    command_map = {
        "iam": cmd_iam,
        "cfn": cmd_cfn,
        "discovery": cmd_discovery,
        "list": cmd_list,
    }

    handler = command_map.get(args.command)
    if handler is None:
        print(f"ERROR: Unknown command '{args.command}'", file=sys.stderr)
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
