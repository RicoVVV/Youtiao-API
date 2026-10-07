"use client";
import { NodeResizeControl, useReactFlow, useStore } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { Info, Trash2, Group } from 'lucide-react';
import { create } from 'zustand';
import { useNodeClickExpand } from './shared/useNodeClickExpand';

export interface GroupNodeData extends Record<string, unknown> {
    /** 分组名称 */
    label: string;
}

export type GroupFlowNode = Node<GroupNodeData, 'groupNode'>;

/** 拖拽中的子节点即将加入的分组 id（仅用于高亮组边框，不随画布存档） */
export const useGroupHighlightStore = create<{
    highlightId: string | null;
    setHighlightId: (id: string | null) => void;
}>(set => ({ highlightId: null, setHighlightId: id => set({ highlightId: id }) }));

/** 组框尺寸约束 */
const MIN_WIDTH = 320;
const MIN_HEIGHT = 240;

/** 组框默认尺寸（创建时使用） */
export const GROUP_DEFAULT_WIDTH = 640;
export const GROUP_DEFAULT_HEIGHT = 420;

/** 四角缩放手柄样式 */
const CORNER_STYLE: React.CSSProperties = {
    width: 12,
    height: 12,
    borderRadius: '50%',
    background: 'var(--background)',
    border: '2px solid var(--primary)',
};

const CORNERS = ['top-left', 'top-right', 'bottom-left', 'bottom-right'] as const;

export default function GroupNode({ id, data, selected, dragging }: NodeProps<GroupFlowNode>) {
    const { deleteElements, setNodes, getNode } = useReactFlow();
    const highlighted = useGroupHighlightStore(s => s.highlightId === id);
    // 点击展开态：仅真实点击（非拖拽）时显示操作栏
    const { expanded, onPointerDown, onPointerUp } = useNodeClickExpand(selected, dragging);
    // 右上角统计：组内子节点数量
    const childCount = useStore(s => s.nodes.reduce((count, n) => count + (n.parentId === id ? 1 : 0), 0));

    /** 删除分组：先把组内节点移出（坐标转绝对），再删组框，避免子节点被连带删除 */
    const handleDelete = () => {
        const group = getNode(id);
        if (group) {
            setNodes(nds =>
                nds.map(n =>
                    n.parentId === id
                        ? { ...n, parentId: undefined, position: { x: group.position.x + n.position.x, y: group.position.y + n.position.y } }
                        : n,
                ),
            );
        }
        void deleteElements({ nodes: [{ id }] });
    };

    /** 头部操作：删除有逻辑，信息先只展示 */
    const headerActions = [
        // { key: 'info', label: '信息', icon: <Info className="h-4 w-4" /> },
        { key: 'delete', label: '删除', icon: <Trash2 className="h-4 w-4" />, onClick: handleDelete },
    ];

    return (
        <div className="group relative h-full w-full" onPointerDown={onPointerDown} onPointerUp={onPointerUp}>
            {/* 点击展开时节点上方悬浮操作栏（拖拽不展开） */}
            {expanded && (
                <div className="nodrag absolute -top-14 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-popover px-2 py-1.5 whitespace-nowrap shadow-card">
                    {headerActions.map(action => (
                        <button
                            key={action.key}
                            type="button"
                            onClick={action.onClick}
                            className="flex cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-1 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                        >
                            {action.icon}
                            {action.label}
                        </button>
                    ))}
                </div>
            )}

            {/* 节点标题：默认隐藏，悬停/选中时显示（与其他节点一致） */}
            <div
                className={`absolute -top-6 left-1 text-xs text-muted-foreground transition-opacity ${
                    selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                }`}
            >
                组
            </div>

            {/* 组框主体：拖入节点过半时高亮边框 */}
            <div
                className={`h-full w-full rounded-3xl border-2 border-dashed transition-colors ${
                    highlighted
                        ? 'border-primary bg-primary/5'
                        : selected
                          ? 'border-primary'
                          : 'border-border group-hover:border-primary/60'
                }`}
            >
                {/* 头部：左侧名称，右侧节点计数 */}
                <div className="flex items-center justify-between px-4 py-3">
                    <div className="flex items-center gap-2">
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-muted">
                            <Group className="h-4 w-4 text-muted-foreground" />
                        </span>
                        <span className="text-sm text-foreground">{data.label || '组'}</span>
                    </div>
                    <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">
                        {childCount} 个节点
                    </span>
                </div>
            </div>

            {/* 四角缩放手柄：仅选中时可用 */}
            {selected &&
                CORNERS.map(position => (
                    <NodeResizeControl
                        key={position}
                        position={position}
                        minWidth={MIN_WIDTH}
                        minHeight={MIN_HEIGHT}
                        style={CORNER_STYLE}
                    />
                ))}
        </div>
    );
}
