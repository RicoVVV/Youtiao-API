"use client";
import { useCallback, useMemo, useRef, useState } from 'react';
import { useTranslation } from "react-i18next";
import { Handle, Position, useReactFlow, useStore } from '@xyflow/react';
import type { Edge, Node, NodeProps } from '@xyflow/react';
import { Info, Trash2, Play, SlidersHorizontal, X, Cpu, ChevronDown, Check } from 'lucide-react';
import { CHANNEL_MODEL_SEPARATOR, useCanvasConfigStore } from '@/stores/use-canvas-config-store';
import { useCanvasModels } from '../models-context';
import { NODE_DEFAULT_SIZE } from '../index';
import NodeCornerResizer from './shared/NodeCornerResizer';
import ApiKeySelect from './shared/ApiKeySelect';
import { useNodeClickExpand } from './shared/useNodeClickExpand';
import ImageNodeSettings from './settings/ImageNodeSettings';
import TextNodeSettings from './settings/TextNodeSettings';
import VideoNodeSettings, { videoRatioSummaryLabel } from './settings/VideoNodeSettings';
import type { ImageNodeData } from './ImageNode';
import type { TextNodeData } from './TextNode';
import type { VideoNodeData } from './VideoNode';

/** 生成配置的三种能力模式：生图/文本/视频，各自模型与参数设置不同 */
export type GenConfigMode = 'image' | 'text' | 'video';

export interface GenConfigNodeData extends Record<string, unknown> {
    /** 组装提示词，支持 @[node:节点ID] 形式引用已连接资产 */
    prompt: string;
    /** 当前能力模式 */
    mode: GenConfigMode;
    /** 选中的 API 密钥 id（空则生成时取密钥列表第一个）；随生成下发给结果节点 */
    apiKeyId?: string;
    /** 各模式独立保存自己的配置，切换模式互不覆盖 */
    image: Omit<ImageNodeData, 'imageUrl' | 'prompt'>;
    text: Omit<TextNodeData, 'text' | 'prompt'>;
    video: Omit<VideoNodeData, 'videoUrl' | 'prompt'>;
}

export type GenConfigFlowNode = Node<GenConfigNodeData, 'genConfigNode'>;

/** 各模式默认配置（与对应节点创建时的初始 data 对齐） */
export const GEN_CONFIG_DEFAULTS: GenConfigNodeData = {
    prompt: '',
    mode: 'image',
    apiKeyId: '',
    image: { model: '', ratio: '1:1', width: 1024, height: 1024, align16: true, transparent: false, count: 1 },
    text: { model: '', reasoning: '自动', count: 1, fontSize: 14 },
    video: { model: '', ratio: '横屏', width: 1280, height: 720, seconds: 6 },
};

/** 提示词中的资产引用 token：@[node:节点ID] */
const REFERENCE_PATTERN = /@\[node:([^\]]+)\]/g;

/** 上游输入资产：从已连接的上游节点读取的可引用内容 */
interface UpstreamInput {
    nodeId: string;
    type: 'text' | 'image' | 'video' | 'audio';
    /** 展示标题（图片1/文本1 这类编号在渲染时按类型生成） */
    title: string;
    /** 文本内容（text 类型） */
    text?: string;
    /** 图片地址（image 类型，作为生成参考图下发） */
    imageUrl?: string;
}

const NODE_TYPE_TO_INPUT: Record<string, UpstreamInput['type']> = {
    textNode: 'text',
    imageNode: 'image',
    videoNode: 'video',
    audioNode: 'audio',
};

/** 输入资产类型 → i18n label key */
const INPUT_TYPE_LABEL_KEYS: Record<UpstreamInput['type'], string> = {
    text: 'common.typeText',
    image: 'common.typeImage',
    video: 'common.typeVideo',
    audio: 'common.typeAudio',
};

/** 推理强度存储值（中文，持久化兼容）→ i18n label key */
const REASONING_LABEL_KEYS: Record<string, string> = {
    '自动': 'settings.reasoningAuto',
    '低': 'settings.reasoningLow',
    '中': 'settings.reasoningMedium',
    '高': 'settings.reasoningHigh',
    '极高': 'settings.reasoningExtraHigh',
};

/** 能力模式 → i18n label key */
const MODE_OPTIONS: { value: GenConfigMode; labelKey: string }[] = [
    { value: 'image', labelKey: 'channelForm.capability.image' },
    { value: 'text', labelKey: 'common.typeText' },
    { value: 'video', labelKey: 'common.typeVideo' },
];

/** 各能力对应的默认模型配置键（与 NodeGenerateArea 对齐） */
const DEFAULT_MODEL_KEY = {
    image: 'imageModel',
    video: 'videoModel',
    text: 'textModel',
} as const;

/** 从 `渠道ID::模型名` 中取模型名用于展示 */
const modelNameOf = (value: string) => value.split(CHANNEL_MODEL_SEPARATOR).pop() || value;

/** 旧存档中本节点的固定默认高度：视为未手动缩放（内容自适应） */
const LEGACY_FIXED_HEIGHT = 260;

export default function GenConfigNode({ id, data, selected, dragging }: NodeProps<GenConfigFlowNode>) {
    const { t } = useTranslation("canvas");
    const { updateNodeData, deleteElements, getNode, setNodes, setEdges } = useReactFlow();
    // 点击展开态：仅真实点击（非拖拽）时显示操作栏
    const { expanded, onPointerDown, onPointerUp } = useNodeClickExpand(selected, dragging);

    const update = useCallback((patch: Partial<GenConfigNodeData>) => updateNodeData(id, patch), [id, updateNodeData]);

    /** 当前模式配置更新：写回对应模式的子配置 */
    const updateModeConfig = useCallback(
        (patch: Record<string, unknown>) => updateNodeData(id, { [data.mode]: { ...data[data.mode], ...patch } }),
        [id, data, updateNodeData],
    );

    // ---- 上游已连接资产（边 target 为本节点的 source 节点） ----
    // 注意：useStore 的 selector 必须返回稳定快照（原样返回每次渲染都是新对象会触发无限重渲染）
    const upstreamKey = useStore(
        useCallback(
            state =>
                state.edges
                    .filter((e: Edge) => e.target === id && e.source !== id)
                    .map((e: Edge) => e.source)
                    .join(','),
            [id],
        ),
    );
    const allNodes = useStore(s => s.nodes);
    /** 输入资产类型标签（当前语言） */
    const inputTypeLabel = useCallback((type: UpstreamInput['type']) => t(INPUT_TYPE_LABEL_KEYS[type]), [t]);
    const { inputs, inputSummary } = useMemo(() => {
        const list: UpstreamInput[] = [];
        const counters = { text: 0, image: 0, video: 0, audio: 0 };
        for (const sid of new Set(upstreamKey.split(',').filter(Boolean))) {
            const n = allNodes.find(node => node.id === sid);
            if (!n) continue;
            const type = NODE_TYPE_TO_INPUT[n.type ?? ''];
            if (!type) continue;
            counters[type] += 1;
            const d = n.data as Record<string, unknown>;
            list.push({
                nodeId: sid,
                type,
                title: `${inputTypeLabel(type)}${counters[type]}`,
                text: type === 'text' ? String(d.text ?? d.prompt ?? '') : String(d.prompt ?? ''),
                imageUrl: type === 'image' ? String(d.imageUrl ?? '') : undefined,
            });
        }
        return {
            inputs: list,
            inputSummary: {
                text: list.filter(i => i.type === 'text').length,
                image: list.filter(i => i.type === 'image').length,
                video: list.filter(i => i.type === 'video').length,
                audio: list.filter(i => i.type === 'audio').length,
            },
        };
    }, [allNodes, upstreamKey]);

    const config = useCanvasConfigStore(s => s.config);
    const [composerOpen, setComposerOpen] = useState(false);
    const [modelOpen, setModelOpen] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);
    // 悬停态：悬停/选中时显示四角缩放手柄
    const [hovered, setHovered] = useState(false);
    /** 已创建结果节点计数：多次点击生成时竖向排开，避免重叠 */
    const spawnCountRef = useRef(0);

    const mode = data.mode;
    const modeConfig = data[mode];

    /** 高度自适应：默认由内容撑开；用户四角缩放改变高度后固定为该高度（旧存档的默认高度 260 视为未缩放） */
    const styleHeight = useStore(
        useCallback(state => {
            const n = state.nodes.find(node => node.id === id);
            return typeof n?.style?.height === 'number' ? n.style.height : null;
        }, [id]),
    );
    const heightFixed = styleHeight !== null && styleHeight !== LEGACY_FIXED_HEIGHT;

    /** 组装提示词：有 @ 引用时按 token 解析；无 @ 引用时自动纳入全部已连接输入（文本拼入提示词，媒体作为引用） */
    const resolvePrompt = useCallback((): { prompt: string; refs: UpstreamInput[] } => {
        if (!/@\[node:[^\]]+\]/.test(data.prompt)) {
            const texts = inputs.filter(i => i.type === 'text' && i.text).map(i => i.text as string);
            return { prompt: [data.prompt.trim(), ...texts].filter(Boolean).join('\n\n'), refs: inputs };
        }
        const inputById = new Map(inputs.map(i => [i.nodeId, i]));
        const refs: UpstreamInput[] = [];
        const textBlocks: string[] = [];
        const seen = new Map<string, string>();
        const counters = { text: 0, image: 0, video: 0, audio: 0 };
        const prompt = data.prompt.replace(REFERENCE_PATTERN, (raw, nodeId: string) => {
            const input = inputById.get(nodeId);
            if (!input) return raw;
            let label = seen.get(nodeId);
            if (!label) {
                counters[input.type] += 1;
                label = `${inputTypeLabel(input.type)}${counters[input.type]}`;
                seen.set(nodeId, label);
                refs.push(input);
                if (input.type === 'text' && input.text) textBlocks.push(`【${label}】\n${input.text}`);
            }
            return input.type === 'text' ? `【${label}】` : label;
        });
        return { prompt: textBlocks.length ? `${prompt.trim()}\n\n${textBlocks.join('\n\n')}` : prompt.trim(), refs };
    }, [data.prompt, inputs]);

    /** 点击生成：只创建结果节点+连线，请求由结果节点自身触发 */
    const handleSpawn = () => {
        const { prompt, refs } = resolvePrompt();
        const mediaHint = refs.some(r => r.type !== 'text') ? t('genConfigNode.mediaRefHint') : '';
        const mediaPrompt = (mode === 'image' && refs.some(r => r.type === 'image') ? `${prompt}\n\n${t('genConfigNode.imageRefPromptHint')}` : prompt + mediaHint).trim() || t('genConfigNode.defaultPrompt');
        // 参考图快照下发给结果节点（图/视频生成按多参考图提交；与提示词同样在生成时定稿）
        const referenceImages = refs.map(r => r.imageUrl).filter((u): u is string => Boolean(u));
        createResultNode(mediaPrompt, referenceImages);
    };

    /** 在右侧创建结果节点（每次都新建，竖向排开）并连线，写入生成参数 + autoGenerate 触发节点自发请求 */
    const createResultNode = (mediaPrompt: string, referenceImages: string[] = []): string => {
        // 参考图仅图/视频节点消费；apiKeyId 随配置下发，结果节点生成时按所选密钥鉴权
        const pendingData = { ...modeConfig, prompt: mediaPrompt, apiKeyId: data.apiKeyId ?? '', autoGenerate: true, ...(mode === 'image' || mode === 'video' ? { referenceImages } : {}) };

        const self = getNode(id);
        if (!self) throw new Error('节点不存在');
        const w = self.measured?.width ?? 360;
        const gap = 120;
        const count = spawnCountRef.current;
        spawnCountRef.current = count + 1;
        // 首个节点右侧 120px；后续节点右侧 120px + 竖向偏移 360px 间距（与自身高度拉开）
        const newId = `${mode}-gen-${Date.now()}`;
        const position = { x: self.position.x + w + gap, y: self.position.y + count * 360 };
        const base = { id: newId, position, style: { ...NODE_DEFAULT_SIZE[`${mode}Node`] } } as const;
        const newNode =
            mode === 'image'
                ? { ...base, type: 'imageNode', data: { imageUrl: '', ...pendingData } }
                : mode === 'text'
                  ? { ...base, type: 'textNode', data: { text: '', ...pendingData } }
                  : { ...base, type: 'videoNode', data: { videoUrl: '', ...pendingData } };
        setNodes(nds => [...nds, newNode as never]);
        setEdges(eds => [...eds, { id: `edge-${id}-${newId}`, source: id, sourceHandle: 'out', target: newId, targetHandle: 'in', type: 'connectEdge' }]);
        return newId;
    };

    const headerActions = [
        // { key: 'info', label: '信息', icon: <Info className="h-4 w-4" /> },
        { key: 'delete', label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => void deleteElements({ nodes: [{ id }] }) },
    ];

    const settingsSummary = useMemo(() => {
        if (mode === 'image') {
            const c = modeConfig as GenConfigNodeData['image'];
            return t('common.summaryImage', { size: c.ratio, count: c.count });
        }
        if (mode === 'text') {
            const c = modeConfig as GenConfigNodeData['text'];
            const reasoningKey = String(c.reasoning);
            return t('common.summaryText', { reasoning: t(REASONING_LABEL_KEYS[reasoningKey] || reasoningKey), count: c.count });
        }
        if (mode === 'video') {
            const c = modeConfig as GenConfigNodeData['video'];
            return t('common.summaryVideo', { ratio: videoRatioSummaryLabel(String(c.ratio), Number(c.width), Number(c.height), t), width: c.width, height: c.height, seconds: c.seconds });
        }
    }, [mode, modeConfig, t]);

    const settingsTitle = t(`common.settingsTitle${mode.charAt(0).toUpperCase() + mode.slice(1)}`);

    const hasAnyInput = Object.values(inputSummary).some(n => n > 0);

    /** 模型广场中匹配当前能力类型（category）的模型选项（与 NodeGenerateArea 一致，由画布根组件经 Context 下发） */
    const marketModels = useCanvasModels();
    const modelOptions = useMemo(
        () =>
            marketModels
                .filter(m => m.category === mode)
                .map(m => ({
                    value: `${m.providerId ?? 'marketplace'}${CHANNEL_MODEL_SEPARATOR}${m.provider}`,
                    name: m.name,
                    channelName: m.providerName ?? m.provider,
                })),
        [marketModels, mode],
    );
    /** 生效模型：未选时回退到模型设置里的默认值；无默认（或已失效）时取列表第一个 */
    const defaultModel = config[DEFAULT_MODEL_KEY[mode]];
    const activeModel =
        (modeConfig as { model: string }).model || (modelOptions.some(o => o.value === defaultModel) ? defaultModel : modelOptions[0]?.value || '');
    /** 触发按钮展示名：优先取下拉选项里的展示名（display_name），兜底取 value 的模型名段 */
    const activeModelName = modelOptions.find(o => o.value === activeModel)?.name ?? modelNameOf(activeModel);

    return (
        /* pointer-events-none：卡片两侧不可见区域不拦截指针，避免重叠时挡住其他节点拖拽（可见部分各自恢复 auto） */
        /* 高度默认由内容撑开（自适应）；用户四角缩放后根容器改为撑满节点框（固定高度） */
        <div
            className="group pointer-events-none relative w-full"
            style={heightFixed ? { height: '100%' } : undefined}
            onPointerEnter={() => setHovered(true)}
            onPointerLeave={() => setHovered(false)}
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
        >
            {/* 四角缩放手柄：悬停/选中时可见（只画角点，不画边框） */}
            <NodeCornerResizer visible={hovered || !!selected} minWidth={400} minHeight={240} />
            {/* 点击展开时节点上方悬浮操作栏（拖拽不展开） */}
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
                {t('genConfigNode.title')}
            </div>

            {/* 卡片主体：填满节点框（节点 style 宽高 = 卡片尺寸） */}
            <div
                className={`pointer-events-auto relative h-full w-full rounded-2xl border-2 bg-card p-4 transition-colors group-hover:border-primary/60 ${
                    selected ? 'border-primary' : 'border-border'
                }`}
            >
                    {/* 标题行：模式切换 */}
                    <div className="mb-3 flex items-center justify-between gap-3">
                        <span className="shrink-0 text-sm font-medium text-foreground">{t('genConfigNode.title')}</span>
                        <div className="nodrag flex gap-0.5 rounded-lg bg-muted p-0.5">
                            {MODE_OPTIONS.map(opt => (
                                <button
                                    key={opt.value}
                                    type="button"
                                    onClick={() => update({ mode: opt.value })}
                                    className={`cursor-pointer rounded-md px-2.5 py-1 text-xs transition-colors ${
                                        mode === opt.value ? 'bg-popover text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
                                    }`}
                                >
                                    {t(opt.labelKey)}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* 输入资产统计 + 组装提示词入口 */}
                    <div className="mb-3 flex flex-wrap items-center gap-1.5">
                        <span className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11px] text-muted-foreground">
                            {t('genConfigNode.badgePrompt', { count: inputSummary.text })}
                        </span>
                        <span className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11px] text-muted-foreground">
                            {t('genConfigNode.badgeImage', { count: inputSummary.image })}
                        </span>
                        <span className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11px] text-muted-foreground">
                            {t('genConfigNode.badgeVideo', { count: inputSummary.video })}
                        </span>
                        {/* <span className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11px] text-muted-foreground">
                            {t('genConfigNode.badgeAudio', { count: inputSummary.audio })}
                        </span> */}
                        <button
                            type="button"
                            onClick={() => setComposerOpen(v => !v)}
                            className={`nodrag inline-flex h-7 cursor-pointer items-center gap-1 rounded-md border px-2 text-[11px] transition-colors ${
                                composerOpen
                                    ? 'border-primary bg-primary/10 text-primary'
                                    : 'border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                            }`}
                        >
                            <SlidersHorizontal className="h-3.5 w-3.5" />
                            {t('genConfigNode.composePrompt')}
                        </button>
                    </div>

                    {/* 模型选择 + 参数设置 */}
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                        {/* 模型下拉：模型广场中匹配当前能力的模型 */}
                        <div className="relative">
                            <button
                                type="button"
                                onClick={() => setModelOpen(v => !v)}
                                className="nodrag flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-popover px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-accent"
                            >
                                <Cpu className="h-3.5 w-3.5 text-muted-foreground" />
                                <span className="max-w-32 truncate">{activeModel ? activeModelName : t('genConfigNode.selectModel')}</span>
                                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                            </button>
                            {modelOpen && (
                                <>
                                    <div className="fixed inset-0 z-40" onClick={() => setModelOpen(false)} />
                                    <div className="nowheel absolute top-[calc(100%+8px)] left-0 z-50 max-h-72 w-56 overflow-y-auto rounded-xl border border-border bg-popover p-1 shadow-card">
                                        {modelOptions.length === 0 ? (
                                            <div className="px-3 py-2 text-xs text-muted-foreground">{t('genConfigNode.noModel')}</div>
                                        ) : (
                                            modelOptions.map(opt => (
                                                <button
                                                    key={opt.value}
                                                    type="button"
                                                    onClick={() => {
                                                        updateModeConfig({ model: opt.value });
                                                        setModelOpen(false);
                                                    }}
                                                    className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-left transition-colors hover:bg-accent"
                                                >
                                                    <span className="min-w-0 truncate text-xs text-foreground">
                                                        {opt.name}
                                                    </span>
                                                    {opt.value === activeModel && <Check className="h-3.5 w-3.5 shrink-0 text-primary" />}
                                                </button>
                                            ))
                                        )}
                                    </div>
                                </>
                            )}
                        </div>

                        {/* API 密钥下拉：生成请求以所选密钥作为 Bearer Token（随生成下发给结果节点） */}
                        <ApiKeySelect value={data.apiKeyId} onChange={v => update({ apiKeyId: v })} placement="down" />

                        {/* 参数设置 */}
                        <div className="relative">
                            <button
                                type="button"
                                onClick={() => setSettingsOpen(v => !v)}
                                className="nodrag flex cursor-pointer items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent"
                            >
                                <SlidersHorizontal className="h-3.5 w-3.5" />
                                {settingsSummary}
                            </button>
                            {settingsOpen && (
                                <>
                                    <div className="fixed inset-0 z-40" onClick={() => setSettingsOpen(false)} />
                                    <div className="absolute top-[calc(100%+8px)] left-0 z-50 w-80 rounded-2xl border border-border bg-popover p-4 shadow-card">
                                        <div className="text-sm font-medium text-popover-foreground">{settingsTitle}</div>
                                        <div className="nowheel mt-1 -mr-3 max-h-72 overflow-y-auto pr-3">
                                            {mode === 'image' ? (
                                                <ImageNodeSettings
                                                    data={{ ...(modeConfig as GenConfigNodeData['image']), prompt: '', imageUrl: '' } as ImageNodeData}
                                                    update={updateModeConfig as (patch: Partial<ImageNodeData>) => void}
                                                />
                                            ) : mode === 'text' ? (
                                                <TextNodeSettings
                                                    data={{ ...(modeConfig as GenConfigNodeData['text']), prompt: '', text: '' } as TextNodeData}
                                                    update={updateModeConfig as (patch: Partial<TextNodeData>) => void}
                                                />
                                            ) : mode === 'video' ? (
                                                <VideoNodeSettings
                                                    data={{ ...(modeConfig as GenConfigNodeData['video']), prompt: '', videoUrl: '' } as VideoNodeData}
                                                    update={updateModeConfig as (patch: Partial<VideoNodeData>) => void}
                                                />
                                            ) : null}
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    {/* 开始生成按钮：只创建结果节点+连线，请求与 loading 由结果节点自身承担 */}
                    <button
                        type="button"
                        onClick={handleSpawn}
                        disabled={!data.prompt.trim() && !hasAnyInput}
                        className="nodrag flex h-10 w-full cursor-pointer items-center justify-center gap-1.5 rounded-lg bg-primary text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        <Play className="h-4 w-4" />
                        {t('genConfigNode.startGenerate')}
                    </button>

                    {/* 连接点：左入右出（放在卡片内部，top 50% 始终对齐卡片中间，不受下方组装提示词面板撑高影响） */}
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

            {/* 组装提示词编辑区：@ 引用已连接资产 */}
            {composerOpen && (
                <PromptComposer value={data.prompt} inputs={inputs} onChange={v => update({ prompt: v })} onClose={() => setComposerOpen(false)} />
            )}
        </div>
    );
}

/* ---------------- 组装提示词编辑区（@ 引用已连接资产） ---------------- */

function PromptComposer({
    value,
    inputs,
    onChange,
    onClose,
}: {
    value: string;
    inputs: UpstreamInput[];
    onChange: (v: string) => void;
    onClose: () => void;
}) {
    const { t } = useTranslation("canvas");
    const [mentionOpen, setMentionOpen] = useState(false);
    const [mentionQuery, setMentionQuery] = useState('');
    const [activeIndex, setActiveIndex] = useState(0);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const candidates = useMemo(() => {
        const q = mentionQuery.trim().toLowerCase();
        if (!q) return inputs;
        return inputs.filter(i => `${i.title} ${i.text ?? ''}`.toLowerCase().includes(q));
    }, [inputs, mentionQuery]);

    /** 输入中检测 @ 触发引用菜单（取光标前最近的 @ 片段） */
    const syncMention = () => {
        const ta = textareaRef.current;
        if (!ta) return;
        const before = ta.value.slice(0, ta.selectionStart ?? ta.value.length);
        const match = /@([^\s@]*)$/.exec(before);
        if (!match || !inputs.length) {
            setMentionOpen(false);
            return;
        }
        setMentionQuery(match[1] ?? '');
        setActiveIndex(0);
        setMentionOpen(true);
    };

    /** 选中引用：替换 @ 查询片段为 @[node:ID] token */
    const insertReference = (input: UpstreamInput) => {
        const ta = textareaRef.current;
        if (!ta) return;
        const start = ta.selectionStart ?? ta.value.length;
        const before = ta.value.slice(0, start);
        const after = ta.value.slice(start);
        const match = /@([^\s@]*)$/.exec(before);
        const token = `@[node:${input.nodeId}] `;
        const next = (match ? before.slice(0, before.length - match[0].length) : before) + token + after;
        onChange(next);
        setMentionOpen(false);
        requestAnimationFrame(() => {
            const caret = (match ? before.length - match[0].length : before.length) + token.length;
            ta.focus();
            ta.setSelectionRange(caret, caret);
        });
    };

    /** 键盘导航：上下选择，回车插入，Esc 关闭 */
    const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        e.stopPropagation();
        if (!mentionOpen || !candidates.length) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActiveIndex(i => (i + 1) % candidates.length);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActiveIndex(i => (i - 1 + candidates.length) % candidates.length);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            insertReference(candidates[Math.min(activeIndex, candidates.length - 1)]);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            setMentionOpen(false);
        }
    };

    return (
        <div className="nodrag pointer-events-auto mt-3 w-160 rounded-2xl border border-border bg-popover p-4 shadow-card">
            <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-baseline gap-2">
                    <span className="shrink-0 text-sm font-medium text-popover-foreground">{t('genConfigNode.composePrompt')}</span>
                    <span className="truncate text-[11px] text-muted-foreground">{t('genConfigNode.composerHint')}</span>
                </div>
                <button
                    type="button"
                    aria-label={t('common.close')}
                    onClick={onClose}
                    className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                    <X className="h-3.5 w-3.5" />
                </button>
            </div>
            <div className="relative">
                <textarea
                    ref={textareaRef}
                    value={value}
                    onChange={e => {
                        onChange(e.target.value);
                        requestAnimationFrame(syncMention);
                    }}
                    onKeyDown={onKeyDown}
                    onKeyUp={syncMention}
                    onClick={syncMention}
                    placeholder={inputs.length ? t('genConfigNode.composerPlaceholder') : t('genConfigNode.composerPlaceholderEmpty')}
                    rows={6}
                    className="nowheel w-full resize-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
                />
                {mentionOpen && candidates.length > 0 && (
                    <div className="nowheel absolute bottom-[calc(100%+6px)] left-0 z-50 max-h-56 w-64 overflow-y-auto rounded-xl border border-border bg-popover p-1 shadow-card">
                        {candidates.map((input, index) => (
                            <button
                                key={input.nodeId}
                                type="button"
                                onMouseDown={e => {
                                    e.preventDefault();
                                    insertReference(input);
                                }}
                                className={`flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors ${
                                    index === activeIndex ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-accent'
                                }`}
                            >
                                <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{input.title}</span>
                                <span className="min-w-0 flex-1 truncate">{input.text || input.title}</span>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
