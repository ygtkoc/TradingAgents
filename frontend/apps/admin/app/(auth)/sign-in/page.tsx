import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ta/ui";

export default function AdminSignInPage() {
  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Admin sign in</CardTitle>
        <CardDescription>
          Auth UI lands in a later task. Non-admin authenticated users hit a 404
          on every other admin route.
        </CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">Placeholder.</CardContent>
    </Card>
  );
}
