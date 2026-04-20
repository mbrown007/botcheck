"use client";

import Link from "next/link";
import type { Route } from "next";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export function AccessPanel({
  title,
  message,
  backHref = "/scenarios",
  backLabel = "Back to dashboard",
}: {
  title: string;
  message: string;
  backHref?: string;
  backLabel?: string;
}) {
  return (
    <Card>
      <CardHeader>
        <span className="text-sm font-medium text-text-secondary">{title}</span>
      </CardHeader>
      <CardBody className="space-y-4">
        <p className="text-sm text-text-muted">{message}</p>
        <Link href={backHref as Route}>
          <Button variant="secondary">{backLabel}</Button>
        </Link>
      </CardBody>
    </Card>
  );
}
