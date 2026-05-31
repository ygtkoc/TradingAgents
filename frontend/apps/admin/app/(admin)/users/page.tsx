import { AdminDataPage, formatDate } from "../_components/admin-data-page";

export default function UsersPage() {
  return (
    <AdminDataPage
      eyebrow="Identity"
      title="Users"
      description="Customer profiles, roles, risk state, and subscription visibility."
      table="profiles"
      searchKeys={["email", "role", "subscription_status", "risk_level"]}
      columns={[
        { key: "email", label: "Email" },
        { key: "role", label: "Role" },
        { key: "subscription_status", label: "Subscription" },
        { key: "risk_level", label: "Risk" },
        { key: "is_banned", label: "Banned" },
        { key: "created_at", label: "Created", format: formatDate },
      ]}
    />
  );
}
