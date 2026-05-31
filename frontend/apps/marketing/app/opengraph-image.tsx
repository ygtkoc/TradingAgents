import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Lucrandos AI Trading System live decision dashboard";
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#07090b",
          color: "#f8fafc",
          padding: 64,
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 16,
              border: "2px solid #2dd4bf",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#ccfbf1",
              fontSize: 30,
              fontWeight: 800,
            }}
          >
            L
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 30, fontWeight: 800 }}>Lucrandos</div>
            <div style={{ color: "#5eead4", fontSize: 18, letterSpacing: 3 }}>AI TRADING SYSTEM</div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          <div style={{ color: "#5eead4", fontSize: 22, letterSpacing: 4 }}>MULTI-AGENT CRYPTO DECISIONS</div>
          <div style={{ maxWidth: 920, fontSize: 76, lineHeight: 0.95, fontWeight: 800 }}>
            Live decisions, risk controls, and trade results.
          </div>
          <div style={{ display: "flex", gap: 16, fontSize: 24 }}>
            {["Agent scoring", "Paper trading", "Lifecycle monitoring"].map((label) => (
              <div
                key={label}
                style={{
                  border: "1px solid rgba(45, 212, 191, 0.35)",
                  background: "rgba(45, 212, 191, 0.1)",
                  color: "#ccfbf1",
                  borderRadius: 14,
                  padding: "14px 18px",
                }}
              >
                {label}
              </div>
            ))}
          </div>
        </div>
      </div>
    ),
    size,
  );
}
