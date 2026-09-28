"use client";

/** 开关 */
export default function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            onClick={() => onChange(!checked)}
            className={`relative h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors ${checked ? 'bg-foreground' : 'bg-muted'}`}
        >
            <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-background shadow transition-all ${checked ? 'left-4.5' : 'left-0.5'}`}
            />
        </button>
    );
}
