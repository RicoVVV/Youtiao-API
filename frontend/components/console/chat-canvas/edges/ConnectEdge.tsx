"use client";
import { useRef, useState } from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath, useReactFlow, useStore, useViewport } from '@xyflow/react';
import type { EdgeProps } from '@xyflow/react';
import { Scissors } from 'lucide-react';

/**
 * 自定义连线：贝塞尔路径连接节点左右连接点；
 * 自身选中/关联节点选中/悬停时高亮，悬停停留 300ms 后在指针处显示剪刀按钮（点击断开连线）。
 */
export default function ConnectEdge({ id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, selected, data }: EdgeProps) {
    const { screenToFlowPosition, deleteElements } = useReactFlow();
    const { zoom } = useViewport();
    // 临时连线（拖线落空白、等待选择新节点期间）不显示剪刀
    const hideCut = Boolean((data as { hideCut?: boolean } | undefined)?.hideCut);
    // 悬停状态与指针在边路径上的流坐标（用于定位剪刀按钮）
    const [isHovered, setIsHovered] = useState(false);
    const [pointer, setPointer] = useState<{ x: number; y: number } | null>(null);
    const pointerRaf = useRef(0);

    // 悬停缓冲：停留 300ms 才显示剪刀，扫过/点击选中连线时不弹出
    const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const clearHoverTimer = () => {
        if (hoverTimer.current) {
            clearTimeout(hoverTimer.current);
            hoverTimer.current = null;
        }
    };
    const scheduleShow = () => {
        clearHoverTimer();
        hoverTimer.current = setTimeout(() => setIsHovered(true), 300);
    };
    const hideNow = () => {
        clearHoverTimer();
        cancelAnimationFrame(pointerRaf.current);
        setIsHovered(false);
        setPointer(null);
    };

    // 关联节点被选中时高亮连线
    const connectedSelected = useStore(s => !!s.nodeLookup.get(source)?.selected || !!s.nodeLookup.get(target)?.selected);
    const highlighted = !!selected || connectedSelected || isHovered;

    const [path] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
    // 剪刀默认落边中点；悬停移动时跟随指针（rAF 节流）
    const labelX = pointer?.x ?? (sourceX + targetX) / 2;
    const labelY = pointer?.y ?? (sourceY + targetY) / 2;

    return (
        <>
            <BaseEdge
                id={id}
                path={path}
                markerEnd={markerEnd}
                style={{ stroke: 'var(--muted-foreground)', ...style, ...(highlighted ? { stroke: 'var(--primary)' } : undefined) }}
            />
            {/* 加宽透明热区：捕捉悬停与指针位置（RF 的 interactionWidth 只处理点击命中） */}
            <path
                d={path}
                fill="none"
                stroke="transparent"
                strokeWidth={20}
                style={{ pointerEvents: 'stroke' }}
                onPointerEnter={scheduleShow}
                onPointerLeave={e => {
                    // 按钮渲染后正好盖住鼠标，移入按钮不算离开（否则 enter/leave 闪烁循环）
                    if ((e.relatedTarget as HTMLElement | null)?.closest?.('.edge-cut-btn')) return;
                    hideNow();
                }}
                onPointerMove={e => {
                    const { clientX, clientY } = e;
                    cancelAnimationFrame(pointerRaf.current);
                    pointerRaf.current = requestAnimationFrame(() => setPointer(screenToFlowPosition({ x: clientX, y: clientY })));
                }}
            />
            {isHovered && !hideCut && (
                <EdgeLabelRenderer>
                    <button
                        type="button"
                        aria-label="断开连线"
                        className="edge-cut-btn nodrag nopan absolute flex h-6 w-6 cursor-pointer items-center justify-center rounded-full border border-border bg-popover text-muted-foreground shadow-card transition-colors hover:bg-accent hover:text-foreground"
                        style={{
                            // 除以 zoom 抵消容器的视口缩放，按钮保持固定屏幕尺寸
                            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px) scale(${1 / (zoom || 1)})`,
                            pointerEvents: 'all',
                        }}
                        // 已在显示中，移入直接维持（无需再缓冲）
                        onPointerEnter={() => {
                            clearHoverTimer();
                            setIsHovered(true);
                        }}
                        onPointerLeave={e => {
                            // 移回热区 path 不算离开；移到画布空白处才关闭
                            if ((e.relatedTarget as HTMLElement | null)?.closest?.('.react-flow__edge')) return;
                            hideNow();
                        }}
                        onMouseDown={e => e.stopPropagation()}
                        onClick={e => {
                            e.stopPropagation();
                            void deleteElements({ edges: [{ id }] });
                        }}
                    >
                        <Scissors className="h-3.5 w-3.5" />
                    </button>
                </EdgeLabelRenderer>
            )}
        </>
    );
}
