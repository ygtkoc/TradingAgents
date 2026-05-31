import { AdminDataPage, formatDate } from "../../_components/admin-data-page";

export default function SecurityLogsPage() {
  return (
    <AdminDataPage
      eyebrow="Logs"
      title="Security logs"
      description="Security events, API key validation, role-gated actions, and critical alerts."
      table="security_logs"
      searchKeys={["event_type", "severity", "message", "source"]}
      columns={[
        { key: "event_type", label: "Event" },
        { key: "severity", label: "Severity" },
        { key: "source", label: "Source" },
        { key: "message", label: "Message" },
        { key: "resolved", label: "Resolved" },
        { key: "created_at", label: "Created", format: formatDate },
      ]}
    />
  );
}
