import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import client from '../client';

export interface SkillRun {
  id: string;
  skill_type: string;
  status: string;
  current_phase: string;
  current_iteration: number;
  confidence: number;
  total_cost_usd: number;
  output: Record<string, unknown> | null;
  errors: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  config?: Record<string, unknown>;
}

export interface Artifact {
  id: string;
  file_type: string;
  file_name: string;
  content_type: string;
  created_at: string;
}

export function useSkillRuns() {
  return useQuery<SkillRun[]>({
    queryKey: ['skill-runs'],
    queryFn: () => client.get('/api/skill-runs').then((r) => r.data),
  });
}

export function useSkillRun(id: string) {
  return useQuery<SkillRun>({
    queryKey: ['skill-runs', id],
    queryFn: () => client.get(`/api/skill-runs/${id}`).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.status === 'complete' || data.status === 'failed'))
        return false;
      return 2000;
    },
  });
}

export function useCreateSkillRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      skill_type: string;
      input_content?: string;
      input_resource_id?: string;
      migration_id?: string;
      config?: Record<string, unknown>;
    }) => client.post('/api/skill-runs', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['skill-runs'] }),
  });
}

export function useSkillRunArtifacts(skillRunId: string) {
  return useQuery<Artifact[]>({
    queryKey: ['skill-runs', skillRunId, 'artifacts'],
    queryFn: () =>
      client.get(`/api/skill-runs/${skillRunId}/artifacts`).then((r) => r.data),
    enabled: !!skillRunId,
  });
}

interface SSEEvent {
  phase: string;
  iteration: number;
  confidence: number;
  status: string;
  elapsed_secs: number;
}

export function useSkillRunStream(skillRunId: string) {
  const [event, setEvent] = useState<SSEEvent | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!skillRunId) return;

    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const token = localStorage.getItem('token');
    const url = `${API_URL}/api/skill-runs/${skillRunId}/stream?token=${token}`;
    const es = new EventSource(url);

    es.onopen = () => setConnected(true);
    es.onmessage = (e) => {
      try {
        setEvent(JSON.parse(e.data));
      } catch {
        // ignore parse errors
      }
    };
    es.onerror = () => {
      setConnected(false);
      es.close();
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [skillRunId]);

  return { event, connected };
}

export function getArtifactDownloadUrl(artifactId: string) {
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const token = localStorage.getItem('token');
  return `${API_URL}/api/artifacts/${artifactId}/download?token=${token}`;
}
