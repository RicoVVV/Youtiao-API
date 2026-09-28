"use client";
import { useTranslation } from "react-i18next";
import type { AudioNodeData } from '../AudioNode';

/** 声音选项 */
const VOICE_OPTIONS = ['Alloy', 'Ash', 'Ballad', 'Coral', 'Echo', 'Fable', 'Nova', 'Onyx', 'Sage', 'Shimmer', 'Verse', 'Marin', 'Cedar'];

/** 格式选项 */
const FORMAT_OPTIONS = ['MP3', 'WAV', 'Opus', 'AAC', 'FLAC', 'PCM'];

/** 语速选项 */
const SPEED_OPTIONS = [0.75, 1, 1.25, 1.5];

/** 音频设置参数区：声音 / 格式 / 语速 / 声音指令 */
export default function AudioNodeSettings({
    data,
    update,
}: {
    data: AudioNodeData;
    update: (patch: Partial<AudioNodeData>) => void;
}) {
    const { t } = useTranslation("canvas");

    return (
        <>
            {/* 声音 */}
            <div className="mt-3 text-xs text-muted-foreground">{t('settings.voice')}</div>
            <div className="mt-2 grid grid-cols-3 gap-2">
                {VOICE_OPTIONS.map(voice => (
                    <button
                        key={voice}
                        type="button"
                        onClick={() => update({ voice })}
                        className={`cursor-pointer rounded-full border py-1.5 text-xs transition-colors ${
                            data.voice === voice
                                ? 'border-foreground text-foreground'
                                : 'border-border text-muted-foreground hover:border-muted-foreground'
                        }`}
                    >
                        {voice}
                    </button>
                ))}
            </div>

            {/* 格式 */}
            <div className="mt-4 text-xs text-muted-foreground">{t('settings.format')}</div>
            <div className="mt-2 grid grid-cols-3 gap-2">
                {FORMAT_OPTIONS.map(format => (
                    <button
                        key={format}
                        type="button"
                        onClick={() => update({ format })}
                        className={`cursor-pointer rounded-full border py-1.5 text-xs transition-colors ${
                            data.format === format
                                ? 'border-foreground text-foreground'
                                : 'border-border text-muted-foreground hover:border-muted-foreground'
                        }`}
                    >
                        {format}
                    </button>
                ))}
            </div>

            {/* 语速 */}
            <div className="mt-4 text-xs text-muted-foreground">{t('settings.speed')}</div>
            <div className="mt-2 grid grid-cols-4 gap-2">
                {SPEED_OPTIONS.map(n => (
                    <button
                        key={n}
                        type="button"
                        onClick={() => update({ speed: n })}
                        className={`cursor-pointer rounded-full border py-1.5 text-xs transition-colors ${
                            data.speed === n
                                ? 'border-foreground text-foreground'
                                : 'border-border text-muted-foreground hover:border-muted-foreground'
                        }`}
                    >
                        {n}x
                    </button>
                ))}
            </div>
            <input
                type="number"
                min={0.25}
                max={4}
                step={0.25}
                value={data.speed}
                onChange={e => {
                    const n = Number(e.target.value);
                    if (Number.isFinite(n)) update({ speed: Math.min(4, Math.max(0.25, n)) });
                }}
                className={`mt-2 w-full rounded-full border bg-transparent py-1.5 text-center text-xs text-foreground outline-none transition-colors ${
                    SPEED_OPTIONS.includes(data.speed)
                        ? 'border-border'
                        : 'border-foreground'
                }`}
            />

            {/* 声音指令 */}
            <div className="mt-4 text-xs text-muted-foreground">{t('settings.voiceInstructions')}</div>
            <textarea
                value={data.instructions}
                onChange={e => update({ instructions: e.target.value })}
                placeholder={t('settings.voiceInstructionsPlaceholder')}
                rows={3}
                className="mt-2 w-full resize-none rounded-xl border border-border bg-transparent p-3 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
            />
        </>
    );
}
