"use client";
import { useState, type ReactNode } from 'react';
import { Maximize2, BookOpen, Cpu, ChevronDown, SlidersHorizontal, ArrowUp, Check, Square } from 'lucide-react';
import { CHANNEL_MODEL_SEPARATOR, useCanvasConfigStore, type ModelCapability } from '@/stores/use-canvas-config-store';
import { useCanvasModels } from '../../models-context';
import ApiKeySelect from './ApiKeySelect';
import PromptEditModal from './PromptEditModal';

interface NodeGenerateAreaProps {
    /** 提示词内容与更新 */
    prompt: string;
    promptPlaceholder: string;
    onPromptChange: (v: string) => void;
    /** 节点能力类型：决定可选模型列表与默认模型来源 */
    capability: ModelCapability;
    /** 当前选中的模型（`供应商ID::原始模型名`），空则取默认模型 */
    model: string;
    onModelChange: (v: string) => void;
    /** 当前选中的 API 密钥 id，空则默认取密钥列表第一个 */
    apiKeyId?: string;
    onApiKeyChange: (v: string) => void;
    /** 模型按钮是否显示图标（文本节点无图标） */
    showModelIcon?: boolean;
    /** 是否显示提示词库入口（文本节点无） */
    showPromptLibrary?: boolean;
    /** 设置按钮摘要文案，如 `1:1 · 3 张`；不传则不显示设置按钮 */
    settingsSummary?: string;
    /** 设置弹层标题 */
    settingsTitle?: string;
    /** 设置弹层面板类名（宽度/滚动等），默认 w-80 */
    settingsPanelClassName?: string;
    /** 设置内容是否包裹限高滚动容器（标题固定，内容滚动） */
    settingsScrollable?: boolean;
    /** 设置弹层内容（各节点的参数区）；不传则不显示设置按钮 */
    settingsContent?: ReactNode;
    /** 发送/停止生成 */
    onSend: () => void;
    /** 是否正在生成（按钮变为停止态） */
    isRunning?: boolean;
    /** 覆盖发送按钮禁用逻辑（如生成配置节点：有引用输入时允许空提示词）；不传则默认提示词为空禁用 */
    sendDisabled?: boolean;
}

/** 各能力对应的默认模型配置键 */
const DEFAULT_MODEL_KEY = {
    image: 'imageModel',
    video: 'videoModel',
    text: 'textModel',
    audio: 'audioModel',
} as const;

/** 从 `渠道ID::模型名` 中取模型名用于展示 */
const modelNameOf = (value: string) => value.split(CHANNEL_MODEL_SEPARATOR).pop() || value;

/** 节点选中时展开的生成区域：提示词输入 + 工具栏（放大编辑/提示词库/模型/参数设置/发送） */
export default function NodeGenerateArea({
    prompt,
    promptPlaceholder,
    onPromptChange,
    capability,
    model,
    onModelChange,
    apiKeyId,
    onApiKeyChange,
    showModelIcon = false,
    showPromptLibrary = false,
    settingsSummary,
    settingsTitle,
    settingsPanelClassName,
    settingsScrollable = false,
    settingsContent,
    onSend,
    isRunning = false,
    sendDisabled,
}: NodeGenerateAreaProps) {
    const [modalOpen, setModalOpen] = useState(false);
    const [modelOpen, setModelOpen] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);

    const config = useCanvasConfigStore(s => s.config);

    /** 模型广场数据（画布根组件加载后经 Context 下发） */
    const marketModels = useCanvasModels();

    /** 模型广场中匹配当前能力类型（category）的模型选项；value 用原始模型名（provider 字段），生成请求直接取该段 */
    const modelOptions = marketModels
        .filter(m => m.category === capability)
        .map(m => ({
            value: `${m.providerId ?? 'marketplace'}${CHANNEL_MODEL_SEPARATOR}${m.provider}`,
            name: m.name,
            channelName: m.providerName ?? m.provider,
        }));
    /** 生效模型：未选时回退到模型设置里的默认值；无默认（或已失效）时取列表第一个 */
    const defaultModel = config[DEFAULT_MODEL_KEY[capability]];
    const activeModel = model || (modelOptions.some(o => o.value === defaultModel) ? defaultModel : modelOptions[0]?.value || '');
    /** 触发按钮展示名：优先取下拉选项里的展示名（display_name），兜底取 value 的模型名段 */
    const activeModelName = modelOptions.find(o => o.value === activeModel)?.name ?? modelNameOf(activeModel);

    return (
        /* pointer-events-auto：节点根容器为 pointer-events-none（不挡下层节点），这里恢复交互 */
        <div className="nodrag pointer-events-auto mt-3 w-160 rounded-2xl border border-border bg-popover p-4 shadow-card">
            <textarea
                value={prompt}
                onChange={e => onPromptChange(e.target.value)}
                placeholder={promptPlaceholder}
                rows={6}
                className="nowheel w-full resize-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            />
            <div className="relative mt-2 flex items-center gap-2">
                {/* 放大编辑 */}
                <button
                    type="button"
                    aria-label="放大编辑"
                    onClick={() => setModalOpen(true)}
                    className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent"
                >
                    <Maximize2 className="h-4 w-4" />
                </button>

                {/* 模型下拉：聚合所有渠道中匹配当前能力的模型 */}
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => setModelOpen(v => !v)}
                        className="flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-popover px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-accent"
                    >
                        {showModelIcon && <Cpu className="h-3.5 w-3.5 text-muted-foreground" />}
                        <span className="max-w-32 truncate">{activeModel ? activeModelName : '选择模型'}</span>
                        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                    {modelOpen && (
                        <>
                            <div className="fixed inset-0 z-40" onClick={() => setModelOpen(false)} />
                            <div className="nowheel absolute bottom-[calc(100%+8px)] left-0 z-50 max-h-72 w-56 overflow-y-auto rounded-xl border border-border bg-popover p-1 shadow-card">
                                {modelOptions.length === 0 ? (
                                    <div className="px-3 py-2 text-xs text-muted-foreground">暂无可用模型</div>
                                ) : (
                                    modelOptions.map(opt => (
                                        <button
                                            key={opt.value}
                                            type="button"
                                            onClick={() => {
                                                onModelChange(opt.value);
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

                {/* API 密钥下拉：生成请求以所选密钥作为 Bearer Token */}
                <ApiKeySelect value={apiKeyId} onChange={onApiKeyChange} />

                {/* 参数设置（未提供设置内容时不显示） */}
                {settingsContent && (
                <div className="relative">
                    <button
                        type="button"
                        onClick={() => setSettingsOpen(v => !v)}
                        className="flex cursor-pointer items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent"
                    >
                        <SlidersHorizontal className="h-3.5 w-3.5" />
                        {settingsSummary}
                    </button>
                    {settingsOpen && (
                        <>
                            <div className="fixed inset-0 z-40" onClick={() => setSettingsOpen(false)} />
                            <div
                                className={`absolute bottom-[calc(100%+8px)] left-0 z-50 rounded-2xl border border-border bg-popover p-4 shadow-card ${settingsPanelClassName ?? 'w-80'}`}
                            >
                                <div className="text-sm font-medium text-popover-foreground">{settingsTitle}</div>
                                {settingsScrollable ? (
                                    /* 设置内容区：限高滚动，标题固定；负边距让滚动条贴近面板边框 */
                                    <div className="nowheel mt-1 -mr-3 max-h-72 overflow-y-auto pr-3">{settingsContent}</div>
                                ) : (
                                    settingsContent
                                )}
                            </div>
                        </>
                    )}
                </div>
                )}

                {/* 发送/停止：未运行时按 sendDisabled（默认提示词为空）禁用，运行中点击停止 */}
                <button
                    type="button"
                    aria-label={isRunning ? '停止生成' : '发送'}
                    onClick={onSend}
                    disabled={!isRunning && (sendDisabled ?? !prompt.trim())}
                    className={`ml-auto flex h-9 w-9 cursor-pointer items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                        isRunning ? 'bg-destructive/10 text-destructive hover:bg-destructive/20' : 'bg-primary text-primary-foreground hover:bg-primary/90'
                    }`}
                >
                    {isRunning ? <Square className="h-3.5 w-3.5 fill-current" /> : <ArrowUp className="h-4 w-4" />}
                </button>
            </div>

            {modalOpen && (
                <PromptEditModal
                    value={prompt}
                    onChange={onPromptChange}
                    onClose={() => setModalOpen(false)}
                    placeholder={promptPlaceholder}
                />
            )}
        </div>
    );
}
