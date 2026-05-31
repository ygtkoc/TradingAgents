import { AdminDataPage, formatDate } from "../_components/admin-data-page";

export default function ReconciliationPage() {
  return (
    <AdminDataPage
      eyebrow="Operations"
      title="Reconciliation"
      description="Trades that need reconciliation or lifecycle attention."
      table="trades"
      searchKeys={["symbol", "lifecycle_status", "lifecycle_error", "status"]}
      columns={[
        { key: "symbol", label: "Symbol" },
        { key: "status", label: "Status" },
        { key: "lifecycle_status", label: "Lifecycle" },
        { key: "lifecycle_error", label: "Error" },
        { key: "close_reason", label: "Close reason" },
        { key: "updated_at", label: "Updated", format: formatDate },
      ]}
    />
  );
}
