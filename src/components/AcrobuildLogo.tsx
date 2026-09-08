type AcrobuildLogoProps = {
  className?: string;
  subtitle?: string;
};

export function AcrobuildLogo({
  className = "",
  subtitle = "Project support desk"
}: AcrobuildLogoProps) {
  const rootClassName = `acrobuild-logo${className ? ` ${className}` : ""}`;

  return (
    <span className={rootClassName}>
      <span className="acrobuild-logo-mark-shell" aria-hidden="true">
        <img alt="" className="acrobuild-logo-mark" src="/Acrobuild_logo.png?v=20260730-2" />
      </span>
      <span className="acrobuild-logo-copy">
        <span className="acrobuild-logo-title">ACROBUILD</span>
        {subtitle ? <span className="acrobuild-logo-subtitle">{subtitle}</span> : null}
      </span>
    </span>
  );
}
