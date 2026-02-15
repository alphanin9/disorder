import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib-utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white hover:bg-blue-700 focus:ring-blue-500",
        secondary: "bg-white text-ink border border-slate-300 hover:bg-slate-50 focus:ring-slate-400",
        danger: "bg-danger text-white hover:bg-red-800 focus:ring-red-500",
        ghost: "bg-transparent text-ink hover:bg-slate-100 focus:ring-slate-400",
      },
    },
    defaultVariants: {
      variant: "primary",
    },
  },
);

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant }), className)} {...props} />;
}
