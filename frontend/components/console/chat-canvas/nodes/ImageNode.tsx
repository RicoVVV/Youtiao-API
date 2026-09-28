"use client";
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from "react-i18next";
import { Handle, Position, useReactFlow } from '@xyflow/react';
import type { Node, NodeProps } from '@xyflow/react';
import { Info, Trash2, Upload, Download, Image as ImageIcon, Copy, Star, ChevronDown, ChevronRight } from 'lucide-react';
import { useCanvasApiKeys, useCanvasModels } from '../models-context';
import { createNodeGenerateController, generateNodeContent, isGenerateCancel } from '../api/generate';
import NodeGenerateArea from './shared/NodeGenerateArea';
import NodeCornerResizer from './shared/NodeCornerResizer';
import NodeGenerateOverlay from './shared/NodeGenerateOverlay';
import ImageNodeSettings from './settings/ImageNodeSettings';
import { useNodeClickExpand } from './shared/useNodeClickExpand';
import { useUpstreamImageUrls } from './shared/useUpstreamImageUrls';
import { downloadResource } from './shared/downloadResource';

export interface ImageNodeData extends Record<string, unknown> {
    /** 当前展示的图片地址（主图；上传/生成结果），空则显示占位 */
    imageUrl?: string;
    /** 一次生成得到的全部图片地址（含主图），多张时右上角可展开 */
    imageUrls?: string[];
    /** 输入区提示词 */
    prompt: string;
    /** 生成参考图（生成配置节点下发的快照；生成时还会合并直接连入的上游图片节点） */
    referenceImages?: string[];
    /** 选中的模型（`供应商ID::原始模型名`） */
    model: string;
    /** 选中的 API 密钥 id（空则生成时取密钥列表第一个） */
    apiKeyId?: string;
    /** 宽高比标签（auto 表示由模型决定） */
    ratio: string;
    /** 生成尺寸 */
    width: number;
    height: number;
    /** 尺寸按 16 倍数对齐 */
    align16: boolean;
    /** 透明背景（仅部分模型可用） */
    transparent: boolean;
    /** 生成张数 */
    count: number;
    /** 生成配置节点下发的自动生成标记：节点创建后由本节点自身发起一次生成（随即清除） */
    autoGenerate?: boolean;
}

export type ImageFlowNode = Node<ImageNodeData, 'imageNode'>;

export default function ImageNode({ id, data, selected, dragging }: NodeProps<Node<ImageNodeData, 'imageNode'>>) {
    const { t } = useTranslation("canvas");
    const { updateNodeData, deleteElements, setNodes, getNode } = useReactFlow();
    const fileInputRef = useRef<HTMLInputElement>(null);
    // 悬停态：悬停/选中时显示四角缩放手柄
    const [hovered, setHovered] = useState(false);
    // 点击展开态：仅真实点击（非拖拽）时显示操作栏与生成区
    const { expanded, onPointerDown, onPointerUp } = useNodeClickExpand(selected, dragging);
    // 多图展开态：右上角数量按钮切换
    const [galleryOpen, setGalleryOpen] = useState(false);

    const update = (patch: Partial<ImageNodeData>) => updateNodeData(id, patch);

    const apiKeys = useCanvasApiKeys();
    const marketModels = useCanvasModels();
    const controllerRef = useRef<ReturnType<typeof createNodeGenerateController> | null>(null);
    if (!controllerRef.current) controllerRef.current = createNodeGenerateController();
    const [isRunning, setIsRunning] = useState(false);
    const [generateError, setGenerateError] = useState('');
    // 直接连入的上游图片节点：与配置节点下发的参考图快照合并后作为多参考图提交
    const upstreamImageUrls = useUpstreamImageUrls(id);

    /** 发送/停止：按提示词生成图片并回写节点（结果取首条） */
    const handleSend = () => {
        controllerRef.current?.toggle(id, async signal => {
            setIsRunning(true);
            setGenerateError('');
            try {
                const referenceImages = [...new Set([...(data.referenceImages ?? []), ...upstreamImageUrls])];
                const result = await generateNodeContent({ capability: 'image', data: { ...data, referenceImages }, models: marketModels, apiKeys, signal });
                // 回写全部结果：imageUrl 为主图（默认首张），imageUrls 为整批
                if (result.capability === 'image') update({ imageUrl: result.url, imageUrls: result.urls });
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

    /** 本地图片上传为 dataURL（生成逻辑接入前的图片来源） */
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = '';
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => update({ imageUrl: reader.result as string, imageUrls: [reader.result as string] });
        reader.readAsDataURL(file);
    };

    // 一次生成得到的全部图片（无多图时回退到当前图）
    const imageUrls = data.imageUrls?.length ? data.imageUrls : data.imageUrl ? [data.imageUrl] : [];
    // 展开面板中展示的其余图片：主图已在节点上显示，不再重复
    const galleryUrls = imageUrls.filter(url => url !== data.imageUrl);
    /** 设为主图：当前节点默认展示 */
    const setPrimary = (url: string) => update({ imageUrl: url });

    /** 创建副本：以该图在右下方新建一个图片节点（不连线） */
    const duplicateAsNode = (url: string) => {
        const self = getNode(id);
        if (!self) return;
        const w = self.measured?.width ?? (self.style?.width as number) ?? 360;
        const h = self.measured?.height ?? (self.style?.height as number) ?? 240;
        const newId = `image-copy-${Date.now()}`;
        setNodes(nds => [
            ...nds,
            {
                id: newId,
                type: 'imageNode',
                position: { x: self.position.x + w + 40, y: self.position.y + 40 },
                style: { width: w, height: h },
                data: { ...data, imageUrl: url, imageUrls: [url] },
            } as never,
        ]);
    };

    /** 头部操作：删除、上传与下载有逻辑，其余先只展示 */
    const headerActions = [
        // { key: 'info', label: '信息', icon: <Info className="h-4 w-4" /> },
        { key: 'delete', label: t('common.delete'), icon: <Trash2 className="h-4 w-4" />, onClick: () => void deleteElements({ nodes: [{ id }] }) },
        { key: 'upload', label: t('common.upload'), icon: <Upload className="h-4 w-4" />, onClick: () => fileInputRef.current?.click() },
        ...(data.imageUrl ? [{ key: 'download', label: t('common.download'), icon: <Download className="h-4 w-4" />, onClick: () => downloadResource(data.imageUrl!, 'image.png') }] : []),
    ];

    /** 展开面板中每张图的操作 */
    const galleryActions = (url: string) => [
        { key: 'download', label: t('common.download'), icon: <Download className="h-3.5 w-3.5" />, onClick: () => downloadResource(url, 'image.png') },
        { key: 'duplicate', label: t('imageNode.duplicate'), icon: <Copy className="h-3.5 w-3.5" />, onClick: () => duplicateAsNode(url) },
        { key: 'primary', label: t('imageNode.setPrimary'), icon: <Star className="h-3.5 w-3.5" />, onClick: () => setPrimary(url) },
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
            <NodeCornerResizer visible={hovered || !!selected} minWidth={200} minHeight={120} />
            <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handleFileChange} />

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
                {t('imageNode.title')}
            </div>

            {/* 卡片主体：填满节点框（节点 style 宽高 = 卡片尺寸），双击上传图片 */}
            <div
                className={`pointer-events-auto relative h-full w-full rounded-2xl border-2 bg-card transition-colors group-hover:border-primary/60 ${
                    selected ? 'border-primary' : 'border-border'
                }`}
                onDoubleClick={() => fileInputRef.current?.click()}
            >
                    {/* 内容层单独裁剪圆角，避免覆盖两侧的连接点 */}
                    <div className="absolute inset-0 overflow-hidden rounded-2xl">
                        {data.imageUrl ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={data.imageUrl} alt="" className="h-full w-full object-cover" />
                        ) : (
                            <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-muted-foreground">
                                <ImageIcon className="h-8 w-8" />
                                <span className="text-sm">{t('imageNode.empty')}</span>
                            </div>
                        )}
                    </div>

                    {/* 生成状态浮层：生成中 loading + 进度，失败报错 + 重试 */}
                    <NodeGenerateOverlay isRunning={isRunning} error={generateError} onRetry={handleSend} />

                    {/* 多张结果时右上角数量按钮：点击展开/收起全部图片 */}
                    {imageUrls.length > 1 && (
                        <button
                            type="button"
                            onClick={e => {
                                e.stopPropagation();
                                setGalleryOpen(v => !v);
                            }}
                            className="nodrag absolute top-2 right-2 z-10 flex cursor-pointer items-center gap-1 rounded-full border border-border bg-popover/95 px-2.5 py-1 text-xs text-foreground shadow-card backdrop-blur transition-colors hover:bg-accent"
                        >
                            {t('common.countImages', { count: imageUrls.length })}
                            {galleryOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                        </button>
                    )}

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

            {/* 多图展开面板：从卡片右侧横向展开其余生成结果（主图已在节点上展示，不重复），每张图带操作 */}
            {galleryOpen && galleryUrls.length > 0 && (
                <div className="nodrag pointer-events-auto absolute top-0 left-full z-20 ml-3 flex items-start gap-3">
                    {galleryUrls.map((url, i) => (
                        <div
                            key={i}
                            className="relative h-60 w-90 shrink-0 overflow-hidden rounded-2xl border-2 border-border bg-card shadow-card"
                        >
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={url} alt="" className="h-full w-full object-cover" />
                            <div className="absolute top-2 left-2 flex flex-wrap items-center gap-1.5">
                                {galleryActions(url).map(action => (
                                    <button
                                        key={action.key}
                                        type="button"
                                        onClick={action.onClick}
                                        className="flex cursor-pointer items-center gap-1 rounded-full border border-border bg-popover/95 px-2.5 py-1 text-xs text-foreground shadow-card backdrop-blur transition-colors hover:bg-accent"
                                    >
                                        {action.icon}
                                        {action.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* 点击展开时的生成区域：绝对定位在节点下方，不占节点框高度 */}
            {expanded && (
                <div className="absolute top-full left-1/2 z-10 -translate-x-1/2">
                <NodeGenerateArea
                    prompt={data.prompt}
                    promptPlaceholder={t('imageNode.inputPlaceholder')}
                    onPromptChange={v => update({ prompt: v })}
                    capability="image"
                    model={data.model}
                    onModelChange={v => update({ model: v })}
                    apiKeyId={data.apiKeyId}
                    onApiKeyChange={v => update({ apiKeyId: v })}
                    showModelIcon
                    showPromptLibrary
                    settingsSummary={t('common.summaryImage', { size: data.ratio, count: data.count })}
                    settingsTitle={t('common.settingsTitleImage')}
                    settingsPanelClassName="w-80"
                    settingsScrollable
                    settingsContent={<ImageNodeSettings data={data} update={update} />}
                    onSend={handleSend}
                    isRunning={isRunning}
                />
                </div>
            )}
        </div>
    );
}
