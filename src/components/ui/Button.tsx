import { forwardRef, type ButtonHTMLAttributes } from "react";
import { classNames } from "./classNames";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, type = "button", variant = "primary", ...props },
  ref
) {
  return (
    <button
      className={classNames("ab-button", `ab-button--${variant}`, className)}
      ref={ref}
      type={type}
      {...props}
    />
  );
});
