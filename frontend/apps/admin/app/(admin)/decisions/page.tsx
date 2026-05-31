import { AdminDataPage, formatDate } from "../_components/admin-data-page";

export default function DecisionsPage() {
  return (
    <AdminDataPage
      eyebrow="Intelligence"
      title="Decisions"
      description="Trade decisions, approval state, execution status, and final agent verdict."
      table="trade_decisions"
      searchKeys={["symbol", "direction", "final_decision", "approval_status", "execution_status"]}
      columns={[
        { key: "symbol", label: "Symbol" },
        { key: "direction", label: "Direction" },
        { key: "final_decision", label: "Decision" },
        { key: "approval_status", label: "Approval" },
        { key: "execution_status", label: "Execution" },
        { key: "manual_approval_required", label: "Manual" },
        { key: "created_at", label: "Created", format: formatDate },
      ]}
    />
  );
}
