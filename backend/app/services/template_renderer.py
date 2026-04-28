"""Deterministic Jinja2 renderer for structured template specs.

Takes a list of ``{template, label, params}`` dicts, validates each against
its Pydantic schema, renders the Jinja2 template, and groups HCL output by
domain into the filenames the synthesis_composer expects.

Hard-fails on validation errors so schema bugs surface immediately instead
of producing subtly broken HCL.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import ValidationError

_log = logging.getLogger(__name__)

# Template root directory
_TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "templates" / "oci"

# Map template name prefix -> output filename
# Templates are named like "core/vcn", "load_balancer/load_balancer", etc.
_DOMAIN_TO_FILE: dict[str, str] = {
    "core": "network.tf",
    "load_balancer": "loadbalancer.tf",
    "cloud_migrations": "ocm/main.tf",
}

# Fallback file if domain isn't recognized
_DEFAULT_FILE = "main.tf"


def _build_jinja_env() -> Environment:
    """Create a Jinja2 Environment with strict undefined and the template directory."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_ROOT)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


class TemplateRenderError(Exception):
    """Raised when a spec fails schema validation or template rendering."""
    def __init__(self, template: str, label: str, detail: str):
        self.template = template
        self.label = label
        self.detail = detail
        super().__init__(f"Template '{template}' label '{label}': {detail}")


def render_specs(specs: list[dict[str, Any]]) -> dict[str, str]:
    """Render a list of structured specs into HCL files.

    Args:
        specs: List of dicts, each with keys:
            - template (str): Template name like "core/vcn", "load_balancer/listener"
            - label (str): Terraform resource label (e.g., "main", "web_subnet")
            - params (dict): Parameters matching the template's Pydantic schema

    Returns:
        Dict mapping filename -> HCL content. E.g.:
            {"network.tf": "resource ...", "loadbalancer.tf": "resource ..."}

    Raises:
        TemplateRenderError: If any spec fails validation or rendering.
    """
    from app.templates.schemas import TEMPLATE_REGISTRY

    env = _build_jinja_env()
    # Accumulate rendered blocks per output file
    file_blocks: dict[str, list[str]] = {}

    for i, spec in enumerate(specs):
        template_name = spec.get("template", "")
        label = spec.get("label", f"unnamed_{i}")
        params = spec.get("params", {})

        if not template_name:
            raise TemplateRenderError("", label, "Missing 'template' key in spec")

        # --- Handle free_form_hcl fallback ---
        if template_name == "free_form_hcl":
            hcl_content = params.get("hcl", "")
            if not hcl_content:
                raise TemplateRenderError(
                    template_name, label,
                    "free_form_hcl spec has empty 'hcl' param",
                )
            # Validate against FreeFormHclParams if registered
            schema_cls = TEMPLATE_REGISTRY.get("free_form_hcl")
            if schema_cls:
                try:
                    schema_cls.model_validate(params)
                except ValidationError as exc:
                    raise TemplateRenderError(
                        template_name, label,
                        f"Schema validation failed:\n{exc}",
                    ) from exc
            output_file = _DEFAULT_FILE
            file_blocks.setdefault(output_file, []).append(hcl_content.strip())
            continue

        # --- Resolve domain and output file ---
        parts = template_name.split("/")
        if len(parts) == 2:
            domain, resource_type = parts
        else:
            domain = parts[0] if parts else ""
            resource_type = template_name

        output_file = _DOMAIN_TO_FILE.get(domain, _DEFAULT_FILE)

        # --- Validate params against Pydantic schema ---
        schema_cls = TEMPLATE_REGISTRY.get(template_name)
        if schema_cls is None:
            raise TemplateRenderError(
                template_name, label,
                f"No schema registered for template '{template_name}'. "
                f"Available: {sorted(TEMPLATE_REGISTRY.keys())}",
            )

        try:
            validated = schema_cls.model_validate(params)
        except ValidationError as exc:
            raise TemplateRenderError(
                template_name, label,
                f"Schema validation failed:\n{exc}",
            ) from exc

        # --- Render Jinja2 template ---
        template_file = f"{template_name}.tf.j2"
        try:
            tmpl = env.get_template(template_file)
        except Exception as exc:
            raise TemplateRenderError(
                template_name, label,
                f"Template file '{template_file}' not found: {exc}",
            ) from exc

        # Build render context: validated params + label
        render_ctx = validated.model_dump(exclude_none=True)
        render_ctx["label"] = label

        try:
            rendered = tmpl.render(**render_ctx)
        except Exception as exc:
            raise TemplateRenderError(
                template_name, label,
                f"Jinja2 rendering failed: {exc}",
            ) from exc

        file_blocks.setdefault(output_file, []).append(rendered.strip())

    # --- Assemble final output ---
    result: dict[str, str] = {}
    for filename, blocks in file_blocks.items():
        header = "# Generated by template_renderer — deterministic HCL output\n"
        result[filename] = header + "\n\n".join(blocks) + "\n"

    return result


def render_specs_safe(
    specs: list[dict[str, Any]],
) -> tuple[dict[str, str], list[str]]:
    """Like render_specs but collects errors instead of raising.

    Returns:
        Tuple of (rendered_files, errors). If errors is non-empty, some specs
        failed but others may have succeeded.
    """
    from app.templates.schemas import TEMPLATE_REGISTRY

    env = _build_jinja_env()
    file_blocks: dict[str, list[str]] = {}
    errors: list[str] = []

    for i, spec in enumerate(specs):
        template_name = spec.get("template", "")
        label = spec.get("label", f"unnamed_{i}")
        params = spec.get("params", {})

        try:
            if not template_name:
                raise TemplateRenderError("", label, "Missing 'template' key")

            if template_name == "free_form_hcl":
                hcl_content = params.get("hcl", "")
                if not hcl_content:
                    raise TemplateRenderError(
                        template_name, label, "empty hcl param",
                    )
                schema_cls = TEMPLATE_REGISTRY.get("free_form_hcl")
                if schema_cls:
                    schema_cls.model_validate(params)
                file_blocks.setdefault(_DEFAULT_FILE, []).append(
                    hcl_content.strip(),
                )
                continue

            parts = template_name.split("/")
            domain = parts[0] if len(parts) >= 2 else ""
            output_file = _DOMAIN_TO_FILE.get(domain, _DEFAULT_FILE)

            schema_cls = TEMPLATE_REGISTRY.get(template_name)
            if schema_cls is None:
                raise TemplateRenderError(
                    template_name, label,
                    f"No schema for '{template_name}'",
                )

            validated = schema_cls.model_validate(params)
            tmpl = env.get_template(f"{template_name}.tf.j2")
            render_ctx = validated.model_dump(exclude_none=True)
            render_ctx["label"] = label
            rendered = tmpl.render(**render_ctx)
            file_blocks.setdefault(output_file, []).append(rendered.strip())

        except (TemplateRenderError, ValidationError, Exception) as exc:
            errors.append(f"[{template_name}/{label}] {exc}")

    result: dict[str, str] = {}
    for filename, blocks in file_blocks.items():
        header = "# Generated by template_renderer — deterministic HCL output\n"
        result[filename] = header + "\n\n".join(blocks) + "\n"

    return result, errors
