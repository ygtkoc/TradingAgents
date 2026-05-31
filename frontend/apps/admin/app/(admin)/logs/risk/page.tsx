import { AdminDataPage, formatDate } from "../../_components/admin-data-page";

export default function RiskLogsPage() {
  return (
    <AdminDataPage
      eyebrow="Logs"
      title="Risk logs"
      description="Risk guard triggers, blocked executions, and portfolio safety events."
      table="risk_logs"
      searchKeys={["risk_type", "severity", "message"]}
      columns={[
        { key: "risk_type", label: "Risk type" },
        { key: "severity", label: "Severity" },
        { key: "triggered", label: "Triggered" },
        { key: "message", label: "Message" },
        { key: "created_at", label: "Created", format: formatDate },
      ]}
    />
  );
}
