import type { Route } from "next";
import { redirect } from "next/navigation";

export default function DashboardIndex() {
  redirect("/dashboard" as Route);
}
