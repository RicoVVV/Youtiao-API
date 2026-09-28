import type { MarketplaceListResponse, MarketplaceModel, ModelInfo } from "@/lib/types";
import { get } from "@/lib/request";

/** 从分组价格中提取卡片展示价格 */
function formatGroupPrice(
  groups: MarketplaceModel["groups"]
): { price: string; unit: string; amount: number } {
  const group = groups?.[0];
  if (!group) return { price: "按量计费", unit: "", amount: 0 };
  if (group.pricing.type === "usage_based") {
    return { price: group.pricing.message || "按量计费", unit: "", amount: 0 };
  }
  const item = group.pricing.rules?.[0]?.items.find((entry) => entry.unit_amount !== null);
  const amount = item?.unit_amount ? Number(item.unit_amount) : NaN;
  if (!Number.isFinite(amount)) return { price: "按量计费", unit: "", amount: 0 };
  return { price: `¥${amount}`, unit: item?.kind === "output_video_duration" ? "/秒" : "/次", amount };
}

/** 从模型广场数据映射为展示模型 */
function mapToModelInfo(model: MarketplaceModel): ModelInfo {
  const { amount, unit } = formatGroupPrice(model.groups);
  return {
    id: model.model_id,
    name: model.display_name || model.name,
    provider: model.name,
    providerId: model.provider_id ?? null,
    providerName: model.provider_name ?? null,
    providerLogoUrl: model.provider_logo_url ?? null,
    category: (model.type as "video" | "image" | "text") || "video",
    description: model.description ?? "",
    inputPrice: 0,
    outputPrice: amount,
    unit,
    tags: model.tags,
    _marketplace: model.template || model.groups ? model : undefined,
  };
}

/** 加载全部模型（分页拉取，最多 10 页防溢出） */
async function fetchAllMarketplaceModels(): Promise<MarketplaceModel[]> {
  const all: MarketplaceModel[] = [];
  let page = 1;
  const pageSize = 100;
  while (true) {
    const res = await get<MarketplaceListResponse>("/model-marketplace/list", {
      params: { page, page_size: pageSize },
    });
    all.push(...res.items);
    if (all.length >= res.total || res.items.length < pageSize || page >= 10) break;
    page++;
  }
  return all;
}

/** 获取模型列表。 */
export async function getModels(): Promise<ModelInfo[]> {
  try {
    const models = await fetchAllMarketplaceModels();
    return models.map(mapToModelInfo);
  } catch {
    return [];
  }
}

/** 获取单个模型详情并映射为展示模型。 */
export async function getModelDetail(modelId: string): Promise<ModelInfo> {
  const model = await get<MarketplaceModel>("/model-marketplace/detail", {
    params: { model_id: modelId },
  });
  return mapToModelInfo(model);
}
