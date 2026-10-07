"use client";
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, KeyRound } from 'lucide-react';
import { useCanvasApiKeys } from '../../models-context';

interface ApiKeySelectProps {
    /** 当前选中的密钥 id（节点 data.apiKeyId），空则默认取列表第一个 */
    value?: string;
    onChange: (v: string) => void;
    /** 面板展开方向：up 向上（节点底部工具栏），down 向下（生成配置节点） */
    placement?: 'up' | 'down';
}

/** API 密钥下拉（图标按钮 + 状态点，参照操练场输入框左侧的密钥选择） */
export default function ApiKeySelect({ value, onChange, placement = 'up' }: ApiKeySelectProps) {
    const { t } = useTranslation('canvas');
    const [open, setOpen] = useState(false);
    const keys = useCanvasApiKeys();

    /** 生效密钥：未选时默认列表第一个 */
    const active = value || keys[0]?.value || '';
    const activeLabel = keys.find(k => k.value === active)?.label;

    return (
        <div className="relative">
            <button
                type="button"
                aria-label={t('common.selectApiKey')}
                title={activeLabel || t('common.selectApiKey')}
                onClick={() => setOpen(v => !v)}
                className="relative flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border border-border bg-popover text-muted-foreground transition-colors hover:bg-accent"
            >
                <KeyRound className="h-3.5 w-3.5" />
                {/* 状态点：已选绿色，未选/无可用灰色 */}
                <span className={`absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full ${active ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`} />
            </button>
            {open && (
                <>
                    <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
                    <div className={`nowheel absolute left-0 z-50 max-h-72 w-56 overflow-y-auto rounded-xl border border-border bg-popover p-1 shadow-card ${placement === 'up' ? 'bottom-[calc(100%+8px)]' : 'top-[calc(100%+8px)]'}`}>
                        {keys.length === 0 ? (
                            <div className="px-3 py-2 text-xs text-muted-foreground">{t('common.noApiKey')}</div>
                        ) : (
                            keys.map(k => (
                                <button
                                    key={k.value}
                                    type="button"
                                    onClick={() => {
                                        onChange(k.value);
                                        setOpen(false);
                                    }}
                                    className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-left transition-colors hover:bg-accent"
                                >
                                    <span className="min-w-0 truncate text-xs text-foreground">{k.label || k.value}</span>
                                    {k.value === active && <Check className="h-3.5 w-3.5 shrink-0 text-primary" />}
                                </button>
                            ))
                        )}
                    </div>
                </>
            )}
        </div>
    );
}
