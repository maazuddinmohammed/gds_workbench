import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ValidationLedger } from "./ValidationLedger";
import type { ValidationValidationCheck, ValidationValidationGroup } from "./api";

const check: ValidationValidationCheck = {
  validation_check_id: 2, validation_check_name: "Completeness", validation_check_description: "Checks missing records.",
  validation_category_code: "row_count", validation_severity: "blocking", validation_query_sql: "SELECT 0",
  validation_comparison_query_sql: null, validation_result_data_type: "integer",
  validation_comparison_operator: "equal", validation_comparison_value_type: "literal", validation_comparison_value: 0,
  is_active: true, is_locked: false,
};
const group: ValidationValidationGroup = {
  validation_group_id: 1, validation_group_name: "Customer", validation_group_description: "Customer checks",
  modeled_entity_type: "logical_entity", system_id: 3, system_code: "CRM", mapping_context_is_current: true,
  code_context_is_current: true, validation_group_is_current: true, is_active: true, is_locked: false, checks: [check],
};

describe("Validation criteria", () => {
  it.each([
    ["equal", "equals 0"], ["not_equal", "does not equal 0"], ["greater_than", "is greater than 0"],
    ["greater_than_or_equal", "is greater than or equal to 0"], ["less_than", "is less than 0"],
    ["less_than_or_equal", "is less than or equal to 0"], ["is_null", "is null"], ["is_not_null", "is not null"],
    ["is_true", "is true"], ["is_false", "is false"], ["in", "is in [0,1]"], ["not_in", "is not in [0,1]"],
  ])("explains %s without changing the stored assertion", (operator, expected) => {
    const unary = operator.startsWith("is_");
    const list = operator === "in" || operator === "not_in";
    render(<ValidationLedger tenantId={7} modelId={18} groupId={1} checkId={2} modelRevision={4} loadedModelRevision={4} isLoading={false} error={null}
      groups={[{ ...group, checks: [{ ...check, validation_comparison_operator: operator,
        validation_comparison_value_type: unary ? "none" : list ? "literal_list" : "literal",
        validation_comparison_value: list ? [0, 1] : 0 }] }]} />);
    const criteria = screen.getByLabelText("Pass and fail criteria");
    expect(within(criteria).getByText(`Query A’s result ${expected}.`)).toBeVisible();
    expect(criteria).toHaveTextContent("Query errors or an invalid result shape cannot pass.");
    expect(screen.getByLabelText("Check purpose")).toHaveTextContent("Checks missing records.");
  });

  it("distinguishes execution-only checks from scalar assertions", () => {
    render(<ValidationLedger tenantId={7} modelId={18} groupId={1} checkId={2} modelRevision={4} loadedModelRevision={4} isLoading={false} error={null}
      groups={[{ ...group, checks: [{ ...check, validation_comparison_operator: "executes_successfully",
        validation_comparison_value_type: "none", validation_result_data_type: null, validation_comparison_value: null }] }]} />);
    const criteria = screen.getByLabelText("Pass and fail criteria");
    expect(criteria).toHaveTextContent("Query A completes without an execution error.");
    expect(criteria).toHaveTextContent("Query A produces an execution error.");
    expect(criteria).toHaveTextContent("returned values are ignored");
    expect(criteria).not.toHaveTextContent("One row");
  });
});
