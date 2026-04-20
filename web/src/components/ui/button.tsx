import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import React from "react";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-brand text-text-inverse hover:bg-brand-hover",
        secondary:
          "bg-bg-elevated border border-border text-text-primary hover:bg-bg-subtle",
        ghost: "text-text-secondary hover:bg-bg-elevated hover:text-text-primary",
        destructive: "bg-fail-bg border border-fail-border text-fail hover:bg-fail/10",
      },
      size: {
        icon: "h-7 w-7 p-0 text-xs",
        sm: "h-7 px-3 text-xs",
        md: "h-9 px-4",
        lg: "h-10 px-6 text-base",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
);
Button.displayName = "Button";
