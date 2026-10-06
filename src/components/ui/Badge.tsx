import type { HTMLAttributes } from "react";
import { classNames } from "./classNames";

export type BadgeTone = "neutral" | "success" | "warning" | "error" | "info";

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone;
};

export function Badge({ className, tone = "neutral", ...props }: BadgeProps) {
  return <span className={classNames("ab-badge", `ab-badge--${tone}`, className)} {...props} />;
}
