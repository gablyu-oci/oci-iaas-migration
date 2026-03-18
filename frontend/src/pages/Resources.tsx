import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useResources } from '../api/hooks/useResources';
import { useMigrations } from '../api/hooks/useMigrations';
import ResourceTable, { type Resource } from '../components/ResourceTable';

export default function Resources() {
  const [migrationFilter, setMigrationFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [selectedResource, setSelectedResource] = useState<Resource | null>(null);
  const navigate = useNavigate();

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (migrationFilter) p.migration_id = migrationFilter;
    if (typeFilter) p.type = typeFilter;
    return Object.keys(p).length ? p : undefined;
  }, [migrationFilter, typeFilter]);

  const { data: resources, isLoading, isError } = useResources(params);
  const { data: migrations } = useMigrations();

  const resourceTypes = useMemo(() => {
    if (!resources) return [];
    const types = new Set(resources.map((r) => r.aws_type));
    return Array.from(types).sort();
  }, [resources]);

  const handleRunSkill = () => {
    if (selectedResource) {
      navigate(`/skill-runs/new?resource_id=${selectedResource.id}`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Resources</h1>
          <p className="text-gray-600 mt-1">
            Browse discovered AWS resources across your migrations.
          </p>
        </div>
        <button
          onClick={handleRunSkill}
          disabled={!selectedResource}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          Run Skill on Selected
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-4 flex-wrap">
        <div>
          <label
            htmlFor="migration-filter"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Migration
          </label>
          <select
            id="migration-filter"
            value={migrationFilter}
            onChange={(e) => setMigrationFilter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="">All Migrations</option>
            {migrations?.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label
            htmlFor="type-filter"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Resource Type
          </label>
          <select
            id="type-filter"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="">All Types</option>
            {resourceTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Resource Table */}
      <div className="bg-white rounded-lg shadow">
        {isLoading ? (
          <div className="p-6">
            <div className="animate-pulse space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-10 bg-gray-100 rounded" />
              ))}
            </div>
          </div>
        ) : isError ? (
          <div className="p-6 text-center text-red-500">
            Failed to load resources. Please try again.
          </div>
        ) : (
          <ResourceTable
            resources={resources || []}
            onSelect={(r) => setSelectedResource(r)}
            selectedId={selectedResource?.id}
          />
        )}
      </div>

      {/* Selected Resource Detail */}
      {selectedResource && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-3">
            Selected: {selectedResource.name || selectedResource.aws_type}
          </h2>
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <dt className="text-gray-500">Type</dt>
              <dd className="font-mono">{selectedResource.aws_type}</dd>
            </div>
            <div>
              <dt className="text-gray-500">ARN</dt>
              <dd className="font-mono truncate">
                {selectedResource.aws_arn || '\u2014'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">Status</dt>
              <dd>{selectedResource.status}</dd>
            </div>
            <div>
              <dt className="text-gray-500">ID</dt>
              <dd className="font-mono truncate">{selectedResource.id}</dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}
