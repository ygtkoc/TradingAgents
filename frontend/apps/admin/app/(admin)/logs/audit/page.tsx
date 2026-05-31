import { AdminDataPage, formatDate } from "../../_components/admin-data-page";

export default function AuditLogsPage() {
  return (
    <AdminDataPage
      eyebrow="Logs"
      title="Audit logs"
      description="Audited operator and system actions."
      table="audit_logs"
      searchKeys={["action", "table_name", "source", "actor_role"]}
      columns={[
        { key: "action", label: "Action" },
        { key: "actor_role", label: "Actor role" },
        { key: "table_name", label: "Table" },
        { key: "source", label: "Source" },
        { key: "created_at", label: "Created", format: formatDate },
      ]}
    />
  );
}
