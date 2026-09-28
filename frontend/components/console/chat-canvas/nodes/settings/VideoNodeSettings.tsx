"use client";
import { useEffect } from 'react';
import { useTranslation } from "react-i18next";
import { ArrowLeftRight } from 'lucide-react';
import { useCanvasConfigStore } from '@/stores/use-canvas-config-store';
import { H3_SIZE_TABLE, findH3Size } from '../../api/generate';
import type { VideoNodeData } from '../VideoNode';

/** 尺寸选项及对应宽高：value 为存储值（持久化兼容），labelKey 用于 i18n 显示 */
const SIZE_OPTIONS: { value: string; labelKey: string; w: number; h: number }[] = [
    { value: '横屏', labelKey: 'settings.ratioLandscape', w: 1280, h: 720 },
    { value: '竖屏', labelKey: 'settings.ratioPortrait', w: 720, h: 1280 },
    { value: '方形', labelKey: 'settings.ratioSquare', w: 1024, h: 1024 },
    { value: '宽屏', labelKey: 'settings.ratioWide', w: 1792, h: 1024 },
    { value: '长图', labelKey: 'settings.ratioTall', w: 1024, h: 1792 },
];

const AUTO_SIZE = { ratio: 'auto', labelKey: 'settings.auto' };

/** 旧存档的中文比例存储值 → i18n label key（minimax_h3 的 16:9 等比例值不在此列） */
const LEGACY_RATIO_LABEL_KEYS: Record<string, string> = {
    横屏: 'settings.ratioLandscape',
    竖屏: 'settings.ratioPortrait',
    方形: 'settings.ratioSquare',
    宽屏: 'settings.ratioWide',
    长图: 'settings.ratioTall',
    auto: 'settings.auto',
};

/**
 * 视频摘要首段文案：旧中文比例走 i18n；H3 比例（16:9 等）按宽高反查清晰度显示（如 768P）；都不匹配显示原始值。
 * 注意：原始值不能直接传给 t()，16:9 中的冒号会被 i18next 当作命名空间分隔符（t('16:9') 会错误显示为 "9"）
 */
export function videoRatioSummaryLabel(ratio: string, width: number, height: number, t: (key: string) => string): string {
    const labelKey = LEGACY_RATIO_LABEL_KEYS[ratio];
    if (labelKey) return t(labelKey);
    return findH3Size(width, height)?.q ?? ratio;
}

/** 秒数选项 */
const SECONDS_OPTIONS = [4, 6, 10, 12, 15];

/* ---------------- minimax_h3：清晰度 × 比例 查表定尺寸 ---------------- */

type H3Quality = '480P' | '768P' | '1080P';

const H3_QUALITIES: H3Quality[] = ['480P', '768P', '1080P'];

/** 尺寸示意小图形：最长边固定，短边按比例缩放 */
const ratioShape = (w: number, h: number): { width: number; height: number } => {
    const max = 18;
    return w >= h
        ? { width: max, height: Math.max(6, Math.round((max * h) / w)) }
        : { width: Math.max(6, Math.round((max * w) / h)), height: max };
};

/** 视频设置参数区：尺寸 / 预设尺寸 / 秒数；minimax_h3 模型时改为 清晰度 × 比例 查表定尺寸 */
export default function VideoNodeSettings({
    data,
    update,
}: {
    data: VideoNodeData;
    update: (patch: Partial<VideoNodeData>) => void;
}) {
    const { t } = useTranslation("canvas");
    const config = useCanvasConfigStore(s => s.config);
    /** 生效模型：节点未选时回退到默认视频模型 */
    const activeModel = data.model || config.videoModel || '';
    const isH3 = activeModel.includes('minimax_h3');

    /** 当前宽高在表中的位置；不在表内则按 768P·16:9 兜底 */
    const h3Sel = findH3Size(data.width, data.height);
    const quality: H3Quality = (h3Sel?.q as H3Quality) ?? '768P';
    const h3Ratio = h3Sel?.r ?? '16:9';

    // 切换/生效为 minimax_h3 且当前尺寸不在支持表内时，自动对齐到 768P·16:9
    useEffect(() => {
        if (isH3 && !h3Sel) update({ ratio: '16:9', width: 1376, height: 768 });
    }, [isH3, h3Sel, update]);

    /** 清晰度变更：保持当前比例，按表取对应尺寸 */
    const setQuality = (q: H3Quality) => {
        const [w, h] = H3_SIZE_TABLE[h3Ratio][q];
        update({ ratio: h3Ratio, width: w, height: h });
    };

    /** 比例变更：保持当前清晰度，按表取对应尺寸 */
    const setH3Ratio = (r: string) => {
        const [w, h] = H3_SIZE_TABLE[r][quality];
        update({ ratio: r, width: w, height: h });
    };

    /** 尺寸输入（非 minimax_h3 模型） */
    const setSize = (key: 'width' | 'height', value: number) => {
        update({ [key]: Math.max(16, value || 16) });
    };

    return (
        <>
            {isH3 ? (
                <>
                    {/* minimax_h3：清晰度 */}
                    <div className="mt-3 text-xs text-muted-foreground">{t('settings.clarity')}</div>
                    <div className="mt-2 grid grid-cols-3 gap-2">
                        {H3_QUALITIES.map(q => (
                            <button
                                key={q}
                                type="button"
                                onClick={() => setQuality(q)}
                                className={`cursor-pointer rounded-full border py-1.5 text-xs transition-colors ${
                                    quality === q
                                        ? 'border-foreground text-foreground'
                                        : 'border-border text-muted-foreground hover:border-muted-foreground'
                                }`}
                            >
                                {q}
                            </button>
                        ))}
                    </div>

                    {/* minimax_h3：比例（按当前清晰度显示对应尺寸） */}
                    <div className="mt-4 text-xs text-muted-foreground">{t('settings.videoRatio')}</div>
                    <div className="mt-2 grid grid-cols-4 gap-2">
                        {Object.entries(H3_SIZE_TABLE).map(([r, qs]) => {
                            const [w, h] = qs[quality];
                            return (
                                <button
                                    key={r}
                                    type="button"
                                    onClick={() => setH3Ratio(r)}
                                    className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border py-2 text-xs transition-colors ${
                                        h3Ratio === r
                                            ? 'border-foreground text-foreground'
                                            : 'border-border text-muted-foreground hover:border-muted-foreground'
                                    }`}
                                >
                                    <span
                                        className="rounded-[2px] border-[1.5px] border-current"
                                        style={ratioShape(w, h)}
                                    />
                                    {r}
                                    <span className="text-[10px] text-muted-foreground">{w}x{h}</span>
                                </button>
                            );
                        })}
                    </div>

                    {/* 生成参数回显：按清晰度与比例查表得到的尺寸将作为接口 size 参数 */}
                    <div className="mt-3 rounded-xl bg-muted px-3 py-2 text-xs text-muted-foreground">
                        {t('settings.videoSize')} <span className="font-medium text-foreground">{data.width}x{data.height}</span>
                        <span className="ml-1">（{quality} · {h3Ratio}）</span>
                    </div>
                </>
            ) : (
                <>
                    {/* 尺寸 */}
                    <div className="mt-3 text-xs text-muted-foreground">{t('settings.size')}</div>
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

                    {/* 预设尺寸 */}
                    <div className="mt-2 grid grid-cols-3 gap-2">
                        {SIZE_OPTIONS.map(opt => (
                            <button
                                key={opt.value}
                                type="button"
                                onClick={() => update({ ratio: opt.value, width: opt.w, height: opt.h })}
                                className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border py-2.5 text-xs transition-colors ${
                                    data.ratio === opt.value
                                        ? 'border-foreground text-foreground'
                                        : 'border-border text-muted-foreground hover:border-muted-foreground'
                                }`}
                            >
                                <span
                                    className="rounded-[2px] border-[1.5px] border-current"
                                    style={ratioShape(opt.w, opt.h)}
                                />
                                {t(opt.labelKey)}
                                <span className="text-[10px] text-muted-foreground">{opt.w}x{opt.h}</span>
                            </button>
                        ))}
                        <button
                            type="button"
                            onClick={() => update({ ratio: AUTO_SIZE.ratio })}
                            className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border py-2.5 text-xs transition-colors ${
                                data.ratio === AUTO_SIZE.ratio
                                    ? 'border-foreground text-foreground'
                                    : 'border-border text-muted-foreground hover:border-muted-foreground'
                            }`}
                        >
                            {t(AUTO_SIZE.labelKey)}
                        </button>
                    </div>
                </>
            )}

            {/* 秒数 */}
            <div className="mt-4 text-xs text-muted-foreground">{t('settings.videoSeconds')}</div>
            <div className="mt-2 grid grid-cols-3 gap-2">
                {SECONDS_OPTIONS.map(n => (
                    <button
                        key={n}
                        type="button"
                        onClick={() => update({ seconds: n })}
                        className={`cursor-pointer rounded-full border py-1.5 text-xs transition-colors ${
                            data.seconds === n
                                ? 'border-foreground text-foreground'
                                : 'border-border text-muted-foreground hover:border-muted-foreground'
                        }`}
                    >
                        {n}s
                    </button>
                ))}
                <input
                    type="number"
                    min={1}
                    max={60}
                    value={data.seconds}
                    onChange={e => {
                        const n = Math.floor(Number(e.target.value));
                        if (Number.isFinite(n)) update({ seconds: Math.min(60, Math.max(1, n)) });
                    }}
                    className={`w-full rounded-full border bg-transparent py-1.5 text-center text-xs text-foreground outline-none transition-colors ${
                        SECONDS_OPTIONS.includes(data.seconds)
                            ? 'border-border'
                            : 'border-foreground'
                    }`}
                />
            </div>
        </>
    );
}
