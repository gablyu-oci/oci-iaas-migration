/**
 * Regression tests for the PlanResults artifact partition logic.
 *
 * The partition algorithm places terraform/ocm/* files into
 * bySection.terraform with the `ocm/` prefix preserved (they are a child
 * module directory, not a separate top-level section).
 *
 * This file replicates the partition algorithm from PlanResults (in
 * MigrationDetail.tsx lines ~587-620) as a pure function so we can verify
 * correctness without mounting the full React component tree.
 *
 * To run: install vitest (`npm i -D vitest`) and execute `npx vitest run`.
 */
import { describe, it, expect } from 'vitest';

type SectionName = 'terraform' | 'runbooks' | 'reports' | 'debug';

/**
 * Exact replica of the partition loop inside PlanResults.
 * Keep in sync with MigrationDetail.tsx if the logic changes.
 */
function partitionArtifacts(rawArtifacts: Record<string, string>) {
  const bySection: Record<SectionName, Record<string, string>> = {
    terraform: {},
    runbooks: {},
    reports: {},
    debug: {},
  };

  const legacyFallback: Record<string, string> = {};

  for (const [key, content] of Object.entries(rawArtifacts)) {
    if (key === 'README.md' || key === 'manifest.json') continue;
    const top = key.split('/', 1)[0];
    if (
      top === 'terraform' ||
      top === 'runbooks' ||
      top === 'reports' ||
      top === 'debug'
    ) {
      const subKey = key.slice(top.length + 1);
      bySection[top][subKey] = content;
    } else {
      legacyFallback[key] = content;
    }
  }

  // Legacy fallback: if no new-layout terraform files exist but we have
  // old-style keys, fold them into approximate sections.
  if (
    Object.keys(bySection.terraform).length === 0 &&
    Object.keys(legacyFallback).length > 0
  ) {
    for (const [key, content] of Object.entries(legacyFallback)) {
      if (key.startsWith('synthesis/'))
        bySection.terraform[key.replace('synthesis/', '')] = content;
      else if (key.startsWith('data_migration/'))
        bySection.runbooks[
          `data-migration/${key.replace('data_migration/', '')}`
        ] = content;
      else if (key.startsWith('workload_planning/'))
        bySection.runbooks[
          `cutover/${key.replace('workload_planning/', '')}`
        ] = content;
      else if (key === 'resource-mapping.json')
        bySection.reports['resource-mapping.json'] = content;
      else bySection.debug[key] = content;
    }
  }

  return bySection;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PlanResults partition logic', () => {
  // -- Core OCM routing (child module under terraform/) ----------------------

  it('routes terraform/ocm/* into bySection.terraform with ocm/ prefix', () => {
    const artifacts: Record<string, string> = {
      'terraform/network.tf': 'resource "oci_core_vcn" "main" {}',
      'terraform/compute.tf': 'resource "oci_core_instance" "web" {}',
      'terraform/ocm/main.tf': 'resource "ocm_migration_plan" "p" {}',
      'terraform/ocm/variables.tf': 'variable "ocm_var" {}',
      'runbooks/cutover/plan.md': '# Cutover plan',
      'reports/resource-mapping.json': '{}',
    };

    const result = partitionArtifacts(artifacts);

    // OCM files land in terraform section with ocm/ prefix preserved
    expect(result.terraform).toEqual({
      'network.tf': 'resource "oci_core_vcn" "main" {}',
      'compute.tf': 'resource "oci_core_instance" "web" {}',
      'ocm/main.tf': 'resource "ocm_migration_plan" "p" {}',
      'ocm/variables.tf': 'variable "ocm_var" {}',
    });

    // Terraform section DOES contain ocm/ files
    expect(
      Object.keys(result.terraform).some((k) => k.startsWith('ocm/')),
    ).toBe(true);
    expect(result.terraform['ocm/main.tf']).toBe(
      'resource "ocm_migration_plan" "p" {}',
    );
    expect(result.terraform['ocm/variables.tf']).toBe(
      'variable "ocm_var" {}',
    );
  });

  it('puts all terraform/ocm/* files into bySection.terraform with ocm/ prefix', () => {
    const artifacts: Record<string, string> = {
      'terraform/ocm/main.tf': 'resource ...',
      'terraform/ocm/outputs.tf': 'output ...',
      'terraform/ocm/variables.tf': 'variable ...',
      'terraform/ocm/providers.tf': 'provider ...',
      'terraform/ocm/data.tf': 'data ...',
    };

    const result = partitionArtifacts(artifacts);

    expect(Object.keys(result.terraform)).toHaveLength(5);
    expect(result.terraform).toHaveProperty('ocm/main.tf');
    expect(result.terraform).toHaveProperty('ocm/providers.tf');
    expect(result.terraform).toHaveProperty('ocm/outputs.tf');
    expect(result.terraform).toHaveProperty('ocm/variables.tf');
    expect(result.terraform).toHaveProperty('ocm/data.tf');
  });

  // -- Non-OCM terraform stays put ------------------------------------------

  it('keeps non-ocm terraform files in terraform section', () => {
    const artifacts: Record<string, string> = {
      'terraform/main.tf': 'main',
      'terraform/providers.tf': 'providers',
    };

    const result = partitionArtifacts(artifacts);
    expect(result.terraform).toEqual({
      'main.tf': 'main',
      'providers.tf': 'providers',
    });
  });

  // -- Top-level files are excluded -----------------------------------------

  it('skips README.md and manifest.json', () => {
    const artifacts: Record<string, string> = {
      'README.md': '# Hello',
      'manifest.json': '{}',
      'terraform/main.tf': 'resource ...',
    };

    const result = partitionArtifacts(artifacts);
    expect(result.terraform).toEqual({ 'main.tf': 'resource ...' });
    // README and manifest should not appear in any section
    for (const section of Object.values(result)) {
      expect(Object.values(section)).not.toContain('# Hello');
      expect(Object.values(section)).not.toContain('{}');
    }
  });

  // -- All sections populated -----------------------------------------------

  it('distributes a full bundle into all four sections', () => {
    const artifacts: Record<string, string> = {
      'README.md': '# Bundle',
      'manifest.json': '{"files":[]}',
      'terraform/main.tf': 'tf-main',
      'terraform/ocm/ocm-main.tf': 'ocm-main',
      'runbooks/handoff.md': 'handoff',
      'reports/gaps.md': '# Gaps',
      'debug/ec2_translation/main.tf': 'debug-ec2',
    };

    const result = partitionArtifacts(artifacts);

    // terraform has main.tf + ocm/ocm-main.tf = 2
    expect(Object.keys(result.terraform)).toHaveLength(2);
    expect(result.terraform).toHaveProperty('main.tf');
    expect(result.terraform).toHaveProperty('ocm/ocm-main.tf');
    expect(Object.keys(result.runbooks)).toHaveLength(1);
    expect(Object.keys(result.reports)).toHaveLength(1);
    expect(Object.keys(result.debug)).toHaveLength(1);
  });

  // -- Empty input ----------------------------------------------------------

  it('returns empty sections for empty input', () => {
    const result = partitionArtifacts({});
    for (const section of Object.values(result)) {
      expect(Object.keys(section)).toHaveLength(0);
    }
  });

  // -- Legacy fallback logic ------------------------------------------------

  it('uses legacy fallback when no new-layout terraform files exist', () => {
    const artifacts: Record<string, string> = {
      'synthesis/main.tf': 'resource "oci_core_vcn" "main" {}',
      'synthesis/providers.tf': 'provider "oci" {}',
      'data_migration/rds.md': '# RDS migration',
      'workload_planning/cutover.md': '# Cutover',
      'resource-mapping.json': '{"mappings":[]}',
    };

    const result = partitionArtifacts(artifacts);

    expect(result.terraform).toEqual({
      'main.tf': 'resource "oci_core_vcn" "main" {}',
      'providers.tf': 'provider "oci" {}',
    });
    expect(result.runbooks['data-migration/rds.md']).toBe('# RDS migration');
    expect(result.runbooks['cutover/cutover.md']).toBe('# Cutover');
    expect(result.reports['resource-mapping.json']).toBe('{"mappings":[]}');
  });

  it('does NOT activate legacy fallback when new-layout terraform files exist', () => {
    const artifacts: Record<string, string> = {
      'terraform/main.tf': 'new-layout',
      'synthesis/old-main.tf': 'old-layout',
    };

    const result = partitionArtifacts(artifacts);

    // New-layout terraform file is present, so legacy fallback is skipped.
    // The synthesis/ key goes to legacyFallback but is NOT folded in.
    expect(result.terraform).toEqual({ 'main.tf': 'new-layout' });
    // old-main.tf must NOT appear in terraform or debug
    expect(result.terraform).not.toHaveProperty('old-main.tf');
  });

  // -- Deeply nested OCM paths land in terraform with ocm/ prefix -----------

  it('handles deeply nested paths under terraform/ocm/', () => {
    const artifacts: Record<string, string> = {
      'terraform/ocm/modules/network/main.tf': 'module network',
    };

    const result = partitionArtifacts(artifacts);
    expect(result.terraform).toEqual({
      'ocm/modules/network/main.tf': 'module network',
    });
  });

  // -- ocm as a non-terraform prefix is not special -------------------------

  it('does not treat top-level ocm/ as a known section (goes to legacyFallback)', () => {
    const artifacts: Record<string, string> = {
      'ocm/something.tf': 'stray file',
    };

    const result = partitionArtifacts(artifacts);
    // "ocm" is not in the known top-level dirs, so it falls to legacyFallback.
    // With no terraform files, legacy fallback activates but "ocm/something.tf"
    // does not match any legacy prefix, so it lands in debug.
    expect(result.debug).toHaveProperty('ocm/something.tf');
  });

  // -- OCM banner detection tests -------------------------------------------

  it('shows banner when every .tf is under ocm/', () => {
    const artifacts: Record<string, string> = {
      'terraform/ocm/main.tf': 'resource ...',
      'terraform/ocm/variables.tf': 'variable ...',
    };

    const result = partitionArtifacts(artifacts);
    const tfKeys = Object.keys(result.terraform);
    expect(tfKeys.length).toBeGreaterThan(0);
    expect(tfKeys.every((k) => k.startsWith('ocm/'))).toBe(true);
  });

  it('no banner when mixed terraform files', () => {
    const artifacts: Record<string, string> = {
      'terraform/network.tf': 'resource "oci_core_vcn" "main" {}',
      'terraform/ocm/main.tf': 'resource ...',
    };

    const result = partitionArtifacts(artifacts);
    const tfKeys = Object.keys(result.terraform);
    expect(tfKeys.length).toBeGreaterThan(0);
    expect(tfKeys.every((k) => k.startsWith('ocm/'))).toBe(false);
  });

  it('no banner when no .tf at all', () => {
    const artifacts: Record<string, string> = {
      'runbooks/handoff.md': 'handoff',
      'reports/gaps.md': '# Gaps',
    };

    const result = partitionArtifacts(artifacts);
    const tfKeys = Object.keys(result.terraform);
    expect(tfKeys).toHaveLength(0);
    // Banner should not fire on empty terraform section
    // (guard: only show banner when there ARE terraform files and all are ocm/)
    const shouldShowBanner =
      tfKeys.length > 0 && tfKeys.every((k) => k.startsWith('ocm/'));
    expect(shouldShowBanner).toBe(false);
  });
});
