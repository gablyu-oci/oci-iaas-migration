export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ');
}

const SKILL_TYPE_LABELS: Record<string, string> = {
  iam_translation: 'IAM Translation',
  network_translation: 'Network Translation',
  ec2_translation: 'EC2 Translation',
  database_translation: 'Database Translation',
  loadbalancer_translation: 'Load Balancer Translation',
  cfn_terraform: 'CFN → Terraform',
  dependency_discovery: 'Dependency Discovery',
};

/**
 * Returns a human-readable name for a skill run, e.g.
 *   "IAM Translation — my-policy"
 *   "Network Translation — my-vpc +2 more"
 */
export function getSkillRunName(
  skillType: string,
  resourceNames?: string[] | null,
  resourceName?: string | null,
): string {
  const label = SKILL_TYPE_LABELS[skillType] || skillType;
  const names = resourceNames?.filter(Boolean) ?? (resourceName ? [resourceName] : []);
  if (names.length === 0) return label;
  if (names.length === 1) return `${label} — ${names[0]}`;
  return `${label} — ${names[0]} +${names.length - 1} more`;
}

export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014';
  return new Date(dateStr).toLocaleString();
}

export function formatCost(cost: number | null): string {
  if (cost === null || cost === undefined) return '$0.00';
  return `$${cost.toFixed(4)}`;
}
