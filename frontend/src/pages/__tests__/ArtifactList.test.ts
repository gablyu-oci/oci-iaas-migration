/**
 * Tests for ArtifactList collision-aware display names.
 *
 * Replicates the display-name logic from ArtifactList in MigrationDetail.tsx
 * as a pure function so we can test without mounting React.
 */
import { describe, it, expect } from 'vitest';

/**
 * Replica of the display-name logic from ArtifactList.
 * Given a dict of artifacts, returns a map of key -> display name.
 */
function computeDisplayNames(artifacts: Record<string, string>): Record<string, string> {
  const entries = Object.entries(artifacts);
  const basenameCounts = new Map<string, number>();
  for (const [key] of entries) {
    const base = key.split('/').pop() || key;
    basenameCounts.set(base, (basenameCounts.get(base) || 0) + 1);
  }
  const collidingBasenames = new Set(
    [...basenameCounts.entries()].filter(([, count]) => count > 1).map(([base]) => base)
  );
  const result: Record<string, string> = {};
  for (const [key] of entries) {
    const basename = key.split('/').pop() || key;
    result[key] = collidingBasenames.has(basename) ? key : basename;
  }
  return result;
}

describe('ArtifactList display names', () => {
  it('shows full path when basenames collide', () => {
    const artifacts = {
      'foo/outputs.tf': 'output "a" {}',
      'bar/outputs.tf': 'output "b" {}',
    };
    const names = computeDisplayNames(artifacts);
    expect(names['foo/outputs.tf']).toBe('foo/outputs.tf');
    expect(names['bar/outputs.tf']).toBe('bar/outputs.tf');
  });

  it('shows basename only when no collision', () => {
    const artifacts = {
      'compute.tf': 'resource ...',
    };
    const names = computeDisplayNames(artifacts);
    expect(names['compute.tf']).toBe('compute.tf');
  });

  it('handles mixed colliding and non-colliding files', () => {
    const artifacts = {
      'terraform/variables.tf': 'var ...',
      'ocm/variables.tf': 'var ...',
      'network.tf': 'resource ...',
    };
    const names = computeDisplayNames(artifacts);
    expect(names['terraform/variables.tf']).toBe('terraform/variables.tf');
    expect(names['ocm/variables.tf']).toBe('ocm/variables.tf');
    expect(names['network.tf']).toBe('network.tf');
  });

  it('handles three-way collision', () => {
    const artifacts = {
      'a/outputs.tf': '',
      'b/outputs.tf': '',
      'c/outputs.tf': '',
    };
    const names = computeDisplayNames(artifacts);
    expect(names['a/outputs.tf']).toBe('a/outputs.tf');
    expect(names['b/outputs.tf']).toBe('b/outputs.tf');
    expect(names['c/outputs.tf']).toBe('c/outputs.tf');
  });

  it('handles empty artifacts', () => {
    const names = computeDisplayNames({});
    expect(Object.keys(names)).toHaveLength(0);
  });
});
