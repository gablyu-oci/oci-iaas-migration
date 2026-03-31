import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useResources } from '../api/hooks/useResources';
import { useTranslationJobs, useDeleteTranslationJob } from '../api/hooks/useTranslationJobs';
import { useQuery } from '@tanstack/react-query';
import { useCreateMigration, useMigrations, type Migration } from '../api/hooks/useMigrations';
import { useConnections } from '../api/hooks/useConnections';
import client from '../api/client';
import { formatDate, getSkillRunName } from '../lib/utils';

/* ── Helpers ─────────────────────────────────────────────────────── */

function statusBadge(status: string): string {
  const map: Record<string, string> = {
    complete: 'badge badge-success',
    running: 'badge badge-running',
    failed: 'badge badge-error',
    queued: 'badge badge-neutral',
    draft: 'badge badge-neutral',
    planning: 'badge badge-info',
    active: 'badge badge-success',
    created: 'badge badge-neutral',
    extracting: 'badge badge-info',
    extracted: 'badge badge-success',
    ready: 'badge badge-success',
  };
  return map[status] || 'badge badge-neutral';
}

function discoveryLabel(m: Migration) {
  if (m.discovery_status === 'discovering') return { text: 'Discovering…', cls: 'badge badge-running' };
  if (m.discovery_status === 'discovered') return { text: 'Discovered', cls: 'badge badge-success' };
  if (m.discovery_status === 'failed') return { text: 'Discovery failed', cls: 'badge badge-error' };
  return { text: 'Not started', cls: 'badge badge-neutral' };
}

const RESOURCE_TYPE_ICONS: Record<string, string> = {
  'AWS::EC2::Instance': '🖥',
  'AWS::EC2::SecurityGroup': '🛡',
  'AWS::EC2::Subnet': '🔌',
  'AWS::EC2::VPC': '☁',
  'AWS::IAM::Policy': '🔑',
  'AWS::EBS::Volume': '💾',
  'AWS::CloudFormation::Stack': '📦',
};

/* ── Main Component ──────────────────────────────────────────────── */

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: resources, isLoading: loadingResources } = useResources();
  const { data: skillRuns, isLoading: loadingSkillRuns } = useTranslationJobs();
  const { data: migrations, isLoading: loadingMigrations } = useMigrations();
  const { data: connections } = useConnections();
  const { data: assessmentCount } = useQuery<number>({
    queryKey: ['assessments-count'],
    queryFn: async () => {
      if (!migrations?.length) return 0;
      let count = 0;
      for (const m of migrations) {
        try {
          const res = await client.get(`/api/migrations/${m.id}/assessments`);
          count += (res.data as unknown[]).length;
        } catch { /* ignore */ }
      }
      return count;
    },
    enabled: !!migrations?.length,
  });
  const createMigration = useCreateMigration();
  const deleteSkillRun = useDeleteTranslationJob();

  const [showNewMigrationModal, setShowNewMigrationModal] = useState(false);
  const [newMigrationName, setNewMigrationName] = useState('');
  const [selectedConnectionId, setSelectedConnectionId] = useState('');

  const handleCreateMigration = () => {
    if (!newMigrationName.trim()) return;
    const payload: { name: string; aws_connection_id?: string } = { name: newMigrationName.trim() };
    if (selectedConnectionId) payload.aws_connection_id = selectedConnectionId;
    createMigration.mutate(payload, {
      onSuccess: (newMigration) => {
        setShowNewMigrationModal(false);
        setNewMigrationName('');
        setSelectedConnectionId('');
        navigate(`/migrations/${newMigration.id}`);
      },
    });
  };

  /* ── Computed values ── */
  const totalResources = resources?.length ?? 0;
  const totalMigrations = migrations?.length ?? 0;
  const recentRuns = (skillRuns || []).slice(0, 5);

  // Group resources by type for the breakdown
  const resourcesByType: Record<string, number> = {};
  (resources || []).forEach((r) => {
    const shortType = r.aws_type.split('::').slice(1).join(' ');
    resourcesByType[shortType] = (resourcesByType[shortType] || 0) + 1;
  });
  const sortedResourceTypes = Object.entries(resourcesByType).sort((a, b) => b[1] - a[1]);

  return (
    <div className="animate-fade-in" style={{ maxWidth: 1120 }}>

      {/* ── Page header ── */}
      <div className="flex items-start justify-between" style={{ marginBottom: 24 }}>
        <div>
          <h1 style={{
            fontFamily: 'var(--font-display)',
            fontSize: '2rem',
            fontWeight: 700,
            color: 'var(--color-text-bright)',
            letterSpacing: '-0.02em',
            lineHeight: 1.1,
            margin: 0,
          }}>
            Overview
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--color-text-dim)', marginTop: 6 }}>
            AWS to Oracle Cloud Infrastructure
          </p>
        </div>
        <button onClick={() => setShowNewMigrationModal(true)} className="btn btn-primary">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Migration
        </button>
      </div>


      {/* ═══════════════════════════════════════════════════════════════
          SECTION 2: Asymmetric two-column layout
          Left: Migration cards (primary focus — 60%)
          Right: Resource breakdown + Activity feed (40%)
          ═══════════════════════════════════════════════════════════════ */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 24, alignItems: 'start' }}>

        {/* ── LEFT COLUMN: Migration Cards ──────────────────────────── */}
        <div>
          <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
            <h2 style={{
              fontFamily: 'var(--font-display)',
              fontSize: '1.125rem',
              fontWeight: 600,
              color: 'var(--color-text-bright)',
              margin: 0,
            }}>
              Active Migrations
            </h2>
            <Link to="/migrations" style={{ fontSize: '0.8125rem', color: 'var(--color-ember)', textDecoration: 'none' }}>
              View all →
            </Link>
          </div>

          {loadingMigrations ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => <div key={i} className="skel" style={{ height: 120, borderRadius: 8 }} />)}
            </div>
          ) : !migrations?.length ? (
            /* ── Empty state — prominent CTA ── */
            <div
              style={{
                background: 'var(--color-surface)',
                border: '2px dashed var(--color-fence)',
                borderRadius: 10,
                padding: '48px 32px',
                textAlign: 'center',
              }}
            >
              <div style={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                background: 'var(--color-ember-dim)',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: 16,
              }}>
                <svg width="24" height="24" fill="none" stroke="var(--color-ember)" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </div>
              <h3 style={{
                fontFamily: 'var(--font-display)',
                fontSize: '1.125rem',
                fontWeight: 600,
                color: 'var(--color-text-bright)',
                margin: '0 0 8px',
              }}>
                Start your first migration
              </h3>
              <p style={{ fontSize: '0.8125rem', color: 'var(--color-text-dim)', maxWidth: 360, margin: '0 auto 20px' }}>
                Connect your AWS account, discover resources, and begin planning your move to OCI.
              </p>
              <button onClick={() => setShowNewMigrationModal(true)} className="btn btn-primary btn-lg">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Create Migration
              </button>
            </div>
          ) : (
            /* ── Migration cards ── */
            <div className="stagger-children" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {migrations.map((m) => {
                const disc = discoveryLabel(m);
                const resourceCount = (m as any).resource_count ?? 0;

                return (
                  <Link
                    key={m.id}
                    to={`/migrations/${m.id}`}
                    className="glow-card"
                    style={{
                      display: 'block',
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-rule)',
                      borderRadius: 10,
                      padding: '20px 24px',
                      textDecoration: 'none',
                      boxShadow: 'var(--shadow-card)',
                      position: 'relative',
                      overflow: 'hidden',
                    }}
                  >
                    {/* Left accent stripe */}
                    <div style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: 4,
                      background: m.discovery_status === 'discovered' ? '#059669' : m.discovery_status === 'discovering' ? '#1d4ed8' : 'var(--color-fence)',
                      borderRadius: '10px 0 0 10px',
                    }} />

                    <div className="flex items-start justify-between" style={{ marginBottom: 12 }}>
                      <div>
                        <h3 style={{
                          fontFamily: 'var(--font-display)',
                          fontSize: '1rem',
                          fontWeight: 600,
                          color: 'var(--color-text-bright)',
                          margin: 0,
                          lineHeight: 1.3,
                        }}>
                          {m.name}
                        </h3>
                        <p style={{ fontSize: '0.75rem', color: 'var(--color-text-dim)', marginTop: 2 }}>
                          Created {formatDate(m.created_at)}
                        </p>
                      </div>
                      <span className={disc.cls}>
                        <span className="badge-dot" />
                        {disc.text}
                      </span>
                    </div>

                    {/* Progress indicators — horizontal stat row */}
                    <div className="flex items-center gap-6">
                      <div className="flex items-center gap-2">
                        <svg width="14" height="14" fill="none" stroke="var(--color-rail)" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
                        </svg>
                        <span style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.8125rem',
                          fontWeight: 500,
                          color: 'var(--color-text-bright)',
                        }}>
                          {resourceCount}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: 'var(--color-text-dim)' }}>resources</span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className={statusBadge(m.status)}>
                          <span className="badge-dot" />
                          {m.status}
                        </span>
                      </div>

                      {/* Visual progress bar */}
                      <div style={{ flex: 1 }}>
                        <div style={{
                          height: 4,
                          background: 'var(--color-well)',
                          borderRadius: 2,
                          overflow: 'hidden',
                        }}>
                          <div style={{
                            height: '100%',
                            borderRadius: 2,
                            width: m.discovery_status === 'discovered' ? '33%'
                              : m.discovery_status === 'discovering' ? '15%'
                              : '5%',
                            background: m.discovery_status === 'discovered'
                              ? 'linear-gradient(90deg, #059669, #34d399)'
                              : m.discovery_status === 'discovering'
                              ? 'linear-gradient(90deg, #1d4ed8, #60a5fa)'
                              : 'var(--color-fence)',
                            transition: 'width 0.6s ease',
                          }} />
                        </div>
                        <div className="flex justify-between" style={{ marginTop: 4 }}>
                          <span style={{ fontSize: '0.625rem', color: 'var(--color-text-dim)' }}>
                            {m.discovery_status === 'discovered' ? 'Ready for assessment'
                              : m.discovery_status === 'discovering' ? 'Scanning AWS…'
                              : 'Awaiting discovery'}
                          </span>
                          <span style={{ fontSize: '0.625rem', color: 'var(--color-rail)', fontFamily: 'var(--font-mono)' }}>
                            Phase 1
                          </span>
                        </div>
                      </div>
                    </div>
                  </Link>
                );
              })}

              {/* Add migration card */}
              <button
                onClick={() => setShowNewMigrationModal(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  background: 'transparent',
                  border: '2px dashed var(--color-fence)',
                  borderRadius: 10,
                  padding: '16px 24px',
                  cursor: 'pointer',
                  color: 'var(--color-text-dim)',
                  fontSize: '0.8125rem',
                  fontWeight: 500,
                  fontFamily: 'inherit',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = 'var(--color-ember)';
                  e.currentTarget.style.color = 'var(--color-ember)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = 'var(--color-fence)';
                  e.currentTarget.style.color = 'var(--color-text-dim)';
                }}
              >
                <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Add another migration
              </button>
            </div>
          )}
        </div>

        {/* ── RIGHT COLUMN: Resource breakdown + Activity ────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* Resource Breakdown Panel */}
          <div
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-rule)',
              borderRadius: 10,
              boxShadow: 'var(--shadow-card)',
              overflow: 'hidden',
            }}
          >
            <div style={{
              padding: '14px 20px',
              borderBottom: '1px solid var(--color-rule)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <h3 style={{
                fontFamily: 'var(--font-display)',
                fontSize: '0.875rem',
                fontWeight: 600,
                color: 'var(--color-text-bright)',
                margin: 0,
              }}>
                Resource Inventory
              </h3>
              <Link to="/resources" style={{ fontSize: '0.75rem', color: 'var(--color-ember)', textDecoration: 'none' }}>
                Browse →
              </Link>
            </div>

            {loadingResources ? (
              <div style={{ padding: 20 }}>
                {[...Array(4)].map((_, i) => <div key={i} className="skel" style={{ height: 20, marginBottom: 8, borderRadius: 4 }} />)}
              </div>
            ) : sortedResourceTypes.length === 0 ? (
              <div style={{ padding: '24px 20px', textAlign: 'center', color: 'var(--color-text-dim)', fontSize: '0.8125rem' }}>
                No resources discovered yet
              </div>
            ) : (
              <div style={{ padding: '12px 20px 16px' }}>
                {/* Total count header */}
                <div className="flex items-baseline gap-2" style={{ marginBottom: 14 }}>
                  <span style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: '2rem',
                    fontWeight: 700,
                    color: 'var(--color-text-bright)',
                    lineHeight: 1,
                  }}>
                    {totalResources}
                  </span>
                  <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-dim)' }}>
                    AWS resources
                  </span>
                </div>

                {/* Type breakdown bars */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {sortedResourceTypes.slice(0, 6).map(([type, count]) => {
                    const pct = totalResources > 0 ? (count / totalResources) * 100 : 0;
                    const shortName = type.replace('EC2 ', '').replace('IAM ', '');
                    const icon = Object.entries(RESOURCE_TYPE_ICONS).find(([k]) => type.includes(k.split('::')[2] || ''))?.[1] || '·';

                    return (
                      <div key={type}>
                        <div className="flex items-center justify-between" style={{ marginBottom: 3 }}>
                          <span style={{ fontSize: '0.75rem', color: 'var(--color-text)' }}>
                            {icon} {shortName}
                          </span>
                          <span style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '0.6875rem',
                            color: 'var(--color-text-dim)',
                          }}>
                            {count}
                          </span>
                        </div>
                        <div style={{
                          height: 6,
                          background: 'var(--color-well)',
                          borderRadius: 3,
                          overflow: 'hidden',
                        }}>
                          <div style={{
                            height: '100%',
                            width: `${Math.max(pct, 3)}%`,
                            background: 'linear-gradient(90deg, #1d4ed8, #60a5fa)',
                            borderRadius: 3,
                            transition: 'width 0.4s ease',
                          }} />
                        </div>
                      </div>
                    );
                  })}
                  {sortedResourceTypes.length > 6 && (
                    <span style={{ fontSize: '0.6875rem', color: 'var(--color-rail)', textAlign: 'right' }}>
                      +{sortedResourceTypes.length - 6} more types
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Quick Numbers */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 12,
          }}>
            <div style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-rule)',
              borderRadius: 8,
              padding: '16px 18px',
              boxShadow: 'var(--shadow-card)',
            }}>
              <p style={{ fontSize: '0.6875rem', color: 'var(--color-text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, margin: 0 }}>
                Assessments
              </p>
              <p style={{
                fontFamily: 'var(--font-display)',
                fontSize: '1.75rem',
                fontWeight: 700,
                color: '#059669',
                margin: '6px 0 0',
                lineHeight: 1,
              }}>
                {assessmentCount ?? 0}
              </p>
            </div>
            <div style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-rule)',
              borderRadius: 8,
              padding: '16px 18px',
              boxShadow: 'var(--shadow-card)',
            }}>
              <p style={{ fontSize: '0.6875rem', color: 'var(--color-text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, margin: 0 }}>
                Connections
              </p>
              <p style={{
                fontFamily: 'var(--font-display)',
                fontSize: '1.75rem',
                fontWeight: 700,
                color: '#1d4ed8',
                margin: '6px 0 0',
                lineHeight: 1,
              }}>
                {connections?.length ?? 0}
              </p>
            </div>
          </div>

          {/* Recent Activity Feed */}
          <div
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-rule)',
              borderRadius: 10,
              boxShadow: 'var(--shadow-card)',
              overflow: 'hidden',
            }}
          >
            <div style={{
              padding: '14px 20px',
              borderBottom: '1px solid var(--color-rule)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <h3 style={{
                fontFamily: 'var(--font-display)',
                fontSize: '0.875rem',
                fontWeight: 600,
                color: 'var(--color-text-bright)',
                margin: 0,
              }}>
                Recent Activity
              </h3>
              <Link to="/translation-jobs" style={{ fontSize: '0.75rem', color: 'var(--color-ember)', textDecoration: 'none' }}>
                All jobs →
              </Link>
            </div>

            {loadingSkillRuns ? (
              <div style={{ padding: 20 }}>
                {[...Array(3)].map((_, i) => <div key={i} className="skel" style={{ height: 36, marginBottom: 8, borderRadius: 4 }} />)}
              </div>
            ) : recentRuns.length === 0 ? (
              <div style={{ padding: '24px 20px', textAlign: 'center', color: 'var(--color-text-dim)', fontSize: '0.8125rem' }}>
                No activity yet
              </div>
            ) : (
              <div>
                {recentRuns.map((run, idx) => (
                  <div
                    key={run.id}
                    style={{
                      padding: '12px 20px',
                      borderBottom: idx < recentRuns.length - 1 ? '1px solid var(--color-rule)' : 'none',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                    }}
                  >
                    {/* Status indicator dot */}
                    <div style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      flexShrink: 0,
                      background: run.status === 'complete' ? '#059669'
                        : run.status === 'running' ? '#1d4ed8'
                        : run.status === 'failed' ? '#e11d48'
                        : 'var(--color-fence)',
                      ...(run.status === 'running' ? { animation: 'pulse-dot 1.4s ease-in-out infinite' } : {}),
                    }} />

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{
                        fontSize: '0.8125rem',
                        color: 'var(--color-text-bright)',
                        fontWeight: 500,
                        margin: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}>
                        {getSkillRunName(run.skill_type, run.resource_names, run.resource_name)}
                      </p>
                      <p style={{
                        fontSize: '0.6875rem',
                        color: 'var(--color-text-dim)',
                        margin: '2px 0 0',
                      }}>
                        {formatDate(run.created_at)}
                        {run.status === 'complete' && run.confidence != null ? (
                          <> · <span style={{ fontFamily: 'var(--font-mono)', color: '#059669' }}>{(run.confidence * 100).toFixed(0)}%</span></>
                        ) : null}
                      </p>
                    </div>

                    <div className="flex items-center gap-1">
                      {run.status === 'complete' ? (
                        <Link to={`/translation-jobs/${run.id}/results`} className="btn btn-ghost btn-sm" style={{ fontSize: '0.6875rem' }}>
                          View
                        </Link>
                      ) : run.status === 'running' || run.status === 'queued' ? (
                        <Link to={`/translation-jobs/${run.id}`} className="btn btn-ghost btn-sm" style={{ fontSize: '0.6875rem' }}>
                          Progress
                        </Link>
                      ) : (
                        <Link to={`/translation-jobs/${run.id}/results`} className="btn btn-ghost btn-sm" style={{ fontSize: '0.6875rem' }}>
                          Details
                        </Link>
                      )}
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          if (confirm('Delete this translation job?')) deleteSkillRun.mutate(run.id);
                        }}
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: '0.6875rem', color: 'var(--color-error)' }}
                        title="Delete"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          New Migration Modal
          ═══════════════════════════════════════════════════════════════ */}
      {showNewMigrationModal && (
        <div
          className="modal-overlay"
          onClick={(e) => { if (e.target === e.currentTarget) setShowNewMigrationModal(false); }}
          role="dialog"
          aria-modal="true"
          aria-label="Create new migration"
        >
          <div className="modal">
            <div className="modal-header">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>New Migration</h3>
              <button onClick={() => setShowNewMigrationModal(false)} className="btn-ghost btn btn-sm" aria-label="Close">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="modal-body space-y-4">
              {createMigration.isError && (
                <div className="alert alert-error" role="alert">
                  {(createMigration.error as any)?.response?.data?.detail || 'Failed to create migration.'}
                </div>
              )}
              <div>
                <label htmlFor="dash-migration-name" className="field-label">Migration Name</label>
                <input
                  id="dash-migration-name"
                  type="text"
                  value={newMigrationName}
                  onChange={(e) => setNewMigrationName(e.target.value)}
                  placeholder="e.g., Production VPC Migration"
                  className="field-input"
                  autoFocus
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreateMigration(); }}
                />
              </div>
              <div>
                <label htmlFor="dash-aws-connection" className="field-label">AWS Connection (optional)</label>
                <select
                  id="dash-aws-connection"
                  value={selectedConnectionId}
                  onChange={(e) => setSelectedConnectionId(e.target.value)}
                  className="field-input field-select"
                >
                  <option value="">No connection</option>
                  {(connections || []).map((conn) => (
                    <option key={conn.id} value={conn.id}>{conn.name} ({conn.region})</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                onClick={() => { setShowNewMigrationModal(false); setNewMigrationName(''); setSelectedConnectionId(''); createMigration.reset(); }}
                className="btn btn-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreateMigration}
                disabled={!newMigrationName.trim() || createMigration.isPending}
                className="btn btn-primary"
              >
                {createMigration.isPending ? <><span className="spinner" />Creating…</> : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
