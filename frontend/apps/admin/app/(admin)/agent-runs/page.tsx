import { AdminDataPage, formatDate } from "../_components/admin-data-page";

export default function AgentRunsPage() {
  return (
    <AdminDataPage
      eyebrow="Workers"
      title="Agent runs"
      description="Agent orchestration runs, status, and run timing."
      table="agent_runs"
      searchKeys={["status", "run_type", "symbol"]}
      columns={[
        { key: "run_type", label: "Type" },
        { key: "status", label: "Status" },
        { key: "symbol", label: "Symbol" },
        { key: "started_at", label: "Started", format: formatDate },
        { key: "completed_at", label: "Completed", format: formatDate },
        { key: "created_at", label: "Created", format: formatDate },
      ]}
    />
  );
}
