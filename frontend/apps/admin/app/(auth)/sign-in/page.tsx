import { Suspense } from "react";

import { AdminSignInForm } from "./sign-in-form";

export default function AdminSignInPage() {
  return (
    <Suspense fallback={<div className="h-80 w-full max-w-sm rounded-xl border border-border bg-card" />}>
      <AdminSignInForm />
    </Suspense>
  );
}
