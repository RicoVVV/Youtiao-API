"use client";
import { useCallback, useState } from 'react';
import { useReactFlow, useViewport } from '@xyflow/react';
import { useTranslation } from 'react-i18next';
import { Map, Minus, Plus, RotateCcw } from 'lucide-react';
import MiniMap from './MiniMap';

/** 画布默认缩放比例 */
export const DEFAULT_VIEWPORT_ZOOM = 1;

/** 缩放范围（与 ReactFlow minZoom/maxZoom 保持一致） */
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 4;

/** 缩放步进倍率（±按钮） */
const ZOOM_STEP = 1.25;

/** 画布左下角固定工具栏：小地图入口 + 缩放控制（-/进度条/+）+ 重置缩放 */
export default function ViewportBar() {
    const { t } = useTranslation('canvas');
    const { setViewport, getViewport } = useReactFlow();
    const { zoom } = useViewport();
    const [mapOpen, setMapOpen] = useState(false);

    const clampZoom = useCallback((z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z)), []);

    /** 以画布中心为锚点设置缩放 */
    const applyZoom = useCallback(
        (nextZoom: number, duration = 150) => {
            const z = clampZoom(nextZoom);
            const { x, y, zoom: cur } = getViewport();
            // 保持视口中心不动：screenCenter 对应的 flow 点在缩放前后一致
            const w = window.innerWidth;
            const h = window.innerHeight;
            const cx = (w / 2 - x) / cur;
            const cy = (h / 2 - y) / cur;
            void setViewport(
                { x: w / 2 - cx * z, y: h / 2 - cy * z, zoom: z },
                { duration },
            );
        },
        [clampZoom, getViewport, setViewport],
    );

    const handleZoomIn = useCallback(() => applyZoom(getViewport().zoom * ZOOM_STEP), [applyZoom, getViewport]);
    const handleZoomOut = useCallback(() => applyZoom(getViewport().zoom / ZOOM_STEP), [applyZoom, getViewport]);

    const handleSliderChange = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            const t = Number(e.target.value) / 100; // 0..1
            // 对数插值：zoom = MIN * (MAX/MIN)^t
            const z = MIN_ZOOM * Math.pow(MAX_ZOOM / MIN_ZOOM, t);
            applyZoom(z, 0);
        },
        [applyZoom],
    );

    const handleReset = useCallback(() => {
        applyZoom(DEFAULT_VIEWPORT_ZOOM, 250);
    }, [applyZoom]);

    // 当前 zoom 映射到滑块 0..100（对数）
    const sliderValue = Math.round(
        (Math.log(zoom / MIN_ZOOM) / Math.log(MAX_ZOOM / MIN_ZOOM)) * 100,
    );

    const btnClass =
        'flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground';

    return (
        <div className="flex flex-col items-start gap-3">
            {mapOpen && <MiniMap />}
            <div className="flex items-center gap-1 rounded-full border border-border bg-card px-2 py-1.5 shadow-card">
                <button
                    type="button"
                    className={`${btnClass} ${mapOpen ? 'bg-accent text-accent-foreground' : ''}`}
                    onClick={() => setMapOpen(open => !open)}
                    aria-label={t('viewportBar.minimap')}
                    title={t('viewportBar.minimap')}
                >
                    <Map className="h-4 w-4" />
                </button>
                <button
                    type="button"
                    className={btnClass}
                    onClick={handleZoomOut}
                    aria-label={t('viewportBar.zoomOut')}
                    title={t('viewportBar.zoomOut')}
                >
                    <Minus className="h-4 w-4" />
                </button>
                <input
                    type="range"
                    className="h-1 w-24 cursor-pointer accent-primary"
                    min={0}
                    max={100}
                    value={sliderValue}
                    onChange={handleSliderChange}
                    aria-label={t('viewportBar.zoomLevel')}
                />
                <button
                    type="button"
                    className={btnClass}
                    onClick={handleZoomIn}
                    aria-label={t('viewportBar.zoomIn')}
                    title={t('viewportBar.zoomIn')}
                >
                    <Plus className="h-4 w-4" />
                </button>
                <div
                    className="min-w-11 text-center text-sm text-muted-foreground tabular-nums"
                    title={t('viewportBar.currentZoom')}
                >
                    {Math.round(zoom * 100)}%
                </div>
                <button
                    type="button"
                    className={btnClass}
                    onClick={handleReset}
                    aria-label={t('viewportBar.resetZoom')}
                    title={t('viewportBar.resetZoom')}
                >
                    <RotateCcw className="h-4 w-4" />
                </button>
            </div>
        </div>
    );
}
