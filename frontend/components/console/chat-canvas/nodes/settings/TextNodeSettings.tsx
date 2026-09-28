"use client";
import { useTranslation } from "react-i18next";
import type { TextNodeData } from '../TextNode';

/** 推理强度选项：value 为存储值（持久化兼容），labelKey 用于 i18n 显示 */
const REASONING_OPTIONS: { value: string; labelKey: string }[] = [
    { value: '自动', labelKey: 'settings.reasoningAuto' },
    { value: '低', labelKey: 'settings.reasoningLow' },
    { value: '中', labelKey: 'settings.reasoningMedium' },
    { value: '高', labelKey: 'settings.reasoningHigh' },
    { value: '极高', labelKey: 'settings.reasoningExtraHigh' },
];

/** 文本设置参数区：推理强度 / 生成次数 */
export default function TextNodeSettings({
    data,
    update,
}: {
    data: TextNodeData;
    update: (patch: Partial<TextNodeData>) => void;
}) {
    const { t } = useTranslation("canvas");

    return (
        <>
            <div className="mt-3 text-xs text-muted-foreground">{t('settings.reasoning')}</div>
            <div className="mt-2 flex flex-wrap gap-2">
                {REASONING_OPTIONS.map(opt => (
                    <button
                        key={opt.value}
                        type="button"
                        onClick={() => update({ reasoning: opt.value })}
                        className={`cursor-pointer rounded-full border px-3 py-1 text-xs transition-colors ${
                            data.reasoning === opt.value
                                ? 'border-foreground text-foreground'
                                : 'border-border text-muted-foreground hover:border-muted-foreground'
                        }`}
                    >
                        {t(opt.labelKey)}
                    </button>
                ))}
            </div>
            {/* 生成次数字段暂时隐藏，默认按 1 次生成
            <div className="mt-3 text-xs text-muted-foreground">{t('settings.count')}</div>
            <input
                type="number"
                min={1}
                value={data.count}
                onChange={e => update({ count: Math.max(1, Number(e.target.value) || 1) })}
                className="mt-2 w-20 rounded-lg border border-border bg-background px-2 py-1 text-xs text-foreground outline-none focus:border-primary"
            />
            */}
        </>
    );
}
