import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ta/ui";

export default function AdminSignInPage() {
  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Admin access</CardTitle>
        <CardDescription>
          Operations access is restricted to authenticated admins. Non-admin accounts are denied from every admin route.
        </CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Authentication UI is intentionally minimal until the admin flow is wired to the production identity policy.
      </CardContent>
    </Card>
  );
}
