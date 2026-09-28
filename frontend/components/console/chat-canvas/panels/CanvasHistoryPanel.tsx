"use client";
import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { PanelLeftClose, PanelLeftOpen, Pencil, Trash2, Check, X, Plus } from 'lucide-react';
import { sessionStats, useCanvasHistoryStore, type CanvasHistoryItem } from '@/stores/use-canvas-history-store';

/** 格式化更新时间为 MM/DD HH:mm */
function formatTime(ts: number) {
    const d = new Date(ts);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

interface CanvasHistoryPanelProps {
    open: boolean;
    onToggle: () => void;
}

/** 历史会话浮层：收起时为左上角展开按钮，展开后展示会话列表（IndexedDB 持久化） */
export default function CanvasHistoryPanel({ open, onToggle }: CanvasHistoryPanelProps) {
    const { t } = useTranslation('canvas');
    const items = useCanvasHistoryStore(s => s.items);
    const currentId = useCanvasHistoryStore(s => s.currentId);
    const canvases = useCanvasHistoryStore(s => s.canvases);
    const createSession = useCanvasHistoryStore(s => s.createSession);
    const selectSession = useCanvasHistoryStore(s => s.selectSession);
    const renameSession = useCanvasHistoryStore(s => s.renameSession);
    const deleteSession = useCanvasHistoryStore(s => s.deleteSession);

    /** 正在重命名的条目 id；null 表示无 */
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editingTitle, setEditingTitle] = useState('');
    /** 待确认删除的条目；null 表示无 */
    const [deletingItem, setDeletingItem] = useState<CanvasHistoryItem | null>(null);

    /** 开始重命名 */
    const startEdit = (item: CanvasHistoryItem) => {
        setEditingId(item.id);
        setEditingTitle(item.title);
    };

    /** 确认重命名 */
    const confirmEdit = () => {
        if (editingId) renameSession(editingId, editingTitle);
        setEditingId(null);
    };

    /** 确认删除条目 */
    const confirmDelete = () => {
        if (!deletingItem) return;
        deleteSession(deletingItem.id);
        if (editingId === deletingItem.id) setEditingId(null);
        setDeletingItem(null);
    };

    // 收起状态：仅展示展开按钮
    if (!open) {
        return (
            <button
                type="button"
                aria-label={t('history.expand')}
                onClick={onToggle}
                className="nodrag absolute top-4 left-4 z-20 flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl border border-border bg-popover text-muted-foreground shadow-md transition-colors hover:bg-accent hover:text-accent-foreground"
            >
                <PanelLeftOpen className="h-4.5 w-4.5" />
            </button>
        );
    }

    return (
        <div className="nodrag absolute top-4 left-4 bottom-20 z-20 flex w-72 flex-col overflow-hidden rounded-2xl border border-border bg-popover text-popover-foreground shadow-xl">
            {/* 头部：标题 + 收起按钮 */}
            <div className="flex items-center justify-between px-4 pt-4 pb-3">
                <span className="text-base font-semibold text-foreground">{t('history.title')}</span>
                <button
                    type="button"
                    aria-label={t('history.collapse')}
                    onClick={onToggle}
                    className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                    <PanelLeftClose className="h-4 w-4" />
                </button>
            </div>

            {/* 新建会话 */}
            <div className="px-3 pb-3">
                <button
                    type="button"
                    onClick={() => createSession(t('history.defaultTitle', { index: items.length + 1 }))}
                    className="flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-xl border border-dashed border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary"
                >
                    <Plus className="h-4 w-4" />
                    {t('history.newSession')}
                </button>
            </div>

            {/* 会话列表 */}
            <div className="flex-1 space-y-2 overflow-y-auto px-3 pb-4">
                {items.length === 0 && (
                    <div className="py-10 text-center text-sm text-muted-foreground">{t('history.empty')}</div>
                )}
                {items.map(item => {
                    const stats = sessionStats(item, canvases);
                    const isCurrent = item.id === currentId;
                    return (
                        <div
                            key={item.id}
                            onClick={() => selectSession(item.id)}
                            className={`group cursor-pointer rounded-xl border p-3 transition-colors ${
                                isCurrent ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/20'
                            }`}
                        >
                            {/* 标题行：编辑态显示输入框，否则显示标题 */}
                            {editingId === item.id ? (
                                <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
                                    <input
                                        autoFocus
                                        value={editingTitle}
                                        onChange={e => setEditingTitle(e.target.value)}
                                        onKeyDown={e => {
                                            if (e.key === 'Enter') confirmEdit();
                                            if (e.key === 'Escape') setEditingId(null);
                                        }}
                                        className="h-7 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-sm outline-none focus:border-primary"
                                    />
                                    <button
                                        type="button"
                                        aria-label={t('history.confirm')}
                                        onClick={confirmEdit}
                                        className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-primary transition-colors hover:bg-primary/10"
                                    >
                                        <Check className="h-3.5 w-3.5" />
                                    </button>
                                    <button
                                        type="button"
                                        aria-label={t('history.cancel')}
                                        onClick={() => setEditingId(null)}
                                        className="flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent"
                                    >
                                        <X className="h-3.5 w-3.5" />
                                    </button>
                                </div>
                            ) : (
                                <div className="flex items-center justify-between gap-2">
                                    <span className="min-w-0 truncate text-sm font-medium text-foreground">{item.title}</span>
                                    {/* 悬停显示编辑 / 删除 */}
                                    <div
                                        className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100"
                                        onClick={e => e.stopPropagation()}
                                    >
                                        <button
                                            type="button"
                                            aria-label={`${t('history.rename')} ${item.title}`}
                                            onClick={() => startEdit(item)}
                                            className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                                        >
                                            <Pencil className="h-3.5 w-3.5" />
                                        </button>
                                        <button
                                            type="button"
                                            aria-label={`${t('history.delete')} ${item.title}`}
                                            onClick={() => setDeletingItem(item)}
                                            className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-destructive transition-colors hover:bg-destructive/10"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* 节点 / 连线数量 */}
                            <div className="mt-1.5 text-xs text-muted-foreground">
                                {t('history.stats', { nodes: stats.nodeCount, edges: stats.edgeCount })}
                            </div>

                            {/* 更新时间 */}
                            <div className="mt-1 text-xs text-muted-foreground">{t('history.updatedAt', { time: formatTime(item.updatedAt) })}</div>
                        </div>
                    );
                })}
            </div>

            {/* 删除确认弹窗 */}
            {deletingItem && createPortal(
                <div className="fixed inset-0 z-100 flex items-center justify-center bg-black/50" onClick={() => setDeletingItem(null)}>
                    <div
                        className="w-[90vw] max-w-md rounded-2xl bg-popover p-6 text-popover-foreground shadow-xl"
                        onClick={e => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between">
                            <span className="text-lg font-semibold">{t('history.deleteTitle')}</span>
                            <button
                                type="button"
                                aria-label={t('history.close')}
                                onClick={() => setDeletingItem(null)}
                                className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <p className="mt-3 text-sm text-muted-foreground">
                            {t('history.deleteDesc', { title: deletingItem.title })}
                        </p>
                        <div className="mt-6 flex justify-end gap-3">
                            <button
                                type="button"
                                onClick={() => setDeletingItem(null)}
                                className="cursor-pointer rounded-lg border border-border px-4 py-2 text-sm transition-colors hover:bg-accent"
                            >
                                {t('history.cancel')}
                            </button>
                            <button
                                type="button"
                                onClick={confirmDelete}
                                className="cursor-pointer rounded-lg bg-destructive px-4 py-2 text-sm text-destructive-foreground transition-opacity hover:opacity-90"
                            >
                                {t('history.delete')}
                            </button>
                        </div>
                    </div>
                </div>,
                document.body,
            )}
        </div>
    );
}
