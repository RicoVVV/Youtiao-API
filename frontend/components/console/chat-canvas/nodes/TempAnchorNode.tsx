"use client";
import { Handle, Position } from '@xyflow/react';
import type { Node } from '@xyflow/react';

export type TempAnchorFlowNode = Node<Record<string, unknown>, 'tempAnchorNode'>;

/** 临时锚点：拖线松手在空白处时固定连线端点（不可见），等用户在「引用该节点生成」菜单选择后替换为真实节点 */
export default function TempAnchorNode() {
    return (
        <div className="pointer-events-none h-px w-px opacity-0">
            <Handle id="in" type="target" position={Position.Left} />
            <Handle id="out" type="source" position={Position.Right} />
        </div>
    );
}
