"use client";
import { NodeResizeControl } from '@xyflow/react';
import type { CSSProperties } from 'react';

/**
 * 四角缩放手柄：透明热区，中心正好压在卡片边框的角点上；
 * 无圆点外观，鼠标滑到角上只显示对应方向的缩放光标，按下即可拖拽。
 */
const CORNERS = ['top-left', 'top-right', 'bottom-left', 'bottom-right'] as const;

/** 各角对应的双向缩放光标 */
const CORNER_CURSOR: Record<(typeof CORNERS)[number], CSSProperties['cursor']> = {
    'top-left': 'nwse-resize',
    'top-right': 'nesw-resize',
    'bottom-left': 'nesw-resize',
    'bottom-right': 'nwse-resize',
};

interface NodeCornerResizerProps {
    /** 悬停/选中时启用 */
    visible: boolean;
    minWidth: number;
    minHeight: number;
}

export default function NodeCornerResizer({ visible, minWidth, minHeight }: NodeCornerResizerProps) {
    if (!visible) return null;
    return (
        <>
            {CORNERS.map(position => (
                <NodeResizeControl
                    key={position}
                    position={position}
                    minWidth={minWidth}
                    minHeight={minHeight}
                    style={{
                        width: 18,
                        height: 18,
                        background: 'transparent',
                        border: 'none',
                        cursor: CORNER_CURSOR[position],
                        // 节点根容器为 pointer-events-none，手柄必须恢复交互
                        pointerEvents: 'auto',
                    }}
                />
            ))}
        </>
    );
}
