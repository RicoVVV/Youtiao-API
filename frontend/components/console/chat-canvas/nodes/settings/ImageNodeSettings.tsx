"use client";
import { useTranslation } from "react-i18next";
import { ArrowLeftRight } from 'lucide-react';
import Toggle from '../shared/Toggle';
import type { ImageNodeData } from '../ImageNode';

/** 宽高比选项及对应尺寸 */
const RATIO_OPTIONS = [
    { label: '1:1', w: 1024, h: 1024 },
    { label: '3:2', w: 1152, h: 768 },
    { label: '2:3', w: 768, h: 1152 },
    { label: '4:3', w: 1088, h: 816 },
    { label: '3:4', w: 816, h: 1088 },
    { label: '16:9', w: 1280, h: 720 },
    { label: '9:16', w: 720, h: 1280 },
    { label: '1:1(2K)', w: 2048, h: 2048 },
    { label: '16:9(2K)', w: 2560, h: 1440 },
    { label: '9:16(2K)', w: 1440, h: 2560 },
    { label: '16:9(4K)', w: 3840, h: 2160 },
    { label: '9:16(4K)', w: 2160, h: 3840 },
];

// 生成张数选项
const COUNT_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const MAX_COUNT = 20;

/** 宽高比示意小图形：最长边固定，短边按比例缩放 */
const ratioShape = (w: number, h: number): { width: number; height: number } => {
    const max = 16;
    return w >= h
        ? { width: max, height: Math.max(4, Math.round((max * h) / w)) }
        : { width: Math.max(4, Math.round((max * w) / h)), height: max };
};

/** 图像设置参数区：尺寸 / 宽高比 / 透明背景 / 生成张数 */
export default function ImageNodeSettings({
    data,
    update,
}: {
    data: ImageNodeData;
    update: (patch: Partial<ImageNodeData>) => void;
}) {
    const { t } = useTranslation("canvas");

    /** 尺寸输入：开启 16 倍数对齐时取整到 16 的倍数 */
    const setSize = (key: 'width' | 'height', value: number) => {
        const v = Math.max(16, value || 16);
        update({ [key]: data.align16 ? Math.round(v / 16) * 16 : v });
    };

    return (
        <>
            {/* 尺寸 */}
            <div className="mt-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{t('settings.size')}</span>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    {t('settings.align16')}
                    <Toggle checked={data.align16} onChange={v => update({ align16: v })} />
                </label>
            </div>
            <div className="mt-2 flex items-center gap-2">
                <label className="flex flex-1 items-center gap-2 rounded-full bg-muted px-3 py-1.5">
                    <span className="text-xs text-muted-foreground">W</span>
                    <input
                        type="number"
                        min={16}
                        value={data.width}
                        onChange={e => setSize('width', Number(e.target.value))}
                        className="w-full bg-transparent text-xs text-foreground outline-none"
                    />
                </label>
                <button
                    type="button"
                    aria-label={t('settings.swap')}
                    onClick={() => update({ width: data.height, height: data.width })}
                    className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent"
                >
                    <ArrowLeftRight className="h-3.5 w-3.5" />
                </button>
                <label className="flex flex-1 items-center gap-2 rounded-full bg-muted px-3 py-1.5">
                    <span className="text-xs text-muted-foreground">H</span>
                    <input
                        type="number"
                        min={16}
                        value={data.height}
                        onChange={e => setSize('height', Number(e.target.value))}
                        className="w-full bg-transparent text-xs text-foreground outline-none"
                    />
                </label>
            </div>

            {/* 宽高比 */}
            <div className="mt-3 text-xs text-muted-foreground">{t('settings.ratio')}</div>
            <div className="mt-2 grid grid-cols-4 gap-2">
                {RATIO_OPTIONS.map(opt => (
                    <button
                        key={opt.label}
                        type="button"
                        onClick={() => update({ ratio: opt.label, width: opt.w, height: opt.h })}
                        className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border py-2.5 text-xs transition-colors ${
                            data.ratio === opt.label
                                ? 'border-foreground text-foreground'
                                : 'border-border text-muted-foreground hover:border-muted-foreground'
                        }`}
                    >
                        <span
                            className="rounded-[2px] border-[1.5px] border-current"
                            style={ratioShape(opt.w, opt.h)}
                        />
                        {opt.label}
                    </button>
                ))}
                <button
                    type="button"
                    onClick={() => update({ ratio: 'auto' })}
                    className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border py-2.5 text-xs transition-colors ${
                        data.ratio === 'auto'
                            ? 'border-foreground text-foreground'
                            : 'border-border text-muted-foreground hover:border-muted-foreground'
                    }`}
                >
                    {t('settings.auto')}
                </button>
            </div>

            {/* 透明背景 */}
            <div className="mt-4 flex items-center justify-between gap-3">
                <div>
                    <div className="text-xs text-foreground">{t('settings.transparent')}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{t('settings.transparentDesc')}</div>
                </div>
                <Toggle checked={data.transparent} onChange={v => update({ transparent: v })} />
            </div>

            {/* 生成张数 */}
            <div className="mt-4 text-xs text-muted-foreground">{t('settings.imageCount')}</div>
            <div className="mt-2 grid grid-cols-4 gap-2">
                {COUNT_OPTIONS.map(n => (
                    <button
                        key={n}
                        type="button"
                        onClick={() => update({ count: n })}
                        className={`cursor-pointer rounded-full border py-1.5 text-xs transition-colors ${
                            data.count === n
                                ? 'border-foreground text-foreground'
                                : 'border-border text-muted-foreground hover:border-muted-foreground'
                        }`}
                    >
                        {t('settings.countUnit', { count: n })}
                    </button>
                ))}
                {/* 自定义张数输入 */}
                <input
                    type="number"
                    min={1}
                    max={MAX_COUNT}
                    value={data.count}
                    onChange={e => {
                        const v = Math.round(Number(e.target.value) || 1);
                        update({ count: Math.min(MAX_COUNT, Math.max(1, v)) });
                    }}
                    className={`rounded-full border bg-transparent py-1.5 text-center text-xs outline-none transition-colors ${
                        COUNT_OPTIONS.includes(data.count)
                            ? 'border-border text-muted-foreground'
                            : 'border-foreground text-foreground'
                    }`}
                />
            </div>
        </>
    );
}
