"use client";
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from "react-i18next";
import { Handle, Position, useReactFlow } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { Info, Trash2, ImagePlus, Minus, Plus } from 'lucide-react';
import { useCanvasApiKeys, useCanvasModels } from '../models-context';
import { createNodeGenerateController, generateNodeContent, isGenerateCancel } from '../api/generate';
import NodeGenerateArea from './shared/NodeGenerateArea';
import NodeCornerResizer from './shared/NodeCornerResizer';
import NodeGenerateOverlay from './shared/NodeGenerateOverlay';
import { useNodeClickExpand } from './shared/useNodeClickExpand';
import { GEN_CONFIG_DEFAULTS } from './GenConfigNode';
import { NODE_DEFAULT_SIZE } from '../index';

export interface TextNodeData extends Record<string, unknown> {
    /** 卡片正文（双击编辑） */
    text: string;
    /** 输入区提示词 */
    prompt: string;
    /** 选中的模型（`供应商ID::原始模型名`） */
    model: string;
    /** 选中的 API 密钥 id（空则生成时取密钥列表第一个） */
    apiKeyId?: string;
    /** 推理强度 */
    reasoning: string;
    /** 生成次数 */
    count: number;
    /** 正文字号 */
    fontSize?: number;
    /** 生成配置节点下发的自动生成标记：节点创建后由本节点自身发起一次生成（随即清除） */
    autoGenerate?: boolean;
}

export type TextFlowNode = Node<TextNodeData, 'textNode'>;

/** 正文字号范围与步进（缩小/放大按钮） */
const FONT_SIZE_MIN = 10;
const FONT_SIZE_MAX = 32;
const FONT_SIZE_STEP = 2;
const FONT_SIZE_DEFAULT = 14;

/** 多次推理结果节点：水平偏移与竖向间距 */
const RESULT_OFFSET_X = 120;
const RESULT_GAP_Y = 60;

export default function TextNode({ id, data, selected, dragging }: NodeProps<Node<TextNodeData, 'textNode'>>) {
    const { t } = useTranslation("canvas");
    const { updateNodeData, deleteElements, getNode, setNodes, setEdges } = useReactFlow();
    const [editing, setEditing] = useState(false);
    // 悬停态：悬停/选中时显示四角缩放手柄
    const [hovered, setHovered] = useState(false);
    // 点击展开态：仅真实点击（非拖拽）时显示操作栏与生成区
    const { expanded, onPointerDown, onPointerUp } = useNodeClickExpand(selected, dragging);

    const update = (patch: Partial<TextNodeData>) => updateNodeData(id, patch);

    const apiKeys = useCanvasApiKeys();
    const marketModels = useCanvasModels();
    const controllerRef = useRef<ReturnType<typeof createNodeGenerateController> | null>(null);
    if (!controllerRef.current) controllerRef.current = createNodeGenerateController();
    const [isRunning, setIsRunning] = useState(false);
    const [generateError, setGenerateError] = useState('');

    /** 发送/停止：按提示词生成文本；count > 1 时把每条结果作为新节点竖向追加到右侧 */
    const handleSend = () => {
        controllerRef.current?.toggle(id, async signal => {
            setIsRunning(true);
            setGenerateError('');
            try {
                const result = await generateNodeContent({ capability: 'text', data, models: marketModels, apiKeys, signal });
                if (result.capability !== 'text') return;
                if (result.texts.length > 1) appendResultNodes(result.texts);
                else update({ text: result.text });
            } catch (error) {
                if (!isGenerateCancel(error)) setGenerateError(error instanceof Error ? error.message : t('common.generateFailed'));
            } finally {
                setIsRunning(false);
            }
        });
    };

    // 生成配置节点创建本节点时下发的自动生成：由本节点自身发起请求，loading/失败状态由本节点管理
    const autoFiredRef = useRef(false);
    useEffect(() => {
        if (!data.autoGenerate || autoFiredRef.current) return;
        autoFiredRef.current = true;
        update({ autoGenerate: false });
        handleSend();
        // 仅在标记下发时触发一次；handleSend/update 随渲染重建，不作为依赖
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [data.autoGenerate]);

    /** 在当前节点右侧追加多个文本结果节点：整体垂直居中于当前节点，逐个连线 */
    const appendResultNodes = (texts: string[]) => {
        const self = getNode(id);
        if (!self) return;
        const w = self.measured?.width ?? NODE_DEFAULT_SIZE.textNode.width;
        const h = self.measured?.height ?? NODE_DEFAULT_SIZE.textNode.height;
        const x = self.position.x + w + RESULT_OFFSET_X;
        const startY = self.position.y + h / 2 - ((texts.length - 1) * (h + RESULT_GAP_Y)) / 2;
        const stamp = Date.now();
        const newNodes = texts.map((text, i) => ({
            id: `text-result-${stamp}-${i}`,
            type: 'textNode',
            position: { x, y: startY + i * (h + RESULT_GAP_Y) },
            style: { ...NODE_DEFAULT_SIZE.textNode },
            data: { text, prompt: '', model: '', apiKeyId: '', reasoning: '自动', count: 1, fontSize: FONT_SIZE_DEFAULT },
        }));
        setNodes(nds => [...nds, ...(newNodes as never[])]);
        setEdges(eds => [
            ...eds,
            ...newNodes.map(n => ({
                id: `edge-${id}-${n.id}`,
                source: id,
                sourceHandle: 'out',
                target: n.id,
                targetHandle: 'in',
                type: 'connectEdge',
            })),
        ]);
    };

    /** 生图：在本节点右侧创建一个「生图」模式的生成配置节点，并连线引用当前文本 */
    const handleGenImage = () => {
        const self = getNode(id);
        if (!self) return;
        const w = self.measured?.width ?? 640;
        const newId = `genConfig-${Date.now()}`;
        setNodes(nds => [
            ...nds,
            {
                id: newId,
                type: 'genConfigNode',
                position: { x: self.position.x + w + 120, y: self.position.y },
                data: { ...structuredClone(GEN_CONFIG_DEFAULTS), mode: 'image' },
            } as never,
        ]);
        setEdges(eds => [
            ...eds,
            { id: `edge-${id}-${newId}`, source: id, sourceHandle: 'out', target: newId, targetHandle: 'in', type: 'connectEdge' },
        ]);
    };

    const fontSize = data.fontSize ?? FONT_SIZE_DEFAULT;
    /** 缩小/放大正文字号 */
    const stepFontSize = (delta: number) =>
        update({ fontSize: Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, fontSize + delta)) });

    /** 头部操作：删除/生图有逻辑，其余先只展示 */
    const headerActions = [
        // { key: 'info', label: '信息', icon: <Info className="h-4 w-4" /> },
        { key: 'delete', label: '删除', icon: <Trash2 className="h-4 w-4" />, onClick: () => void deleteElements({ nodes: [{ id }] }) },
        { key: 'genImage', label: '生图', icon: <ImagePlus className="h-4 w-4" />, onClick: handleGenImage },
        { key: 'shrink', label: '缩小', icon: <Minus className="h-4 w-4" />, onClick: () => stepFontSize(-FONT_SIZE_STEP) },
        { key: 'enlarge', label: '放大', icon: <Plus className="h-4 w-4" />, onClick: () => stepFontSize(FONT_SIZE_STEP) },
    ];

    return (
        // pointer-events-none：卡片两侧的不可见区域不拦截指针，避免重叠时挡住其他节点拖拽（可见部分各自恢复 auto）
        // 根容器撑满节点框（节点 style 宽高 = 卡片区尺寸，NodeResizer 直接缩放）
        <div
            className="group pointer-events-none relative h-full w-full"
            onPointerEnter={() => setHovered(true)}
            onPointerLeave={() => setHovered(false)}
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
        >
            {/* 四角缩放手柄：悬停/选中时可见（只画角点，不画边框） */}
            <NodeCornerResizer visible={hovered || !!selected} minWidth={240} minHeight={120} />
            {/* 点击展开时节点上方悬浮操作栏：宽度自适应内容，水平居中（拖拽不展开） */}
            {expanded && (
                <div className="nodrag pointer-events-auto absolute -top-16 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-popover px-2 py-1.5 whitespace-nowrap shadow-card">
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

            {/* 节点标题：默认隐藏，悬停/选中时显示（悬浮在卡片上方，不占节点框高度） */}
            <div
                className={`absolute -top-5 left-1 text-xs text-muted-foreground transition-opacity ${
                    selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                }`}
            >
                {t('textNode.title')}
            </div>

            {/* 卡片主体：填满节点框（节点 style 宽高 = 卡片尺寸），双击进入编辑 */}
            <div
                className={`pointer-events-auto relative h-full w-full rounded-2xl border-2 bg-card p-4 transition-colors group-hover:border-primary/60 ${
                    selected ? 'border-primary' : 'border-border'
                }`}
                onDoubleClick={() => setEditing(true)}
            >
                {editing ? (
                    <textarea
                        autoFocus
                        defaultValue={data.text}
                        placeholder={t('textNode.placeholder')}
                        style={{ fontSize }}
                        onBlur={e => {
                            update({ text: e.target.value });
                            setEditing(false);
                        }}
                       className="nodrag nowheel h-full w-full resize-none rounded-2xl bg-transparent p-3 pr-1.5 text-foreground outline-none placeholder:text-muted-foreground"
                    />
                ) : (
                    /* 内容超出卡片时内部滚动（nowheel 避免触发画布缩放） */
                    /* 注意：不能加 nodrag——容器撑满整张卡片，加了会导致节点无法拖拽（编辑态 textarea 保留 nodrag 以便划选） */
                    <div className="nowheel h-full w-full overflow-y-auto rounded-2xl p-3 pr-1.5 wrap-break-word whitespace-pre-wrap" style={{ fontSize }}>
                        {data.text ? (
                            <span className="text-foreground">{data.text}</span>
                        ) : (
                            <span className="text-muted-foreground">{t('textNode.placeholder')}</span>
                        )}
                    </div>
                )}

                {/* 生图按钮：新增「生图」模式的生成配置节点并自动连线 */}
                <button
                    type="button"
                    className="nodrag absolute top-4 right-4 flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-popover px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent"
                    onClick={e => {
                        e.stopPropagation();
                        handleGenImage();
                    }}
                >
                    <ImagePlus className="h-3.5 w-3.5" />
                    {t('textNode.generateImage')}
                </button>

                {/* 生成状态浮层：生成中 loading + 进度，失败报错 + 重试 */}
                <NodeGenerateOverlay isRunning={isRunning} error={generateError} onRetry={handleSend} />

                {/* 连接点：左入右出（相对卡片主体定位，输入区展开后仍对准卡片中点） */}
                <Handle
                    id="in"
                    type="target"
                    position={Position.Left}
                    style={{ width: 10, height: 10, background: 'var(--background)', border: '2px solid var(--muted-foreground)' }}
                />
                <Handle
                    id="out"
                    type="source"
                    position={Position.Right}
                    style={{ width: 10, height: 10, background: 'var(--background)', border: '2px solid var(--muted-foreground)' }}
                />
            </div>

            {/* 点击展开时的生成区域（编辑态同样保持展示）：绝对定位在节点下方，不占节点框高度 */}
            {expanded && (
                <div className="absolute top-full left-1/2 z-10 -translate-x-1/2">
                <NodeGenerateArea
                    prompt={data.prompt}
                    promptPlaceholder={t('textNode.inputPlaceholder')}
                    onPromptChange={v => update({ prompt: v })}
                    capability="text"
                    model={data.model}
                    onModelChange={v => update({ model: v })}
                    apiKeyId={data.apiKeyId}
                    onApiKeyChange={v => update({ apiKeyId: v })}
                    onSend={handleSend}
                    isRunning={isRunning}
                />
                </div>
            )}
        </div>
    );
}
