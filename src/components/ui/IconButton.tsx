import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { classNames } from "./classNames";

export type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  "aria-label": string;
  children: ReactNode;
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { className, type = "button", ...props },
  ref
) {
  return <button className={classNames("ab-icon-button", className)} ref={ref} type={type} {...props} />;
});
