"use client";
import { useEffect, useState } from 'react';
import { LoaderCircle, RotateCcw, TriangleAlert } from 'lucide-react';

/** 生成中展示的步骤（按已用时间切换，无法拿到真实进度时的近似反馈） */
const RUNNING_STAGES: { after: number; label: string }[] = [
    { after: 0, label: '正在提交请求…' },
    { after: 2, label: '模型生成中…' },
    { after: 8, label: '生成中，耐心等待…' },
    { after: 30, label: '耗时较长，仍在生成…' },
];

interface NodeGenerateOverlayProps {
    /** 是否正在生成：显示 loading + 进度（步骤与已用时间） */
    isRunning: boolean;
    /** 生成失败信息：非空时显示报错与重试按钮 */
    error?: string;
    /** 点击重试时重新触发生成 */
    onRetry?: () => void;
}

/** 节点卡片上的生成状态浮层：生成中显示 loading + 进度，失败显示报错 + 重试 */
export default function NodeGenerateOverlay({ isRunning, error, onRetry }: NodeGenerateOverlayProps) {
    const [elapsed, setElapsed] = useState(0);

    // 生成开始时计时（0.5s 粒度），结束后复位
    useEffect(() => {
        if (!isRunning) return;
        setElapsed(0);
        const startedAt = Date.now();
        const timer = setInterval(() => setElapsed((Date.now() - startedAt) / 1000), 500);
        return () => clearInterval(timer);
    }, [isRunning]);

    if (!isRunning && !error) return null;

    const stage = RUNNING_STAGES.reduce((acc, s) => (elapsed >= s.after ? s.label : acc), RUNNING_STAGES[0].label);

    return (
        /* 根元素不能加 nodrag：浮层铺满整张卡片，加了会导致节点无法拖拽（仅报错文本区/重试按钮保留 nodrag） */
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 overflow-hidden rounded-2xl bg-background/70 px-6 backdrop-blur-sm">
            {isRunning ? (
                <>
                    <LoaderCircle className="h-8 w-8 animate-spin text-primary" />
                    <div className="text-sm text-foreground">{stage}</div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span className="flex gap-1">
                            {[0, 1, 2].map(i => (
                                <span
                                    key={i}
                                    className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground"
                                    style={{ animationDelay: `${i * 200}ms` }}
                                />
                            ))}
                        </span>
                    </div>
                </>
            ) : (
                <>
                    <TriangleAlert className="h-7 w-7 text-destructive" />
                    <div className="nodrag nowheel max-h-28 w-full overflow-y-auto text-center text-xs leading-5 wrap-break-word whitespace-pre-wrap text-destructive">
                        {error}
                    </div>
                    {onRetry && (
                        <button
                            type="button"
                            onClick={onRetry}
                            className="nodrag flex cursor-pointer items-center gap-1.5 rounded-full bg-primary px-4 py-1.5 text-xs text-primary-foreground transition-colors hover:bg-primary/90"
                        >
                            <RotateCcw className="h-3.5 w-3.5" />
                            重试
                        </button>
                    )}
                </>
            )}
        </div>
    );
}
