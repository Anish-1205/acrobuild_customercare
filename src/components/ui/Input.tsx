import { forwardRef, type InputHTMLAttributes } from "react";
import { classNames } from "./classNames";

export type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "aria-invalid"> & {
  invalid?: boolean;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid = false, ...props },
  ref
) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={classNames("ab-input", className)}
      ref={ref}
      {...props}
    />
  );
});
