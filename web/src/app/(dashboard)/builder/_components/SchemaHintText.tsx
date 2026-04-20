"use client";

import React from "react";

interface SchemaHintTextProps {
  hint: string | null;
}

export function SchemaHintText({ hint }: SchemaHintTextProps) {
  if (!hint) {
    return null;
  }

  return <p className="mt-1 text-[10px] normal-case tracking-normal text-text-muted">{hint}</p>;
}
