"use client";
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from "react-i18next";
import { Handle, Position, useReactFlow } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { Info, Trash2, Pencil, Upload, Download, Video as VideoIcon } from 'lucide-react';
import { useCanvasApiKeys, useCanvasModels } from '../models-context';
import { createNodeGenerateController, generateNodeContent, isGenerateCancel, resumeVideoTask } from '../api/generate';
import NodeGenerateArea from './shared/NodeGenerateArea';
import NodeCornerResizer from './shared/NodeCornerResizer';
import NodeGenerateOverlay from './shared/NodeGenerateOverlay';
import VideoNodeSettings, { videoRatioSummaryLabel } from './settings/VideoNodeSettings';
import { useNodeClickExpand } from './shared/useNodeClickExpand';
import { useUpstreamImageUrls } from './shared/useUpstreamImageUrls';
import { downloadResource } from './shared/downloadResource';

export interface VideoNodeData extends Record<string, unknown> {
    /** 视频地址（上传/生成结果），空则显示占位 */
    videoUrl?: string;
    /** 输入区提示词 */
    prompt: string;
    /** 生成参考图（生成配置节点下发的快照；生成时还会合并直接连入的上游图片节点） */
    referenceImages?: string[];
    /** 选中的模型（`供应商ID::原始模型名`） */
    model: string;
    /** 选中的 API 密钥 id（空则生成时取密钥列表第一个） */
    apiKeyId?: string;
    /** 尺寸标签（auto 表示由模型决定） */
    ratio: string;
    /** 生成尺寸 */
    width: number;
    height: number;
    /** 视频时长（秒） */
    seconds: number;
    /** 生成配置节点下发的自动生成标记：节点创建后由本节点自身发起一次生成（随即清除） */
    autoGenerate?: boolean;
    /** 进行中的视频生成任务 ID：随节点 data 持久化，离开画布中断轮询后凭此恢复查询 */
    videoTaskId?: string;
}

export type VideoFlowNode = Node<VideoNodeData, 'videoNode'>;

export default function VideoNode({ id, data, selected, dragging }: NodeProps<Node<VideoNodeData, 'videoNode'>>) {
    const { t } = useTranslation("canvas");
    const { updateNodeData, deleteElements } = useReactFlow();
    const fileInputRef = useRef<HTMLInputElement>(null);
    // 悬停态：悬停/选中时显示四角缩放手柄
    const [hovered, setHovered] = useState(false);
    // 点击展开态：仅真实点击（非拖拽）时显示操作栏与生成区
    const { expanded, onPointerDown, onPointerUp } = useNodeClickExpand(selected, dragging);

    const update = (patch: Partial<VideoNodeData>) => updateNodeData(id, patch);

    const apiKeys = useCanvasApiKeys();
    const marketModels = useCanvasModels();
    const controllerRef = useRef<ReturnType<typeof createNodeGenerateController> | null>(null);
    if (!controllerRef.current) controllerRef.current = createNodeGenerateController();
    const [isRunning, setIsRunning] = useState(false);
    const [generateError, setGenerateError] = useState('');
    // 直接连入的上游图片节点：与配置节点下发的参考图快照合并后作为多参考图提交
    const upstreamImageUrls = useUpstreamImageUrls(id);

    // loading 由本地运行态 + 持久化的未完成任务共同推导：重进画布恢复轮询时
    // 卸载 cleanup 的 finally 可能把 isRunning 覆盖回 false，凭任务 ID 兜底
    const generating = isRunning || (!!data.videoTaskId && !data.videoUrl);

    // 卸载标记：区分"用户点击停止"与"离开画布中断"，前者清除任务 ID，后者保留以便恢复
    const unmountedRef = useRef(false);

    /** 发送/停止：按提示词生成视频（创建任务后轮询）并回写节点；任务 ID 持久化到节点 data */
    const handleSend = () => {
        controllerRef.current?.toggle(id, async signal => {
            setIsRunning(true);
            setGenerateError('');
            try {
                const referenceImages = [...new Set([...(data.referenceImages ?? []), ...upstreamImageUrls])];
                const result = await generateNodeContent({
                    capability: 'video',
                    data: { ...data, referenceImages },
                    models: marketModels,
                    apiKeys,
                    signal,
                    onVideoTaskId: taskId => update({ videoTaskId: taskId }),
                });
                if (result.capability === 'video') update({ videoUrl: result.url, videoTaskId: undefined });
            } catch (error) {
                // 取消：用户主动停止时放弃任务（离开画布的卸载中断保留任务 ID，重进时恢复）
                if (isGenerateCancel(error)) {
                    if (!unmountedRef.current) update({ videoTaskId: undefined });
                    return;
                }
                // 失败的任务不可恢复：清除任务 ID，重试将创建新任务
                update({ videoTaskId: undefined });
                setGenerateError(error instanceof Error ? error.message : t('common.generateFailed'));
            } finally {
                setIsRunning(false);
            }
        });
    };

    // 离开画布/切换会话（节点卸载）：终止本轮轮询，任务 ID 已存节点 data，重进时凭此恢复
    useEffect(() => {
        unmountedRef.current = false;
        return () => {
            unmountedRef.current = true;
            // 延迟中断：开发环境 StrictMode 双挂载时 setup 会立即复位标记，避免误中断刚发起的请求；
            // 真实卸载时标记保持 true，下一个宏任务执行中断
            setTimeout(() => {
                if (unmountedRef.current) controllerRef.current?.stop(id);
            }, 0);
        };
    }, [id]);

    // 进入画布：存在未完成的任务且尚无结果时，按任务 ID 恢复轮询查询生成结果
    useEffect(() => {
        if (!data.videoTaskId || data.videoUrl) return;
        const taskId = data.videoTaskId;
        // run 内部按节点去重：自动生成等场景已在运行中时直接忽略，避免重复轮询
        void controllerRef.current?.run(id, async signal => {
            setIsRunning(true);
            setGenerateError('');
            try {
                const url = await resumeVideoTask({ taskId, apiKeys, apiKeyId: data.apiKeyId, signal });
                update({ videoUrl: url, videoTaskId: undefined });
            } catch (error) {
                // 卸载中断保留任务 ID；失败则清除任务 ID 并提示
                if (isGenerateCancel(error)) return;
                update({ videoTaskId: undefined });
                setGenerateError(error instanceof Error ? error.message : t('common.generateFailed'));
            } finally {
                setIsRunning(false);
            }
        });
        // 仅在任务 ID/结果变化时尝试恢复；config/update 随渲染重建，不作为依赖
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [id, data.videoTaskId, data.videoUrl]);

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

    /** 本地视频上传为 dataURL（生成逻辑接入前的视频来源） */
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => update({ videoUrl: reader.result as string });
        reader.readAsDataURL(file);
    };

    /** 头部操作：删除、上传与下载有逻辑，其余先只展示 */
    const headerActions = [
        // { key: 'info', label: '信息', icon: <Info className="h-4 w-4" /> },
        { key: 'delete', label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => void deleteElements({ nodes: [{ id }] }) },
        { key: 'edit', label: t('common.edit'), icon: <Pencil className="h-4 w-4" /> },
        { key: 'upload', label: t('common.upload'), icon: <Upload className="h-4 w-4" />, onClick: () => fileInputRef.current?.click() },
        ...(data.videoUrl ? [{ key: 'download', label: t('common.download'), icon: <Download className="h-4 w-4" />, onClick: () => downloadResource(data.videoUrl!, 'video.mp4') }] : []),
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
            <NodeCornerResizer visible={hovered || !!selected} minWidth={240} minHeight={140} />
            <input ref={fileInputRef} type="file" accept="video/*" className="hidden" onChange={handleFileChange} />

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
                {t('videoNode.title')}
            </div>

            {/* 卡片主体：填满节点框（节点 style 宽高 = 卡片尺寸），双击上传视频 */}
            <div
                className={`pointer-events-auto relative h-full w-full rounded-2xl border-2 bg-card transition-colors group-hover:border-primary/60 ${
                    selected ? 'border-primary' : 'border-border'
                }`}
                onDoubleClick={() => fileInputRef.current?.click()}
            >
                    {/* 内容层单独裁剪圆角，避免覆盖两侧的连接点 */}
                    <div className="absolute inset-0 overflow-hidden rounded-2xl">
                        {data.videoUrl ? (
                            <video src={data.videoUrl} controls className="h-full w-full object-cover" />
                        ) : (
                            <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-muted-foreground">
                                <VideoIcon className="h-8 w-8" />
                                <span className="text-sm">{t('videoNode.empty')}</span>
                            </div>
                        )}
                    </div>

                    {/* 生成状态浮层：生成中 loading + 进度，失败报错 + 重试 */}
                    <NodeGenerateOverlay isRunning={generating} error={generateError} onRetry={handleSend} />

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
                    promptPlaceholder={t('videoNode.inputPlaceholder')}
                    onPromptChange={v => update({ prompt: v })}
                    capability="video"
                    model={data.model}
                    onModelChange={v => update({ model: v })}
                    apiKeyId={data.apiKeyId}
                    onApiKeyChange={v => update({ apiKeyId: v })}
                    showModelIcon
                    showPromptLibrary
                    settingsSummary={t('common.summaryVideo', { ratio: videoRatioSummaryLabel(data.ratio, data.width, data.height, t), width: data.width, height: data.height, seconds: data.seconds })}
                    settingsTitle={t('common.settingsTitleVideo')}
                    settingsPanelClassName="nowheel max-h-[70vh] w-80 overflow-y-auto"
                    settingsContent={<VideoNodeSettings data={data} update={update} />}
                    onSend={handleSend}
                    isRunning={generating}
                />
                </div>
            )}
        </div>
    );
}
