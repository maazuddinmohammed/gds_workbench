import { vi } from "vitest";
import type { ModelRecordHistoryPage, ModelReviewCommand, ModelReviewPreview } from "../features/model_record_review/api";

export function withRecordReview(base: typeof fetch, history?: ModelRecordHistoryPage) {
  const commands: ModelReviewCommand[] = [];
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async (input, init) => {
    const url = String(input);
    if (!url.includes("/change-sets/review")) return base(input, init);
    if (url.includes("/review/records")) return new Response(JSON.stringify(history), {
      headers: { "content-type": "application/json" },
    });
    const command = JSON.parse(String(init?.body)) as ModelReviewCommand;
    commands.push(command);
    const preview: ModelReviewPreview = {
      model_id: 18, model_revision: 18, plan_digest: "c".repeat(64), can_apply: true,
      action_count: command.record_ids.length, additional_change_count: 0,
      total_record_count: command.record_ids.length, issue_count: 0, issues: [], page: 1, next_page: null,
      items: command.record_ids.map((record_id) => ({
        dataset: command.dataset, record_id, label: `Selected record ${record_id}`, selected: true,
        reason: "Selected record.", is_locked: false, desired_locked: true,
        status: "active", desired_status: "active", changed: true,
      })),
    };
    return new Response(JSON.stringify(url.includes("/preview") ? preview : {
      model_id: 18, model_revision: 19, model_change_set_id: "receipt", action_count: command.record_ids.length,
    }), { headers: { "content-type": "application/json" } });
  });
  return { fetcher, commands };
}
