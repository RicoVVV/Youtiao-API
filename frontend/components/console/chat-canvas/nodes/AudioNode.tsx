"use client";
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from "react-i18next";
import { Handle, Position, useReactFlow } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { Info, Trash2, Upload, Download, Music } from 'lucide-react';
import { useCanvasApiKeys, useCanvasModels } from '../models-context';
import { createNodeGenerateController, generateNodeContent, isGenerateCancel } from '../api/generate';
import NodeGenerateArea from './shared/NodeGenerateArea';
import NodeCornerResizer from './shared/NodeCornerResizer';
import NodeGenerateOverlay from './shared/NodeGenerateOverlay';
import AudioNodeSettings from './settings/AudioNodeSettings';
import { useNodeClickExpand } from './shared/useNodeClickExpand';
import { downloadResource } from './shared/downloadResource';

export interface AudioNodeData extends Record<string, unknown> {
    /** 音频地址（上传/生成结果），空则显示占位 */
    audioUrl?: string;
    /** 输入区提示词 */
    prompt: string;
    /** 选中的模型（`供应商ID::原始模型名`） */
    model: string;
    /** 选中的 API 密钥 id（空则生成时取密钥列表第一个） */
    apiKeyId?: string;
    /** 声音 */
    voice: string;
    /** 音频格式 */
    format: string;
    /** 语速倍率 */
    speed: number;
    /** 声音指令（语气/风格描述） */
    instructions: string;
    /** 生成配置节点下发的自动生成标记：节点创建后由本节点自身发起一次生成（随即清除） */
    autoGenerate?: boolean;
}

export type AudioFlowNode = Node<AudioNodeData, 'audioNode'>;

export default function AudioNode({ id, data, selected, dragging }: NodeProps<Node<AudioNodeData, 'audioNode'>>) {
    const { t } = useTranslation("canvas");
    const { updateNodeData, deleteElements } = useReactFlow();
    const fileInputRef = useRef<HTMLInputElement>(null);
    // 悬停态：悬停/选中时显示四角缩放手柄
    const [hovered, setHovered] = useState(false);
    // 点击展开态：仅真实点击（非拖拽）时显示操作栏与生成区
    const { expanded, onPointerDown, onPointerUp } = useNodeClickExpand(selected, dragging);

    const update = (patch: Partial<AudioNodeData>) => updateNodeData(id, patch);

    const apiKeys = useCanvasApiKeys();
    const marketModels = useCanvasModels();
    const controllerRef = useRef<ReturnType<typeof createNodeGenerateController> | null>(null);
    if (!controllerRef.current) controllerRef.current = createNodeGenerateController();
    const [isRunning, setIsRunning] = useState(false);
    const [generateError, setGenerateError] = useState('');

    /** 发送/停止：按提示词合成语音并回写节点 */
    const handleSend = () => {
        controllerRef.current?.toggle(id, async signal => {
            setIsRunning(true);
            setGenerateError('');
            try {
                const result = await generateNodeContent({ capability: 'audio', data, models: marketModels, apiKeys, signal });
                if (result.capability === 'audio') update({ audioUrl: result.url });
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

    /** 本地音频上传为 dataURL（生成逻辑接入前的音频来源） */
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => update({ audioUrl: reader.result as string });
        reader.readAsDataURL(file);
    };

    /** 头部操作：删除、上传与下载有逻辑，其余先只展示 */
    const headerActions = [
        // { key: 'info', label: '信息', icon: <Info className="h-4 w-4" /> },
        { key: 'delete', label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => void deleteElements({ nodes: [{ id }] }) },
        { key: 'upload', label: t('common.upload'), icon: <Upload className="h-4 w-4" />, onClick: () => fileInputRef.current?.click() },
        ...(data.audioUrl ? [{ key: 'download', label: t('common.download'), icon: <Download className="h-4 w-4" />, onClick: () => downloadResource(data.audioUrl!, 'audio.mp3') }] : []),
    ];

    return (
        // 根容器宽度恒定为输入区宽度，选中/拖拽时卡片居中位置不变（避免节点跳动）
        /* pointer-events-none：卡片两侧不可见区域不拦截指针，避免重叠时挡住其他节点拖拽 */
        <div
            className="group pointer-events-none relative h-full w-full"
            onPointerEnter={() => setHovered(true)}
            onPointerLeave={() => setHovered(false)}
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
        >
            {/* 四角缩放手柄：悬停/选中时可见（只画角点，不画边框） */}
            <NodeCornerResizer visible={hovered || !!selected} minWidth={260} minHeight={140} />
            <input ref={fileInputRef} type="file" accept="audio/*" className="hidden" onChange={handleFileChange} />

            {/* 点击展开时节点上方悬浮操作栏：宽度自适应内容，水平居中（拖拽不展开） */}
            {expanded && (
                <div className="nodrag pointer-events-auto absolute -top-16 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1 rounded-full border border-border bg-popover px-2 py-1.5 whitespace-nowrap shadow-card">
                    {headerActions.map(action => (
                        <button
                            key={action.key}
                            type="button"
                            onClick={action.onClick}
                            className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
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
                {t('audioNode.title')}
            </div>

            {/* 卡片主体：填满节点框（节点 style 宽高 = 卡片尺寸），双击上传音频 */}
            <div
                className={`pointer-events-auto relative h-full w-full rounded-2xl border-2 bg-card transition-colors group-hover:border-primary/60 ${
                    selected ? 'border-primary' : 'border-border'
                }`}
                onDoubleClick={() => fileInputRef.current?.click()}
            >
                    {/* 内容层单独裁剪圆角，避免覆盖两侧的连接点 */}
                    <div className="absolute inset-0 overflow-hidden rounded-2xl">
                        {data.audioUrl ? (
                            <div className="flex h-full w-full items-center justify-center px-6">
                                <audio src={data.audioUrl} controls className="w-full" />
                            </div>
                        ) : (
                            <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-muted-foreground">
                                <Music className="h-8 w-8" />
                                <span className="text-sm">{t('audioNode.empty')}</span>
                            </div>
                        )}
                    </div>

                    {/* 生成状态浮层：生成中 loading + 进度，失败报错 + 重试 */}
                    <NodeGenerateOverlay isRunning={isRunning} error={generateError} onRetry={handleSend} />

                    {/* 连接点：左入右出 */}
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

            {/* 点击展开时的生成区域：绝对定位在节点下方，不占节点框高度 */}
            {expanded && (
                <div className="absolute top-full left-1/2 z-10 -translate-x-1/2">
                <NodeGenerateArea
                    prompt={data.prompt}
                    promptPlaceholder={t('audioNode.inputPlaceholder')}
                    onPromptChange={v => update({ prompt: v })}
                    capability="audio"
                    model={data.model}
                    onModelChange={v => update({ model: v })}
                    apiKeyId={data.apiKeyId}
                    onApiKeyChange={v => update({ apiKeyId: v })}
                    showModelIcon
                    showPromptLibrary
                    settingsSummary={t('common.summaryAudio', { voice: data.voice, format: data.format, speed: data.speed })}
                    settingsTitle={t('common.settingsTitleAudio')}
                    settingsPanelClassName="w-80"
                    settingsScrollable
                    settingsContent={<AudioNodeSettings data={data} update={update} />}
                    onSend={handleSend}
                    isRunning={isRunning}
                />
                </div>
            )}
        </div>
    );
}
