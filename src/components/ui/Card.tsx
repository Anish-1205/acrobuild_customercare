import { forwardRef, type HTMLAttributes } from "react";
import { classNames } from "./classNames";

export type CardProps = HTMLAttributes<HTMLDivElement>;

export const Card = forwardRef<HTMLDivElement, CardProps>(function Card({ className, ...props }, ref) {
  return <div className={classNames("ab-card", className)} ref={ref} {...props} />;
});
