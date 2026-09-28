"use client";
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

/** 提示词放大编辑弹窗 */
export default function PromptEditModal({
    value,
    onChange,
    onClose,
    placeholder,
}: {
    value: string;
    onChange: (v: string) => void;
    onClose: () => void;
    placeholder: string;
}) {
    return createPortal(
        <div className="fixed inset-0 z-100 flex items-center justify-center bg-black/50" onClick={onClose}>
            <div
                className="flex h-[70vh] w-[80vw] max-w-4xl flex-col rounded-2xl bg-popover p-6 shadow-card"
                onClick={e => e.stopPropagation()}
            >
                <div className="mb-4 flex items-center justify-between">
                    <span className="text-lg font-medium text-popover-foreground">编辑提示词</span>
                    <button
                        type="button"
                        aria-label="关闭"
                        onClick={onClose}
                        className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>
                <textarea
                    autoFocus
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    placeholder={placeholder}
                    className="flex-1 resize-none rounded-xl border border-border bg-transparent p-4 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
                />
            </div>
        </div>,
        document.body,
    );
}
