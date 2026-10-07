import { useCallback } from 'react';
import { useStore } from '@xyflow/react';

/**
 * 直接连入本节点的上游图片节点图片地址（生成时作为多参考图提交）。
 * useStore selector 需返回稳定快照：先按换行拼接字符串，渲染侧再拆分。
 */
export function useUpstreamImageUrls(nodeId: string): string[] {
    const joined = useStore(
        useCallback(
            state =>
                state.edges
                    .filter(e => e.target === nodeId && e.source !== nodeId)
                    .map(e => {
                        const node = state.nodes.find(n => n.id === e.source);
                        const url = node?.type === 'imageNode' ? (node.data as { imageUrl?: unknown }).imageUrl : null;
                        return typeof url === 'string' ? url : '';
                    })
                    .filter(Boolean)
                    .join('\n'),
            [nodeId],
        ),
    );
    return joined ? joined.split('\n') : [];
}
