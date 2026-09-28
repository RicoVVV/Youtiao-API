/* ── Section 组件 ── */

export function SectionHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div>
      <h3 className="text-base font-semibold">{title}</h3>
      {description && (
        <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
      )}
    </div>
  );
}

export function FieldLabel({
  label,
  hint,
  tag,
  tagVariant = "default",
}: {
  label: string;
  hint?: string;
  tag?: string;
  tagVariant?: "default" | "primary";
}) {
  return (
    <div>
      <p className="text-sm font-medium">
        {label}
        {tag && (
          <span
            className={
              tagVariant === "primary"
                ? "ml-2 inline-block rounded bg-primary/10 px-1.5 py-0.5 text-xs text-primary"
                : "ml-2 inline-block rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
            }
          >
            {tag}
          </span>
        )}
      </p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
