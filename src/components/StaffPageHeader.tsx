type StaffPageHeaderProps = {
  description: string;
  eyebrow: string;
  title: string;
};

export function StaffPageHeader({ description, eyebrow, title }: StaffPageHeaderProps) {
  return (
    <header className="staff-page-header">
      <div className="staff-page-eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  );
}
