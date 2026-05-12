// ── Primitives ───────────────────────────────────────────────────────────────
export { Button, buttonVariants }            from "./primitives/button";
export type { ButtonProps }                  from "./primitives/button";

export {
  Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle,
} from "./primitives/card";

export { Badge, badgeVariants }              from "./primitives/badge";
export type { BadgeProps }                   from "./primitives/badge";

export { Skeleton }                          from "./primitives/skeleton";
export { Separator }                         from "./primitives/separator";

export { Tabs, TabsContent, TabsList, TabsTrigger } from "./primitives/tabs";

export { Avatar, AvatarFallback, AvatarImage }      from "./primitives/avatar";

export {
  DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuPortal, DropdownMenuRadioGroup, DropdownMenuSeparator,
  DropdownMenuSub, DropdownMenuTrigger,
} from "./primitives/dropdown-menu";

export {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogOverlay, DialogPortal, DialogTitle, DialogTrigger,
} from "./primitives/dialog";

export {
  Sheet, SheetClose, SheetContent, SheetHeader, SheetPortal, SheetTitle, SheetTrigger,
} from "./primitives/sheet";

export { Input }    from "./primitives/input";
export { Progress } from "./primitives/progress";
export { Label } from "./primitives/label";
export { Switch } from "./primitives/switch";

export {
  Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue,
} from "./primitives/select";

export {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "./primitives/table";

// ── Data display ─────────────────────────────────────────────────────────────
export { DataTable }                         from "./data-display/data-table";
export type { ColumnDef }                    from "./data-display/data-table";
export { KpiCard }                           from "./data-display/kpi-card";

// ── Feedback ─────────────────────────────────────────────────────────────────
export { EmptyState }                        from "./feedback/empty-state";
export { ErrorState }                        from "./feedback/error-state";
export {
  ApprovalBadge, LifecycleBadge, ModeBadge, StatusBadge,
} from "./feedback/status-badge";

// ── Layout ───────────────────────────────────────────────────────────────────
export { AppShell }                          from "./layout/app-shell";
export { PageHeader }                        from "./layout/page-header";
