import { formatDate } from '../lib/utils';

export interface Resource {
  id: string;
  aws_type: string;
  aws_arn: string;
  name: string;
  status: string;
  created_at: string;
}

interface Props {
  resources: Resource[];
  onSelect?: (resource: Resource) => void;
  selectedId?: string;
  filterType?: string;
}

export default function ResourceTable({
  resources,
  onSelect,
  selectedId,
  filterType,
}: Props) {
  const filtered = filterType
    ? resources.filter((r) => r.aws_type === filterType)
    : resources;

  const statusColors: Record<string, string> = {
    discovered: 'bg-blue-100 text-blue-800',
    migrated: 'bg-green-100 text-green-800',
  };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Name
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Type
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              ARN
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Status
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Created
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {filtered.map((r) => (
            <tr
              key={r.id}
              onClick={() => onSelect?.(r)}
              role={onSelect ? 'button' : undefined}
              tabIndex={onSelect ? 0 : undefined}
              onKeyDown={(e) => {
                if (onSelect && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault();
                  onSelect(r);
                }
              }}
              className={`cursor-pointer hover:bg-gray-50 ${selectedId === r.id ? 'bg-blue-50 ring-2 ring-blue-500' : ''}`}
            >
              <td className="px-4 py-3 text-sm font-medium">
                {r.name || '\u2014'}
              </td>
              <td className="px-4 py-3 text-sm text-gray-600 font-mono">
                {r.aws_type}
              </td>
              <td className="px-4 py-3 text-sm text-gray-500 font-mono truncate max-w-xs">
                {r.aws_arn || '\u2014'}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium ${statusColors[r.status] || 'bg-gray-100 text-gray-800'}`}
                >
                  {r.status}
                </span>
              </td>
              <td className="px-4 py-3 text-sm text-gray-500">
                {formatDate(r.created_at)}
              </td>
            </tr>
          ))}
          {filtered.length === 0 && (
            <tr>
              <td
                colSpan={5}
                className="px-4 py-8 text-center text-gray-500"
              >
                No resources found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
