import Link from "next/link";

import { buttonVariants, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ta/ui";


export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col items-center justify-center gap-8 px-6 py-16 text-center">
      <h1 className="text-4xl font-semibold tracking-tight md:text-6xl">TradingAgents</h1>
      <p className="max-w-xl text-balance text-muted-foreground">
        Multi-agent AI trading platform. Paper trade, shadow test, and execute
        with full audit and risk controls.
      </p>
      <div className="flex gap-3">
        <Link href="/pricing" className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
          Pricing
        </Link>
        <Link
          href={process.env.NEXT_PUBLIC_CUSTOMER_URL ?? "http://localhost:3001"}
          className={buttonVariants({ variant: "outline" })}
        >
          Sign in
        </Link>
      </div>

      <Card className="mt-12 w-full max-w-md text-left">
        <CardHeader>
          <CardTitle>Scaffold ready</CardTitle>
          <CardDescription>
            Marketing app placeholder. Real landing copy lands in a follow-up task.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Apps: marketing · customer · admin · packages: ui · supabase · types · query · schemas · utils · config
        </CardContent>
      </Card>
    </main>
  );
}
