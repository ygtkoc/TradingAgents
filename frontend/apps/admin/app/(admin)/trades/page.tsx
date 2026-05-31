import { AdminDataPage, formatDate, money } from "../_components/admin-data-page";

export default function TradesPage() {
  return (
    <AdminDataPage
      eyebrow="Trading"
      title="Trades"
      description="All visible platform trades with status, lifecycle, P&L, and execution mode."
      table="trades"
      searchKeys={["symbol", "status", "direction", "mode", "lifecycle_status"]}
      columns={[
        { key: "symbol", label: "Symbol" },
        { key: "direction", label: "Side" },
        { key: "mode", label: "Mode" },
        { key: "status", label: "Status" },
        { key: "lifecycle_status", label: "Lifecycle" },
        { key: "realized_pnl", label: "Realized", format: money },
        { key: "unrealized_pnl", label: "Unrealized", format: money },
        { key: "created_at", label: "Created", format: formatDate },
      ]}
    />
  );
}
