"use client";
import { useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
    Hand,
    Undo2,
    Redo2,
    Type,
    Image,
    Video,
    // Music, // 音频入口暂时隐藏
    SlidersHorizontal,
    Group,
    Upload,
    Palette,
    Eraser,
    Info,
    CircleDot,
    Grid2x2,
    Square,
    X,
} from 'lucide-react';

export type GridStyle = 'dots' | 'lines' | 'blank';

interface CanvasToolbarProps {
    gridStyle: GridStyle;
    onGridStyleChange: (style: GridStyle) => void;
    /** 添加类工具点击回调（text/image/video/audio） */
    onAddNode?: (toolKey: string) => void;
    /** 撤销/重做可用态与回调 */
    canUndo?: boolean;
    canRedo?: boolean;
    onUndo?: () => void;
    onRedo?: () => void;
    /** 清空画布（确认后回调） */
    onClearCanvas?: () => void;
    /** 上传文件回调（图片/视频/音频，按类型创建对应节点） */
    onUploadFiles?: (files: File[]) => void;
}

/** 画布网格样式选项（label 为 canvas.json toolbar 下的 i18n key） */
const GRID_OPTIONS: { value: GridStyle; labelKey: string; icon: React.ReactNode }[] = [
    { value: 'dots', labelKey: 'dots', icon: <CircleDot className="h-4 w-4" /> },
    { value: 'lines', labelKey: 'lines', icon: <Grid2x2 className="h-4 w-4" /> },
    { value: 'blank', labelKey: 'blank', icon: <Square className="h-4 w-4" /> },
];

interface ToolButton {
    key: string;
    /** canvas.json toolbar 下的 i18n key（与 key 同名） */
    icon: React.ReactNode;
    /** 禁用态 */
    disabled?: boolean;
    /** 危险操作（清空画布） */
    danger?: boolean;
}

/** 工具分组：组间渲染分隔线（label 取 toolbar.<key>） */
const TOOL_GROUPS: ToolButton[][] = [
    [
        { key: 'move', icon: <Hand className="h-4 w-4" /> },
        { key: 'undo', icon: <Undo2 className="h-4 w-4" /> },
        { key: 'redo', icon: <Redo2 className="h-4 w-4" /> },
    ],
    [
        { key: 'text', icon: <Type className="h-4 w-4" /> },
        { key: 'image', icon: <Image className="h-4 w-4" /> },
        { key: 'video', icon: <Video className="h-4 w-4" /> },
        // 音频节点入口暂时隐藏（恢复时同时把 Music 加回导入）
        // { key: 'audio', icon: <Music className="h-4 w-4" /> },
        { key: 'genConfig', icon: <SlidersHorizontal className="h-4 w-4" /> },
        { key: 'group', icon: <Group className="h-4 w-4" /> },
        { key: 'upload', icon: <Upload className="h-4 w-4" /> },
    ],
    [
        { key: 'appearance', icon: <Palette className="h-4 w-4" /> },
    ],
    [{ key: 'clear', icon: <Eraser className="h-4 w-4" />, danger: true }],
];


/** 画布外观弹层：网格样式 + 图片信息开关 */
function AppearancePanel({
    gridStyle,
    onGridStyleChange,
}: CanvasToolbarProps) {
    const { t } = useTranslation('canvas');
    const [showImageInfo, setShowImageInfo] = useState(false);

    return (
        <div className="nodrag absolute right-0 bottom-[calc(100%+12px)] w-72 rounded-2xl border border-border bg-popover p-4 shadow-card">
            <div className="text-base font-medium text-popover-foreground">{t('toolbar.appearance')}</div>

            <div className="mt-4 text-sm text-muted-foreground">{t('toolbar.gridStyle')}</div>
            <div className="mt-2 flex gap-1 rounded-xl bg-muted p-1">
                {GRID_OPTIONS.map(opt => (
                    <button
                        key={opt.value}
                        type="button"
                        onClick={() => onGridStyleChange(opt.value)}
                        className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-sm transition-colors ${
                            gridStyle === opt.value
                                ? 'bg-popover text-foreground shadow-sm'
                                : 'text-muted-foreground hover:text-foreground'
                        }`}
                    >
                        {opt.icon}
                        {t(`toolbar.${opt.labelKey}`)}
                    </button>
                ))}
            </div>
        </div>
    );
}

/** 清空画布确认弹窗 */
function ClearConfirmModal({ onConfirm, onClose }: { onConfirm: () => void; onClose: () => void }) {
    const { t } = useTranslation('canvas');
    return createPortal(
        <div className="fixed inset-0 z-100 flex items-center justify-center bg-black/50" onClick={onClose}>
            <div
                className="w-[92vw] max-w-md rounded-2xl bg-popover p-6 text-popover-foreground shadow-xl"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex items-center justify-between">
                    <span className="text-lg font-semibold">{t('toolbar.clearTitle')}</span>
                    <button
                        type="button"
                        aria-label={t('toolbar.close')}
                        onClick={onClose}
                        className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                    >
                        <X className="h-4 w-4" />
                    </button>
                </div>
                <p className="mt-3 text-sm text-muted-foreground">{t('toolbar.clearDesc')}</p>
                <div className="mt-6 flex justify-end gap-3">
                    <button
                        type="button"
                        onClick={onClose}
                        className="cursor-pointer rounded-lg border border-border px-4 py-2 text-sm transition-colors hover:bg-accent"
                    >
                        {t('toolbar.cancel')}
                    </button>
                    <button
                        type="button"
                        onClick={onConfirm}
                        className="cursor-pointer rounded-lg bg-destructive px-4 py-2 text-sm text-destructive-foreground transition-opacity hover:opacity-90"
                    >
                        {t('toolbar.confirmClear')}
                    </button>
                </div>
            </div>
        </div>,
        document.body,
    );
}

/** 上传可选格式：与四类节点支持的媒体类型一致（文本节点无文件载体） */
const UPLOAD_ACCEPT = 'image/*,video/*,audio/*';

/** 画布底部偏右操作栏 */
export default function CanvasToolbar({ gridStyle, onGridStyleChange, onAddNode, canUndo = false, canRedo = false, onUndo, onRedo, onClearCanvas, onUploadFiles }: CanvasToolbarProps) {
    const { t } = useTranslation('canvas');
    const [activeTool, setActiveTool] = useState('move');
    const [appearanceOpen, setAppearanceOpen] = useState(false);
    const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
    const uploadInputRef = useRef<HTMLInputElement>(null);

    /** 撤销/重做按历史栈状态禁用 */
    const isToolDisabled = (tool: ToolButton) => {
        if (tool.key === 'undo') return !canUndo;
        if (tool.key === 'redo') return !canRedo;
        return tool.disabled ?? false;
    };

    const handleClick = (tool: ToolButton) => {
        if (isToolDisabled(tool)) return;
        if (tool.key === 'undo') {
            onUndo?.();
            return;
        }
        if (tool.key === 'redo') {
            onRedo?.();
            return;
        }
        if (tool.key === 'appearance') {
            setAppearanceOpen(open => !open);
            return;
        }
        if (tool.key === 'text' || tool.key === 'image' || tool.key === 'video' || tool.key === 'audio' || tool.key === 'genConfig' || tool.key === 'group') {
            onAddNode?.(tool.key);
            return;
        }
        if (tool.key === 'clear') {
            setClearConfirmOpen(true);
            return;
        }
        if (tool.key === 'upload') {
            uploadInputRef.current?.click();
            return;
        }
        // 其余工具的行为后续接入
        setActiveTool(tool.key);
    };

    return (
        <div className="relative">
            {/* 隐藏文件选择框：仅允许四类节点支持的媒体格式 */}
            <input
                ref={uploadInputRef}
                type="file"
                multiple
                accept={UPLOAD_ACCEPT}
                className="hidden"
                onChange={e => {
                    const files = Array.from(e.target.files ?? []);
                    e.target.value = '';
                    if (files.length) onUploadFiles?.(files);
                }}
            />
            {appearanceOpen && (
                <AppearancePanel gridStyle={gridStyle} onGridStyleChange={onGridStyleChange} />
            )}
            {clearConfirmOpen && (
                <ClearConfirmModal
                    onClose={() => setClearConfirmOpen(false)}
                    onConfirm={() => {
                        setClearConfirmOpen(false);
                        onClearCanvas?.();
                    }}
                />
            )}
            <div className="flex items-center gap-1 rounded-2xl border border-border bg-card px-3 py-2 shadow-card">
                {TOOL_GROUPS.map((group, gi) => (
                    <div key={gi} className="flex items-center gap-0.5">
                        {gi > 0 && <div className="mx-2 h-6 w-px bg-border" />}
                        {group.map(tool => {
                            const active = tool.key === 'appearance' ? appearanceOpen : activeTool === tool.key;
                            const disabled = isToolDisabled(tool);
                            const label = t(`toolbar.${tool.key}`);
                            return (
                                <button
                                    key={tool.key}
                                    type="button"
                                    title={label}
                                    aria-label={label}
                                    disabled={disabled}
                                    onClick={() => handleClick(tool)}
                                    className={`flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
                                        disabled
                                            ? 'cursor-not-allowed text-muted-foreground/40'
                                            : tool.danger
                                              ? 'cursor-pointer text-destructive hover:bg-destructive/10'
                                              : active
                                                ? 'cursor-pointer bg-accent text-accent-foreground'
                                                : 'cursor-pointer text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                                    }`}
                                >
                                    {tool.icon}
                                </button>
                            );
                        })}
                    </div>
                ))}
            </div>
        </div>
    );
}
