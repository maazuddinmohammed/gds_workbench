import type { ColumnDef } from "@tanstack/react-table";

export interface ModelReviewSelection {
  selectedIds: Set<number>;
  onSelectionChange: (ids: Set<number>) => void;
}

export function reviewSelectionColumn<T>(
  items: T[], selection: ModelReviewSelection, getId: (item: T) => number, label: string,
): ColumnDef<T> {
  const { selectedIds, onSelectionChange } = selection;
  return {
    id: "selection",
    header: () => <input className="model-review-checkbox" type="checkbox" aria-label={`Select loaded ${label}`}
      checked={items.length > 0 && items.every((item) => selectedIds.has(getId(item)))}
      onChange={(event) => onSelectionChange(event.target.checked
        ? new Set(items.map(getId)) : new Set())} />,
    cell: ({ row }) => <input className="model-review-checkbox" type="checkbox" aria-label={`Select ${label} ${getId(row.original)}`}
      checked={selectedIds.has(getId(row.original))}
      onChange={(event) => {
        const ids = new Set(selectedIds);
        if (event.target.checked) ids.add(getId(row.original));
        else ids.delete(getId(row.original));
        onSelectionChange(ids);
      }} />,
  };
}
