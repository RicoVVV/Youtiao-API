"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
    ReactFlowProvider,
    ReactFlow,
    Background,
    BackgroundVariant,
    Panel,
    useReactFlow,
    useNodesState,
    useEdgesState,
    addEdge,
    ConnectionMode
} from "@xyflow/react";
import type { Connection, Edge, FinalConnectionState, OnNodeDrag } from "@xyflow/react";
import '@xyflow/react/dist/style.css';

import ViewportBar from './panels/ViewportBar';
import AddNodeMenu from './panels/AddNodeMenu';
import type { AddNodeMenuType } from './panels/AddNodeMenu';
import CanvasToolbar from './panels/CanvasToolbar';
import type { GridStyle } from './panels/CanvasToolbar';
import CanvasHistoryPanel from './panels/CanvasHistoryPanel';
import TextNode from './nodes/TextNode';
import type { TextFlowNode } from './nodes/TextNode';
import ImageNode from './nodes/ImageNode';
import type { ImageFlowNode } from './nodes/ImageNode';
import VideoNode from './nodes/VideoNode';
import type { VideoFlowNode } from './nodes/VideoNode';
import AudioNode from './nodes/AudioNode';
import type { AudioFlowNode } from './nodes/AudioNode';
import ConnectEdge from './edges/ConnectEdge';
import TempAnchorNode from './nodes/TempAnchorNode';
import type { TempAnchorFlowNode } from './nodes/TempAnchorNode';
import GroupNode, { GROUP_DEFAULT_WIDTH, GROUP_DEFAULT_HEIGHT, useGroupHighlightStore } from './nodes/GroupNode';
import type { GroupFlowNode } from './nodes/GroupNode';
import GenConfigNode, { GEN_CONFIG_DEFAULTS } from './nodes/GenConfigNode';
import type { GenConfigFlowNode } from './nodes/GenConfigNode';
import { useCanvasHistoryStore } from '@/stores/use-canvas-history-store';
import { useTranslation } from "react-i18next";
import { getModels } from '@/lib/models';
import { getApiKeys, type ApiKeyOption } from '@/lib/api-keys';
import type { ModelInfo } from '@/lib/types';
import { CanvasApiKeysContext, CanvasModelsContext } from './models-context';

const nodeTypes = { textNode: TextNode, imageNode: ImageNode, videoNode: VideoNode, audioNode: AudioNode, tempAnchorNode: TempAnchorNode, groupNode: GroupNode, genConfigNode: GenConfigNode };
const edgeTypes = { connectEdge: ConnectEdge };

/** 各节点类型的默认尺寸（卡片区；节点支持四角缩放，内容 w/h-full 依赖节点 style 宽高） */
export const NODE_DEFAULT_SIZE: Record<string, { width: number; height: number }> = {
    textNode: { width: 360, height: 208 },
    imageNode: { width: 360, height: 240 },
    videoNode: { width: 360, height: 240 },
    audioNode: { width: 360, height: 240 },
    genConfigNode: { width: 480, height: 260 },
};

/** 节点无显式尺寸时按类型补默认尺寸（兼容旧存档） */
export function withNodeSize<T extends { type?: string; style?: CSSProperties }>(node: T): T {
    if (node.style?.width) return node;
    const size = NODE_DEFAULT_SIZE[node.type ?? ''];
    if (!size) return node;
    // 缺省高度的类型（如 genConfigNode）清掉旧存档固定高度，保持内容自适应
    const { height, ...sizeRest } = size;
    return { ...node, style: { ...node.style, ...sizeRest, height } };
}

type CanvasNode = TextFlowNode | ImageFlowNode | VideoFlowNode | AudioFlowNode | TempAnchorFlowNode | GroupFlowNode | GenConfigFlowNode;

/** 撤销/重做快照（state 均为不可变引用，无需深拷贝） */
type CanvasSnapshot = { nodes: CanvasNode[]; edges: Edge[] };

/** 快照语义签名：忽略选中态/尺寸测量等 UI 态，仅结构/位置/数据变化才计入历史 */
const snapshotSig = (snap: CanvasSnapshot) => JSON.stringify({
    n: snap.nodes.map(n => [n.id, n.type, n.position.x, n.position.y, n.parentId ?? null, n.data, n.style ?? null]),
    e: snap.edges.map(e => [e.id, e.source, e.target, e.sourceHandle ?? null, e.targetHandle ?? null, e.type ?? null, e.data ?? null, e.style ?? null]),
});

/** 历史栈上限 / 连续变化合并窗口（拖拽、连续输入合并为一步） */
const HISTORY_LIMIT = 100;
const HISTORY_MERGE_MS = 300;

export function FlowCanvas() {
    const wrapperRef = useRef<HTMLDivElement>(null);
    const { screenToFlowPosition, getInternalNode } = useReactFlow();
    const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
    const nodeIdRef = useRef(0);
    // 双击空白处弹出的「添加节点」菜单位置（相对画布容器 + flow 坐标）
    const [menuPos, setMenuPos] = useState<{ x: number; y: number; flowX: number; flowY: number } | null>(null);
    // 画布网格样式（由操作栏「画布外观」控制）
    const [gridStyle, setGridStyle] = useState<GridStyle>('dots');
    // 历史会话浮层开关（由左上角展开/收起按钮控制）
    const [historyOpen, setHistoryOpen] = useState(false);

    // 模型广场列表：画布根加载一次，通过 Context 下发给各节点生成区
    const [models, setModels] = useState<ModelInfo[]>([]);
    // 用户 API 密钥列表：同样根加载一次下发（密钥下拉 + 生成请求鉴权）
    const [apiKeys, setApiKeys] = useState<ApiKeyOption[]>([]);
    useEffect(() => {
        let cancelled = false;
        getModels().then(list => {
            if (!cancelled) setModels(list);
        });
        getApiKeys().then(list => {
            if (!cancelled) setApiKeys(list);
        });
        return () => {
            cancelled = true;
        };
    }, []);

    // ---- 会话历史（IndexedDB）----
    const historyStore = useCanvasHistoryStore();
    const { t } = useTranslation("canvas");
    const loadedSessionRef = useRef<string | null>(null);

    // ---- 撤销/重做（快照式历史栈）----
    const undoRef = useRef<{ past: CanvasSnapshot[]; future: CanvasSnapshot[] }>({ past: [], future: [] });
    // 当前语义快照与签名（非语义变化只同步引用，不入栈）
    const currentSnapRef = useRef<CanvasSnapshot>({ nodes: [], edges: [] });
    const currentSigRef = useRef('');
    const lastRecordAtRef = useRef(0);
    // 会话加载置位：state 与加载内容对齐前不记录历史
    const sessionResetRef = useRef(false);
    const [{ canUndo, canRedo }, setUndoState] = useState({ canUndo: false, canRedo: false });
    /** 历史栈长度变化时同步工具栏禁用态（值未变时跳过重渲染） */
    const syncUndoState = () => setUndoState(prev => {
        const next = { canUndo: undoRef.current.past.length > 0, canRedo: undoRef.current.future.length > 0 };
        return prev.canUndo === next.canUndo && prev.canRedo === next.canRedo ? prev : next;
    });

    // hydrate 完成 / 切换会话时加载对应画布内容
    useEffect(() => {
        if (!historyStore.hydrated) return;
        const id = historyStore.currentId;
        if (loadedSessionRef.current === id) return;
        loadedSessionRef.current = id;
        const canvas = id ? historyStore.canvases[id] : null;
        const nextSnap: CanvasSnapshot = {
            nodes: ((canvas?.nodes ?? []) as CanvasNode[]).map(withNodeSize),
            edges: canvas?.edges ?? [],
        };
        setNodes(nextSnap.nodes);
        setEdges(nextSnap.edges);
        // 节点 id 计数对齐，避免新节点 id 与恢复的节点冲突
        nodeIdRef.current = (canvas?.nodes ?? []).reduce((max, n) => Math.max(max, Number(n.id.split('-').pop()) || 0), 0);
        // 切换会话：清空撤销历史，基线对齐到加载内容（加载本身不可撤销）
        undoRef.current = { past: [], future: [] };
        lastRecordAtRef.current = 0;
        currentSnapRef.current = nextSnap;
        currentSigRef.current = snapshotSig(nextSnap);
        sessionResetRef.current = true;
        setUndoState({ canUndo: false, canRedo: false });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [historyStore.hydrated, historyStore.currentId]);
    // 节点/连线变化自动保存当前会话（debounce）
    useEffect(() => {
        if (!historyStore.hydrated) return;
        if (loadedSessionRef.current !== historyStore.currentId) return;
        const timer = setTimeout(() => useCanvasHistoryStore.getState().saveCurrent(nodes, edges, t("history.defaultTitle", { index: 1 })), 500);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [nodes, edges, historyStore.hydrated, historyStore.currentId]);

    // 节点/连线变化时记录撤销历史：仅语义变化入栈，300ms 内连续变化合并为一步
    useEffect(() => {
        const snap: CanvasSnapshot = { nodes, edges };
        const sig = snapshotSig(snap);
        // 会话刚切换/加载：直到 state 与加载内容对齐前不记录
        if (sessionResetRef.current) {
            if (sig === currentSigRef.current) sessionResetRef.current = false;
            return;
        }
        if (sig === currentSigRef.current) {
            // 仅选中/测量等非语义变化：同步引用但不入栈
            currentSnapRef.current = snap;
            return;
        }
        const now = Date.now();
        // 距上次入栈超过合并窗口才推入新历史（拖拽/连续输入算一步）
        if (currentSigRef.current !== '' && now - lastRecordAtRef.current > HISTORY_MERGE_MS) {
            undoRef.current.past.push(currentSnapRef.current);
            if (undoRef.current.past.length > HISTORY_LIMIT) undoRef.current.past.shift();
        }
        undoRef.current.future = [];
        lastRecordAtRef.current = now;
        currentSigRef.current = sig;
        currentSnapRef.current = snap;
        syncUndoState();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [nodes, edges]);

    /** 撤销：回退到上一步快照 */
    const undo = useCallback(() => {
        const h = undoRef.current;
        if (!h.past.length) return;
        const snap = h.past.pop()!;
        h.future.push(currentSnapRef.current);
        lastRecordAtRef.current = 0;
        currentSigRef.current = snapshotSig(snap);
        currentSnapRef.current = snap;
        setNodes(snap.nodes);
        setEdges(snap.edges);
        setUndoState({ canUndo: h.past.length > 0, canRedo: true });
    }, [setNodes, setEdges]);

    /** 重做：恢复刚撤销的一步 */
    const redo = useCallback(() => {
        const h = undoRef.current;
        if (!h.future.length) return;
        const snap = h.future.pop()!;
        h.past.push(currentSnapRef.current);
        lastRecordAtRef.current = 0;
        currentSigRef.current = snapshotSig(snap);
        currentSnapRef.current = snap;
        setNodes(snap.nodes);
        setEdges(snap.edges);
        setUndoState({ canUndo: true, canRedo: h.future.length > 0 });
    }, [setNodes, setEdges]);

    // 快捷键：Ctrl/Cmd+Z 撤销，Ctrl/Cmd+Shift+Z 重做（输入框内不拦截）
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'z') return;
            const target = e.target as HTMLElement | null;
            if (target?.closest('input, textarea, [contenteditable="true"]')) return;
            e.preventDefault();
            if (e.shiftKey) redo(); else undo();
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [undo, redo]);

    // 拖线落空白处弹出的「引用该节点生成」菜单
    const [connectMenu, setConnectMenu] = useState<{
        x: number;
        y: number;
        flowPos: { x: number; y: number };
        fromNodeId: string;
        /** 发起侧手柄类型：target 表示从节点左侧拖出，新节点应作为来源 */
        fromHandleType: 'source' | 'target';
        anchorId: string;
    } | null>(null);

    /** 落点附近命中检测：包围盒外扩 40px 内取最近节点（参考 CanvasFlow，实现"滑到节点即可连线"） */
    const findHitNode = (flowPos: { x: number; y: number }, excludeId: string): CanvasNode | null => {
        const HIT_PADDING = 40;
        let hit: CanvasNode | null = null;
        let hitDist = Infinity;
        for (const n of nodes) {
            if (n.id === excludeId || n.type === 'tempAnchorNode' || n.type === 'groupNode') continue;
            const w = n.measured?.width ?? 0;
            const h = n.measured?.height ?? 0;
            if (!w || !h) continue;
            const dx = Math.max(n.position.x - flowPos.x, 0, flowPos.x - (n.position.x + w));
            const dy = Math.max(n.position.y - flowPos.y, 0, flowPos.y - (n.position.y + h));
            const dist = Math.hypot(dx, dy);
            if (dist <= HIT_PADDING && dist < hitDist) {
                hit = n;
                hitDist = dist;
            }
        }
        return hit;
    };

    /** 方向规范化：从左侧输入点（in）发起时交换方向，保证边始终 source(out) → target(in) */
    const normalizeConn = (conn: Connection): Connection =>
        conn.sourceHandle === 'in'
            ? { source: conn.target, sourceHandle: conn.targetHandle, target: conn.source, targetHandle: conn.sourceHandle }
            : conn;

    /** 清理临时锚点节点与临时连线 */
    const clearTempAnchor = (anchorId: string) => {
        setNodes(nds => nds.filter(n => n.id !== anchorId));
        setEdges(eds => eds.filter(e => e.id !== `temp-edge-${anchorId}`));
    };

    /** 创建文本节点：不传位置时放到画布中心附近 */
    const addTextNode = (flowPos?: { x: number; y: number }) => {
        let position = flowPos;
        if (!position) {
            const rect = wrapperRef.current?.getBoundingClientRect();
            position = screenToFlowPosition({
                x: (rect?.left ?? 0) + (rect?.width ?? window.innerWidth) / 2 - 320,
                y: (rect?.top ?? 0) + (rect?.height ?? window.innerHeight) / 2 - 120,
            });
        }
        const parentGroup = findGroupAtPos(position.x, position.y);
        const relPos = parentGroup
            ? { x: position.x - parentGroup.position.x, y: position.y - parentGroup.position.y }
            : position;

        const id = `text-${++nodeIdRef.current}`;
        setNodes(nds => [
            ...nds,
            {
                id,
                type: 'textNode',
                parentId: parentGroup?.id,
                position: relPos,
                style: { ...NODE_DEFAULT_SIZE.textNode },
                data: { text: '', prompt: '', model: '', apiKeyId: '', reasoning: '自动', count: 1, fontSize: 14 },
            },
        ]);
        return id;
    };

    /** 创建图片节点：不传位置时放到画布中心附近；mediaUrl 为上传的本地图片 */
    const addImageNode = (flowPos?: { x: number; y: number }, mediaUrl?: string) => {
        let position = flowPos;
        if (!position) {
            const rect = wrapperRef.current?.getBoundingClientRect();
            position = screenToFlowPosition({
                x: (rect?.left ?? 0) + (rect?.width ?? window.innerWidth) / 2 - 320,
                y: (rect?.top ?? 0) + (rect?.height ?? window.innerHeight) / 2 - 120,
            });
        }
        const parentGroup = findGroupAtPos(position.x, position.y);
        const relPos = parentGroup
            ? { x: position.x - parentGroup.position.x, y: position.y - parentGroup.position.y }
            : position;

        const id = `image-${++nodeIdRef.current}`;
        setNodes(nds => [
            ...nds,
            {
                id,
                type: 'imageNode',
                parentId: parentGroup?.id,
                position: relPos,
                style: { ...NODE_DEFAULT_SIZE.imageNode },
                data: { imageUrl: mediaUrl ?? '', prompt: '', model: '', apiKeyId: '', ratio: '1:1', width: 1024, height: 1024, align16: true, transparent: false, count: 1 },
            },
        ]);
        return id;
    };

    /** 创建视频节点：不传位置时放到画布中心附近；mediaUrl 为上传的本地视频 */
    const addVideoNode = (flowPos?: { x: number; y: number }, mediaUrl?: string) => {
        let position = flowPos;
        if (!position) {
            const rect = wrapperRef.current?.getBoundingClientRect();
            position = screenToFlowPosition({
                x: (rect?.left ?? 0) + (rect?.width ?? window.innerWidth) / 2 - 320,
                y: (rect?.top ?? 0) + (rect?.height ?? window.innerHeight) / 2 - 120,
            });
        }
        const parentGroup = findGroupAtPos(position.x, position.y);
        const relPos = parentGroup
            ? { x: position.x - parentGroup.position.x, y: position.y - parentGroup.position.y }
            : position;

        const id = `video-${++nodeIdRef.current}`;
        setNodes(nds => [
            ...nds,
            {
                id,
                type: 'videoNode',
                parentId: parentGroup?.id,
                position: relPos,
                style: { ...NODE_DEFAULT_SIZE.videoNode },
                data: { videoUrl: mediaUrl ?? '', prompt: '', model: '', apiKeyId: '', ratio: '横屏', width: 1280, height: 720, seconds: 6 },
            },
        ]);
        return id;
    };

    /** 创建音频节点：不传位置时放到画布中心附近；mediaUrl 为上传的本地音频 */
    const addAudioNode = (flowPos?: { x: number; y: number }, mediaUrl?: string) => {
        let position = flowPos;
        if (!position) {
            const rect = wrapperRef.current?.getBoundingClientRect();
            position = screenToFlowPosition({
                x: (rect?.left ?? 0) + (rect?.width ?? window.innerWidth) / 2 - 320,
                y: (rect?.top ?? 0) + (rect?.height ?? window.innerHeight) / 2 - 120,
            });
        }
        const parentGroup = findGroupAtPos(position.x, position.y);
        const relPos = parentGroup
            ? { x: position.x - parentGroup.position.x, y: position.y - parentGroup.position.y }
            : position;

        const id = `audio-${++nodeIdRef.current}`;
        setNodes(nds => [
            ...nds,
            {
                id,
                type: 'audioNode',
                parentId: parentGroup?.id,
                position: relPos,
                style: { ...NODE_DEFAULT_SIZE.audioNode },
                data: { audioUrl: mediaUrl ?? '', prompt: '', model: '', apiKeyId: '', voice: 'Alloy', format: 'MP3', speed: 1, instructions: '' },
            },
        ]);
        return id;
    };

    /** 创建生成配置节点：不传位置时放到画布中心附近 */
    const addGenConfigNode = (flowPos?: { x: number; y: number }) => {
        let position = flowPos;
        if (!position) {
            const rect = wrapperRef.current?.getBoundingClientRect();
            position = screenToFlowPosition({
                x: (rect?.left ?? 0) + (rect?.width ?? window.innerWidth) / 2 - 240,
                y: (rect?.top ?? 0) + (rect?.height ?? window.innerHeight) / 2 - 140,
            });
        }
        const parentGroup = findGroupAtPos(position.x, position.y);
        const relPos = parentGroup
            ? { x: position.x - parentGroup.position.x, y: position.y - parentGroup.position.y }
            : position;

        const id = `genConfig-${++nodeIdRef.current}`;
        setNodes(nds => [
            ...nds,
            {
                id,
                type: 'genConfigNode',
                parentId: parentGroup?.id,
                position: relPos,
                style: { ...NODE_DEFAULT_SIZE.genConfigNode },
                data: structuredClone(GEN_CONFIG_DEFAULTS),
            } as CanvasNode,
        ]);
        return id;
    };

    /** 创建分组框节点：不传位置时放到画布中心附近（排在数组最前，保证父节点先于子节点渲染） */
    const addGroupNode = (flowPos?: { x: number; y: number }) => {
        let position = flowPos;
        if (!position) {
            const rect = wrapperRef.current?.getBoundingClientRect();
            position = screenToFlowPosition({
                x: (rect?.left ?? 0) + (rect?.width ?? window.innerWidth) / 2 - GROUP_DEFAULT_WIDTH / 2,
                y: (rect?.top ?? 0) + (rect?.height ?? window.innerHeight) / 2 - GROUP_DEFAULT_HEIGHT / 2,
            });
        }
        const id = `group-${++nodeIdRef.current}`;
        setNodes(nds => [
            {
                id,
                type: 'groupNode',
                position,
                style: { width: GROUP_DEFAULT_WIDTH, height: GROUP_DEFAULT_HEIGHT },
                data: { label: '组' },
            } as CanvasNode,
            ...nds,
        ]);
        return id;
    };

    // 拖拽中的子节点即将加入的分组（高亮组边框）
    const setGroupHighlight = useGroupHighlightStore(s => s.setHighlightId);

    /** 节点绝对坐标矩形（含父级偏移，拖拽中实时值） */
    const getNodeAbsRect = (node: CanvasNode) => {
        const abs = getInternalNode(node.id)?.internals.positionAbsolute ?? node.position;
        return { x: abs.x, y: abs.y, w: node.measured?.width ?? 0, h: node.measured?.height ?? 0 };
    };

    /** 组框矩形（分组无父级，position 即绝对坐标） */
    const getGroupRect = (group: CanvasNode) => ({
        x: group.position.x,
        y: group.position.y,
        w: group.measured?.width ?? (group.style?.width as number) ?? 0,
        h: group.measured?.height ?? (group.style?.height as number) ?? 0,
    });

    /** 入组判定：子节点有一半宽或一半高以上区域进入组框（excludeGroupId 用于脱离原组时不重复命中原组） */
    const findJoinGroup = (rect: { x: number; y: number; w: number; h: number }, excludeId: string, excludeGroupId?: string): CanvasNode | null => {
        for (const g of nodes) {
            if (g.type !== 'groupNode' || g.id === excludeId || g.id === excludeGroupId) continue;
            const gr = getGroupRect(g);
            const overlapX = Math.max(0, Math.min(rect.x + rect.w, gr.x + gr.w) - Math.max(rect.x, gr.x));
            const overlapY = Math.max(0, Math.min(rect.y + rect.h, gr.y + gr.h) - Math.max(rect.y, gr.y));
            if (overlapX > 0 && overlapY > 0 && (overlapX >= rect.w / 2 || overlapY >= rect.h / 2)) return g;
        }
        return null;
    };

    /** 节点中心点是否仍在组框内（在组内移动不高亮、不脱离；中心拖出组框即脱离） */
    const isCenterInGroup = (rect: { x: number; y: number; w: number; h: number }, group: CanvasNode): boolean => {
        const gr = getGroupRect(group);
        const cx = rect.x + rect.w / 2;
        const cy = rect.y + rect.h / 2;
        return cx >= gr.x && cx <= gr.x + gr.w && cy >= gr.y && cy <= gr.y + gr.h;
    };

    /** 检测某个 flow 坐标点是否落在某个组框内（用于创建节点时自动归属分组） */
    const findGroupAtPos = (x: number, y: number): CanvasNode | null => {
        for (const g of nodes) {
            if (g.type !== 'groupNode') continue;
            const gr = getGroupRect(g);
            if (x >= gr.x && x <= gr.x + gr.w && y >= gr.y && y <= gr.y + gr.h) return g;
        }
        return null;
    };

    /** 拖拽子节点：过半进入新组框时高亮组边框（组内移动/拖出不高亮；拖动分组覆盖节点不算加入） */
    const onNodeDrag: OnNodeDrag<CanvasNode> = (_e, node) => {
        if (node.type === 'groupNode' || node.type === 'tempAnchorNode') return;
        const rect = getNodeAbsRect(node);
        const parent = node.parentId ? nodes.find(n => n.id === node.parentId) : null;
        if (parent && isCenterInGroup(rect, parent)) {
            setGroupHighlight(null);
            return;
        }
        setGroupHighlight(findJoinGroup(rect, node.id, parent?.id)?.id ?? null);
    };

    /** 拖拽结束：入组（自动平移到组框内）/ 中心移出组框则脱离（不再计数、不跟随组移动）
     *  多选场景：所有选中节点一起入组/出组 */
    const onNodeDragStop: OnNodeDrag<CanvasNode> = (_e, node) => {
        setGroupHighlight(null);
        if (node.type === 'groupNode' || node.type === 'tempAnchorNode') return;

        // 收集需要一起处理的节点：当前拖拽节点 + 所有选中节点（排除 group/tempAnchor）
        const selectedIds = new Set<string>();
        selectedIds.add(node.id);
        for (const n of nodes) {
            if (n.selected && n.id !== node.id && n.type !== 'groupNode' && n.type !== 'tempAnchorNode') {
                selectedIds.add(n.id);
            }
        }

        const rect = getNodeAbsRect(node);
        const parent = node.parentId ? nodes.find(n => n.id === node.parentId) : null;
        // 中心仍在原组内：保持原分组
        if (parent && isCenterInGroup(rect, parent)) return;
        // 中心已移出原组（或无父组）：按过半规则找新组
        const group = findJoinGroup(rect, node.id, parent?.id);
        if (!group && !node.parentId) return;

        setNodes(nds => {
            let next: CanvasNode[];
            if (group && node.parentId !== group.id) {
                // 加入分组：所有选中节点一起入组，坐标转相对
                const gr = getGroupRect(group);
                const PAD = 16;
                const toJoin = new Map<string, { x: number; y: number }>();
                for (const id of selectedIds) {
                    const n = nds.find(x => x.id === id);
                    if (!n) continue;
                    const r = getNodeAbsRect(n);
                    let relX = r.x - gr.x;
                    let relY = r.y - gr.y;
                    if (r.x < gr.x) relX = PAD;
                    else if (r.x + r.w > gr.x + gr.w) relX = Math.max(PAD, gr.w - r.w - PAD);
                    if (r.y < gr.y) relY = PAD;
                    else if (r.y + r.h > gr.y + gr.h) relY = Math.max(PAD, gr.h - r.h - PAD);
                    toJoin.set(id, { x: relX, y: relY });
                }
                next = nds.map(n =>
                    toJoin.has(n.id)
                        ? { ...n, parentId: group.id, position: toJoin.get(n.id)! } as CanvasNode
                        : n
                );
            } else if (!group && node.parentId) {
                // 拖出分组：所有选中节点一起脱离父级，坐标转绝对
                const toDetach = new Map<string, { x: number; y: number }>();
                for (const id of selectedIds) {
                    const n = nds.find(x => x.id === id);
                    if (!n) continue;
                    const r = getNodeAbsRect(n);
                    toDetach.set(id, { x: r.x, y: r.y });
                }
                next = nds.map(n =>
                    toDetach.has(n.id)
                        ? { ...n, parentId: undefined, position: toDetach.get(n.id)! } as CanvasNode
                        : n
                );
            } else {
                return nds;
            }
            // 分组节点排在数组前面（React Flow 要求父节点先于子节点渲染）
            return [...next].sort((a, b) => Number(b.type === 'groupNode') - Number(a.type === 'groupNode'));
        });
    };

    /** 双击画布空白：弹出添加节点菜单 */
    const handleDoubleClick = (e: React.MouseEvent) => {
        const target = e.target as HTMLElement;
        // 仅空白区域触发：命中点在 pane 内且不在任何节点上
        if (!target.closest('.react-flow__pane') || target.closest('.react-flow__node')) return;
        const rect = wrapperRef.current?.getBoundingClientRect();
        if (!rect) return;
        const flow = screenToFlowPosition({ x: e.clientX, y: e.clientY });
        setMenuPos({ x: e.clientX - rect.left, y: e.clientY - rect.top, flowX: flow.x, flowY: flow.y });
    };

    /** 选择菜单项：文本/图片/视频/音频节点已接入 */
    const handleMenuSelect = (type: AddNodeMenuType) => {
        if (!menuPos) return;
        if (type === 'textNode') addTextNode({ x: menuPos.flowX, y: menuPos.flowY });
        if (type === 'imageNode') addImageNode({ x: menuPos.flowX, y: menuPos.flowY });
        if (type === 'videoNode') addVideoNode({ x: menuPos.flowX, y: menuPos.flowY });
        if (type === 'audioNode') addAudioNode({ x: menuPos.flowX, y: menuPos.flowY });
        if (type === 'genConfigNode') addGenConfigNode({ x: menuPos.flowX, y: menuPos.flowY });
        if (type === 'groupNode') addGroupNode({ x: menuPos.flowX, y: menuPos.flowY });
        setMenuPos(null);
    };

    /** 连接节点：生成自定义连线（禁止自连；Loose 模式下规范方向） */
    const onConnect = (conn: Connection) => {
        if (conn.source === conn.target) return;
        setEdges(eds => addEdge({ ...normalizeConn(conn), type: 'connectEdge' }, eds));
    };

    /** 拖线松手：未连上时，落点附近有节点则吸附连线；落空白处则弹出「引用该节点生成」菜单 */
    const onConnectEnd = (event: MouseEvent | TouchEvent, connectionState: FinalConnectionState) => {
        if (connectionState.isValid || !connectionState.fromNode) return;
        if (!('clientX' in event)) return;
        const fromNodeId = connectionState.fromNode.id;
        const fromHandleType = connectionState.fromHandle?.type ?? 'source';
        const flowPos = screenToFlowPosition({ x: event.clientX, y: event.clientY });

        // 落点吸附：鼠标滑到节点附近（含 40px 外扩）即视为要连到该节点
        const hit = findHitNode(flowPos, fromNodeId);
        if (hit) {
            const conn: Connection = fromHandleType === 'target'
                ? { source: hit.id, sourceHandle: 'out', target: fromNodeId, targetHandle: 'in' }
                : { source: fromNodeId, sourceHandle: 'out', target: hit.id, targetHandle: 'in' };
            setEdges(eds => addEdge({ ...conn, type: 'connectEdge' }, eds));
            return;
        }

        // 落空白处：临时锚点固定虚线端点，弹出「引用该节点生成」菜单
        const rect = wrapperRef.current?.getBoundingClientRect();
        if (!rect) return;
        const anchorId = `anchor-${++nodeIdRef.current}`;
        setNodes(nds => [...nds, { id: anchorId, type: 'tempAnchorNode', position: flowPos, selectable: false, draggable: false, data: {} } as CanvasNode]);
        setEdges(eds => [...eds, {
            id: `temp-edge-${anchorId}`,
            ...(fromHandleType === 'target'
                ? { source: anchorId, sourceHandle: 'out', target: fromNodeId, targetHandle: 'in' }
                : { source: fromNodeId, sourceHandle: 'out', target: anchorId, targetHandle: 'in' }),
            type: 'connectEdge',
            selectable: false,
            style: { strokeDasharray: '6 4' },
            data: { hideCut: true },
        }]);
        setConnectMenu({
            x: event.clientX - rect.left,
            y: event.clientY - rect.top,
            flowPos,
            fromNodeId,
            fromHandleType,
            anchorId,
        });
    };

    /** 「引用该节点生成」菜单选择：清理临时锚点与虚线，在落点创建节点并自动连线 */
    const handleConnectMenuSelect = (type: AddNodeMenuType) => {
        if (!connectMenu) return;
        clearTempAnchor(connectMenu.anchorId);
        const pos = connectMenu.flowPos;
        // 分组节点不参与连线，直接创建后关闭菜单
        if (type === 'groupNode') {
            addGroupNode(pos);
            setConnectMenu(null);
            return;
        }
        const newId =
            type === 'textNode' ? addTextNode(pos) :
            type === 'imageNode' ? addImageNode(pos) :
            type === 'videoNode' ? addVideoNode(pos) :
            type === 'genConfigNode' ? addGenConfigNode(pos) :
            addAudioNode(pos);
        const conn: Connection = connectMenu.fromHandleType === 'target'
            ? { source: newId, sourceHandle: 'out', target: connectMenu.fromNodeId, targetHandle: 'in' }
            : { source: connectMenu.fromNodeId, sourceHandle: 'out', target: newId, targetHandle: 'in' };
        setEdges(eds => addEdge({ ...conn, type: 'connectEdge' }, eds));
        setConnectMenu(null);
    };

    // 点击菜单外部关闭「引用该节点生成」（忽略打开后 200ms 内的事件：连线松手的 pointerup 会补发 click）
    useEffect(() => {
        if (!connectMenu) return;
        const openedAt = Date.now();
        const close = (e: MouseEvent) => {
            if (Date.now() - openedAt < 200) return;
            if ((e.target as HTMLElement).closest('.canvas-add-node-menu')) return;
            clearTempAnchor(connectMenu.anchorId);
            setConnectMenu(null);
        };
        window.addEventListener('click', close);
        return () => window.removeEventListener('click', close);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [connectMenu]);

    /** 操作栏加节点：文本/图片/视频/音频节点已接入 */
    const handleToolbarAddNode = (key: string) => {
        if (key === 'text') addTextNode();
        if (key === 'image') addImageNode();
        if (key === 'video') addVideoNode();
        if (key === 'audio') addAudioNode();
        if (key === 'genConfig') addGenConfigNode();
        if (key === 'group') addGroupNode();
    };

    /** 清空画布：删除所有节点与连线（可撤销）；同时关闭可能打开的菜单 */
    const handleClearCanvas = () => {
        setMenuPos(null);
        setConnectMenu(null);
        setNodes([]);
        setEdges([]);
    };

    /** 上传文件：按 MIME 主类型（image/video/audio）创建对应媒体节点，读取为 dataURL（与节点内上传一致）；多个文件依次错开避免重叠 */
    const handleUploadFiles = (files: File[]) => {
        const rect = wrapperRef.current?.getBoundingClientRect();
        let created = 0;
        files.forEach(file => {
            const kind = file.type.split('/')[0];
            if (kind !== 'image' && kind !== 'video' && kind !== 'audio') return;
            const reader = new FileReader();
            reader.onload = () => {
                const url = reader.result as string;
                const offset = created++ * 40;
                const position = screenToFlowPosition({
                    x: (rect?.left ?? 0) + (rect?.width ?? window.innerWidth) / 2 - 320 + offset,
                    y: (rect?.top ?? 0) + (rect?.height ?? window.innerHeight) / 2 - 120 + offset,
                });
                if (kind === 'image') addImageNode(position, url);
                else if (kind === 'video') addVideoNode(position, url);
                else addAudioNode(position, url);
            };
            reader.readAsDataURL(file);
        });
    };

    /** 阻止 Ctrl+Click 触发浏览器右键菜单（Mac 上 Ctrl+Click = 右键） */
    const handleContextMenu = (e: React.MouseEvent) => {
        if (e.ctrlKey || e.metaKey) e.preventDefault();
    };

    return (
        <div
            ref={wrapperRef}
            className="relative flex h-[calc(100vh-3.5rem)] overflow-hidden"
            onDoubleClick={handleDoubleClick}
            onContextMenu={handleContextMenu}
        >
            <CanvasModelsContext.Provider value={models}>
                <CanvasApiKeysContext.Provider value={apiKeys}>
                    <ReactFlow
                        className="h-full w-full bg-background dark:bg-[#0b0f19]"
                        nodes={nodes}
                        edges={edges}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        onConnect={onConnect}
                        onConnectEnd={onConnectEnd}
                        onNodeDrag={onNodeDrag}
                        onNodeDragStop={onNodeDragStop}
                        nodeTypes={nodeTypes}
                        edgeTypes={edgeTypes}
                        connectionMode={ConnectionMode.Loose}
                        connectionRadius={40}
                        multiSelectionKeyCode="Shift"
                        deleteKeyCode={['Backspace', 'Delete']}
                        panOnDrag
                        zoomOnScroll
                        zoomOnPinch
                        zoomOnDoubleClick={false}
                        minZoom={0.2}
                        maxZoom={4}
                        proOptions={{ hideAttribution: true }}
                        onPaneClick={() => setMenuPos(null)}
                        onMoveStart={() => setMenuPos(null)}
                    >
                        {gridStyle !== 'blank' && (
                            <Background
                                className="[&_circle]:fill-[rgba(28,33,40,0.22)] dark:[&_circle]:fill-[rgba(255,255,255,0.18)]"
                                variant={gridStyle === 'dots' ? BackgroundVariant.Dots : BackgroundVariant.Lines}
                                gap={24}
                                size={1.5}
                            />
                        )}
                        <Panel position="bottom-left">
                            <ViewportBar />
                        </Panel>
                    </ReactFlow>
                    {/* 操作栏：排除左下角小地图区域（220 + 边距）后，在剩余宽度内居中 */}
                    <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center pl-58.75">
                        <div className="pointer-events-auto">
                            <CanvasToolbar
                                gridStyle={gridStyle}
                                onGridStyleChange={setGridStyle}
                                onAddNode={handleToolbarAddNode}
                                canUndo={canUndo}
                                canRedo={canRedo}
                                onUndo={undo}
                                onRedo={redo}
                                onClearCanvas={handleClearCanvas}
                                onUploadFiles={handleUploadFiles}
                            />
                        </div>
                    </div>

                    {/* 历史会话浮层：左上角展开/收起 */}
                    <CanvasHistoryPanel open={historyOpen} onToggle={() => setHistoryOpen(v => !v)} />

                    {menuPos && (
                        <AddNodeMenu x={menuPos.x} y={menuPos.y} onSelect={handleMenuSelect} />
                    )}

                    {/* 拖线落空白处：引用该节点生成 */}
                    {connectMenu && (
                        <AddNodeMenu x={connectMenu.x} y={connectMenu.y} title="引用该节点生成" onSelect={handleConnectMenuSelect} />
                    )}
                </CanvasApiKeysContext.Provider>
            </CanvasModelsContext.Provider>
        </div>
    );
};

export const ChatCanvas = () => (
    <ReactFlowProvider>
        <FlowCanvas />
    </ReactFlowProvider>
);
