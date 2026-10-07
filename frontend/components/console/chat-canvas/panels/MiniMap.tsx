"use client";
import { useCallback, useRef } from 'react';
import { useReactFlow, useStore } from '@xyflow/react';
import type { InternalNode, ReactFlowState } from '@xyflow/react';

/** 小地图面板尺寸 */
const MINIMAP_WIDTH = 220;
const MINIMAP_HEIGHT = 150;

/** 小地图内边距（flow 坐标，避免节点贴边） */
const MINIMAP_PADDING = 40;

/** 最小视野覆盖的主画布屏数（保证视口框不会铺满小地图，且不随 zoom 变化） */
const MIN_VIEW_SCREENS = 2;

interface MiniNode {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
}

/** 计算节点 bounds（含 padding 与最小视野） */
function computeNodesBounds(nodes: MiniNode[]) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const n of nodes) {
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        maxX = Math.max(maxX, n.x + n.width);
        maxY = Math.max(maxY, n.y + n.height);
    }
    const hasNodes = nodes.length > 0;
    const x = (hasNodes ? minX : 0) - MINIMAP_PADDING;
    const y = (hasNodes ? minY : 0) - MINIMAP_PADDING;
    const w = Math.max((hasNodes ? maxX - minX : 0) + MINIMAP_PADDING * 2, 1);
    const h = Math.max((hasNodes ? maxY - minY : 0) + MINIMAP_PADDING * 2, 1);
    return { x, y, w, h };
}

/** 把视野扩展为与面板相同的宽高比（preserveAspectRatio="xMidYMid meet"），确保 viewBox 完整可见 */
function fitAspectRatio(vb: { x: number; y: number; w: number; h: number }, panelW: number, panelH: number) {
    const target = panelW / panelH;
    const current = vb.w / vb.h;
    if (current < target) {
        // 太窄：扩展宽度
        const newW = vb.h * target;
        vb.x -= (newW - vb.w) / 2;
        vb.w = newW;
    } else {
        // 太宽：扩展高度
        const newH = vb.w / target;
        vb.y -= (newH - vb.h) / 2;
        vb.h = newH;
    }
    return vb;
}

/**
 * 自定义小地图：画布的微缩全局视图。
 * - 视野始终同时包住全部节点与当前视口框（双向同步，节点/视口框不出四边）
 * - 点击快速定位，拖拽实时平移主画布
 * - 内置 MiniMap 会把随 zoom 变化的 viewBB 并入 viewBox，无法满足"缩放画布时小地图不跟随缩放"
 */
export default function MiniMap() {
    const { setViewport, getViewport } = useReactFlow();
    const containerRef = useRef<HTMLDivElement>(null);

    // 只订阅渲染所需的最小状态：节点位置/尺寸（数值相等即跳过，拖拽时浅拷贝不变不触发重渲）、主画布视口
    const nodes = useStore(
        useCallback(
            (s: ReactFlowState) =>
                Array.from(s.nodeLookup.values())
                    .filter((n: InternalNode) => !n.hidden)
                    .map((n: InternalNode) => {
                        const { x, y } = n.internals.positionAbsolute;
                        return {
                            id: n.id,
                            x,
                            y,
                            width: n.measured?.width ?? n.width ?? 0,
                            height: n.measured?.height ?? n.height ?? 0,
                        };
                    }),
            [],
        ),
        (a, b) =>
            a.length === b.length &&
            a.every((n, i) => {
                const m = b[i];
                return (
                    n.id === m.id &&
                    n.x === m.x &&
                    n.y === m.y &&
                    n.width === m.width &&
                    n.height === m.height
                );
            }),
    );
    // transform 引用相等（immer 结构共享），平移/缩放时才会更新
    const [vpX, vpY, vpZoom] = useStore(useCallback((s: ReactFlowState) => s.transform, []));
    const containerSize = useStore(
        useCallback((s: ReactFlowState) => ({ w: s.width, h: s.height }), []),
        (a, b) => a.w === b.w && a.h === b.h,
    );

    // 拖拽状态：光标在视口框内的抓取偏移（flow 坐标）+ 视口框尺寸 + 是否已发生移动
    const dragState = useRef<{
        startX: number;
        startY: number;
        grabDX: number;
        grabDY: number;
        vw: number;
        vh: number;
        moved: boolean;
    } | null>(null);

    // ---------- 视野计算（节点 bounds ∪ 视口框，扩展到最小视野，再扩展为面板宽高比） ----------
    const nodesBounds = computeNodesBounds(nodes);
    const nodesBoundsRef = useRef(nodesBounds);
    nodesBoundsRef.current = nodesBounds;
    const containerSizeRef = useRef(containerSize);
    containerSizeRef.current = containerSize;

    /** 给定候选视口框位置，计算对应的小地图视野 */
    const computeVbFor = useCallback(
        (view: { x: number; y: number; width: number; height: number }) => {
            const nb = nodesBoundsRef.current;
            const cs = containerSizeRef.current;
            // 最小视野：至少覆盖 N 屏主画布（以 zoom=1 为基准），保证全局概览感
            const minW = cs.w * MIN_VIEW_SCREENS;
            const minH = cs.h * MIN_VIEW_SCREENS;
            let x = Math.min(nb.x, view.x);
            let y = Math.min(nb.y, view.y);
            let w = Math.max(nb.x + nb.w, view.x + view.width) - x;
            let h = Math.max(nb.y + nb.h, view.y + view.height) - y;
            if (w < minW) {
                x -= (minW - w) / 2;
                w = minW;
            }
            if (h < minH) {
                y -= (minH - h) / 2;
                h = minH;
            }
            return fitAspectRatio({ x, y, w, h }, MINIMAP_WIDTH, MINIMAP_HEIGHT);
        },
        [],
    );

    const viewBB = {
        x: -vpX / vpZoom,
        y: -vpY / vpZoom,
        width: containerSize.w / vpZoom,
        height: containerSize.h / vpZoom,
    };

    const vb = computeVbFor(viewBB);

    /** 面板内 client 坐标 → flow 坐标（viewBox 宽高比 = 面板宽高比，无需额外偏移） */
    const clientToFlow = useCallback(
        (clientX: number, clientY: number) => {
            const el = containerRef.current;
            if (!el) return { flowX: 0, flowY: 0 };
            const rect = el.getBoundingClientRect();
            const scale = vb.w / rect.width; // flow / pixel
            return {
                flowX: vb.x + (clientX - rect.left) * scale,
                flowY: vb.y + (clientY - rect.top) * scale,
            };
        },
        [vb.x, vb.y, vb.w],
    );

    const handlePointerDown = useCallback(
        (e: React.PointerEvent<HTMLDivElement>) => {
            if (e.button !== 0) return;
            e.currentTarget.setPointerCapture(e.pointerId);
            // 以光标相对视口框左上角的偏移作为抓取点，拖动时视口框跟随鼠标
            const { flowX, flowY } = clientToFlow(e.clientX, e.clientY);
            const { x, y, zoom } = getViewport();
            dragState.current = {
                startX: e.clientX,
                startY: e.clientY,
                grabDX: flowX - (-x / zoom),
                grabDY: flowY - (-y / zoom),
                vw: containerSize.w / zoom,
                vh: containerSize.h / zoom,
                moved: false,
            };
        },
        [clientToFlow, getViewport, containerSize],
    );

    const handlePointerMove = useCallback(
        (e: React.PointerEvent<HTMLDivElement>) => {
            const drag = dragState.current;
            if (!drag) return;
            if (!drag.moved && Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 4) return;
            drag.moved = true;

            const el = containerRef.current;
            if (!el) return;
            const rect = el.getBoundingClientRect();
            const { zoom } = getViewport();

            // 迭代求不动点：新视口框位置决定新视野，新视野又决定当前鼠标的 flow 坐标
            // （节点静止、视口框匀速移动，视野边界随拖拽单调变化，2 轮即可收敛）
            let viewX = 0; // 占位，首轮立即被覆盖
            let viewY = 0;
            let lastVb = vb;
            for (let i = 0; i < 2; i++) {
                const scale = lastVb.w / rect.width; // flow / pixel
                const flowX = lastVb.x + (e.clientX - rect.left) * scale;
                const flowY = lastVb.y + (e.clientY - rect.top) * scale;
                viewX = flowX - drag.grabDX;
                viewY = flowY - drag.grabDY;
                lastVb = computeVbFor({ x: viewX, y: viewY, width: drag.vw, height: drag.vh });
            }

            void setViewport({ x: -viewX * zoom, y: -viewY * zoom, zoom });
        },
        [getViewport, setViewport, vb, computeVbFor],
    );

    const handlePointerUp = useCallback(
        (e: React.PointerEvent<HTMLDivElement>) => {
            const drag = dragState.current;
            dragState.current = null;
            e.currentTarget.releasePointerCapture(e.pointerId);

            if (drag?.moved) {
                return;
            }

            // 未拖动 = 点击：快速定位到点击点（不自动关闭面板，关闭仅通过地图图标）
            if (drag) {
                const { flowX, flowY } = clientToFlow(e.clientX, e.clientY);
                const { zoom } = getViewport();
                void setViewport(
                    {
                        x: containerSize.w / 2 - flowX * zoom,
                        y: containerSize.h / 2 - flowY * zoom,
                        zoom,
                    },
                    { duration: 300 },
                );
            }
        },
        [clientToFlow, getViewport, setViewport, containerSize],
    );

    return (
        <div
            ref={containerRef}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            className="relative h-37.5 w-55 cursor-grab touch-none overflow-hidden rounded-[10px] border border-border bg-card shadow-card select-none"
        >
            <svg
                width={MINIMAP_WIDTH}
                height={MINIMAP_HEIGHT}
                viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
                preserveAspectRatio="none"
                className="pointer-events-none block"
            >
                {nodes.map(n => (
                    <rect
                        key={n.id}
                        x={n.x}
                        y={n.y}
                        width={n.width}
                        height={n.height}
                        rx={Math.max(vb.w, vb.h) * 0.008}
                        strokeWidth={Math.max(vb.w, vb.h) * 0.004}
                        className="fill-[rgba(28,33,40,0.08)] stroke-[rgba(28,33,40,0.15)] dark:fill-[rgba(255,255,255,0.10)] dark:stroke-[rgba(255,255,255,0.20)]"
                    />
                ))}
                <rect
                    x={viewBB.x}
                    y={viewBB.y}
                    width={viewBB.width}
                    height={viewBB.height}
                    strokeWidth={Math.max(vb.w, vb.h) * 0.006}
                    className="fill-transparent stroke-primary/70"
                />
            </svg>
        </div>
    );
}
