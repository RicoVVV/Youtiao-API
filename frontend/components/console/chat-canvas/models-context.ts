"use client";
import { createContext, useContext } from "react";
import type { ModelInfo } from "@/lib/types";
import type { ApiKeyOption } from "@/lib/api-keys";

/** 画布内共享的模型广场列表：由画布根组件加载一次，各节点生成区消费（React Flow 节点无法直接传 props，走 Context） */
export const CanvasModelsContext = createContext<ModelInfo[]>([]);

export const useCanvasModels = () => useContext(CanvasModelsContext);

/** 画布内共享的 API 密钥列表：同样由画布根组件加载一次，各节点密钥下拉消费 */
export const CanvasApiKeysContext = createContext<ApiKeyOption[]>([]);

export const useCanvasApiKeys = () => useContext(CanvasApiKeysContext);
