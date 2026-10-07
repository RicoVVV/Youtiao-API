import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Edge, Node } from "@xyflow/react";

import { localForageStorage } from "@/lib/localforage-storage";

export type CanvasHistoryItem = {
    id: string;
    title: string;
    createdAt: number;
    updatedAt: number;
};

type CanvasHistoryState = {
    /** 是否已从 IndexedDB 恢复（hydrate 完成前画布不落库，避免空数据覆盖） */
    hydrated: boolean;
    items: CanvasHistoryItem[];
    /** 当前编辑中的会话 */
    currentId: string | null;
    /** 各会话的画布数据（节点 + 连线） */
    canvases: Record<string, { nodes: Node[]; edges: Edge[] }>;

    setHydrated: (v: boolean) => void;
    /** 更新当前会话画布内容；无会话则自动创建（defaultTitle 为本地化默认标题） */
    saveCurrent: (nodes: Node[], edges: Edge[], defaultTitle?: string) => void;
    /** 新建空白会话并切换，返回会话 id */
    createSession: (title?: string) => string;
    /** 切换到指定会话 */
    selectSession: (id: string) => void;
    renameSession: (id: string, title: string) => void;
    deleteSession: (id: string) => void;
};

export const CANVAS_HISTORY_STORE_KEY = "hook-router:canvas_history_store";

const genId = () => (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

export const useCanvasHistoryStore = create<CanvasHistoryState>()(
    persist(
        (set, get) => ({
            hydrated: false,
            items: [],
            currentId: null,
            canvases: {},

            setHydrated: (v) => set({ hydrated: v }),

            saveCurrent: (nodes, edges, defaultTitle) => {
                if (!get().hydrated) return;
                const { currentId, items } = get();
                if (!currentId) {
                    // 首次产生内容：自动创建会话
                    const id = genId();
                    const now = Date.now();
                    set({
                        currentId: id,
                        items: [{ id, title: defaultTitle || "Untitled Canvas 1", createdAt: now, updatedAt: now }, ...items],
                        canvases: { ...get().canvases, [id]: { nodes, edges } },
                    });
                    return;
                }
                set({
                    canvases: { ...get().canvases, [currentId]: { nodes, edges } },
                    items: get().items.map((it) => (it.id === currentId ? { ...it, updatedAt: Date.now() } : it)),
                });
            },

            createSession: (title) => {
                const id = genId();
                const now = Date.now();
                set({
                    currentId: id,
                    items: [
                        { id, title: title?.trim() || `Untitled Canvas ${get().items.length + 1}`, createdAt: now, updatedAt: now },
                        ...get().items,
                    ],
                    canvases: { ...get().canvases, [id]: { nodes: [], edges: [] } },
                });
                return id;
            },

            selectSession: (id) => {
                if (get().items.some((it) => it.id === id)) set({ currentId: id });
            },

            renameSession: (id, title) => {
                const trimmed = title.trim();
                if (!trimmed) return;
                set({ items: get().items.map((it) => (it.id === id ? { ...it, title: trimmed } : it)) });
            },

            deleteSession: (id) => {
                const { items, canvases, currentId } = get();
                const rest = items.filter((it) => it.id !== id);
                const nextCanvases = { ...canvases };
                delete nextCanvases[id];
                set({
                    items: rest,
                    canvases: nextCanvases,
                    currentId: currentId === id ? (rest[0]?.id ?? null) : currentId,
                });
            },
        }),
        {
            name: CANVAS_HISTORY_STORE_KEY,
            storage: createJSONStorage(() => localForageStorage),
            partialize: (state) => ({ items: state.items, currentId: state.currentId, canvases: state.canvases }),
            onRehydrateStorage: () => (state) => {
                state?.setHydrated(true);
            },
        },
    ),
);

/** 会话条目统计（面板展示用） */
export const sessionStats = (item: CanvasHistoryItem, canvases: CanvasHistoryState["canvases"]) => {
    const canvas = canvases[item.id];
    return { nodeCount: canvas?.nodes.length ?? 0, edgeCount: canvas?.edges.length ?? 0 };
};
