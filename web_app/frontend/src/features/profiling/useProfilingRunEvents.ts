import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import type { WorkflowRunEvent } from "../workflows/api";
import { profilingQueryKeys, type ProfilingApi } from "./api";

export function useProfilingRunEvents({
  api,
  tenantId,
  modelId,
  runId,
  poll,
}: {
  api: ProfilingApi;
  tenantId: number;
  modelId: number;
  runId: number;
  poll: boolean;
}) {
  const [cursor, setCursor] = useState({ runId, sequence: 0 });
  const [events, setEvents] = useState<WorkflowRunEvent[]>([]);
  const afterSequence = cursor.runId === runId ? cursor.sequence : 0;
  const query = useQuery({
    queryKey: profilingQueryKeys.events(tenantId, modelId, runId, afterSequence),
    queryFn: () => api.listWorkflowRunEvents(
      tenantId,
      modelId,
      runId,
      afterSequence,
    ),
    refetchInterval: poll ? 2_000 : false,
  });

  useEffect(() => {
    setEvents([]);
    setCursor({ runId, sequence: 0 });
  }, [runId]);

  useEffect(() => {
    const collection = query.data;
    if (!collection) return;
    setEvents((current) => {
      const merged = new Map(current.map((event) => [event.sequence, event]));
      for (const event of collection.items) merged.set(event.sequence, event);
      return [...merged.values()].sort((left, right) => left.sequence - right.sequence);
    });
    if (collection.next_after_sequence > afterSequence) {
      setCursor({ runId, sequence: collection.next_after_sequence });
    }
  }, [afterSequence, query.data, runId]);

  return { events, query };
}
