"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CircleAlert,
  Clapperboard,
  Download,
  Loader2,
  RefreshCw,
  SendHorizonal,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading } from "@/components/ui/loading";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toaster";
import { getModels } from "@/lib/models";
import { cn } from "@/lib/utils";
import {
  createVideoTask,
  fetchVideoObjectUrl,
  isSuccessStatus,
  isTerminalStatus,
  listVideoTasks,
  pollVideoTask,
  type VideoTask,
} from "@/lib/videos";

/** 状态徽章样式 */
const STATUS_META: Record<string, { label: string; className: string }> = {
  submit_pending: { label: "待提交", className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  queued: { label: "排队中", className: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  running: { label: "生成中", className: "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400" },
  succeeded: { label: "已完成", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  completed: { label: "已完成", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  failed: { label: "失败", className: "border-destructive/30 bg-destructive/10 text-destructive" },
  canceled: { label: "已取消", className: "border-muted-foreground/30 bg-muted text-muted-foreground" },
};

function statusMeta(status: string) {
  return STATUS_META[status] ?? { label: status, className: "border-muted-foreground/30 bg-muted text-muted-foreground" };
}

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-";
}

/** 单个视频任务卡片：非终态轮询，成功后按 media_url fetch Blob 播放 */
function TaskCard({
  task,
  onUpdate,
  onRemove,
}: {
  task: VideoTask;
  onUpdate: (t: VideoTask) => void;
  onRemove: (id: string) => void;
}) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [mediaError, setMediaError] = useState("");

  // 非终态任务轮询详情；卸载、终态或取消后停止
  useEffect(() => {
    if (isTerminalStatus(task.status)) return;
    const controller = new AbortController();
    pollVideoTask(task.id, { signal: controller.signal })
      .then(onUpdate)
      .catch(() => {
        /* 取消或查询失败：停止轮询即可 */
      });
    return () => controller.abort();
  }, [task.id, task.status, onUpdate]);

  // 终态成功后按 media_url 拉取鉴权成品，转换为 Object URL 播放
  useEffect(() => {
    if (!isSuccessStatus(task.status) || !task.media_url) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchVideoObjectUrl(task.media_url)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setVideoUrl(url);
      })
      .catch(() => setMediaError("视频成品暂不可用"));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [task.status, task.media_url]);

  const meta = statusMeta(task.status);
  const running = !isTerminalStatus(task.status);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border/60 bg-card/60 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate font-semibold">{task.model}</h3>
            <Badge variant="outline" className={meta.className}>
              {running && <Loader2 className="size-3 animate-spin" />}
              {meta.label}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            创建时间：{formatTime(task.created_at)}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-8 text-muted-foreground hover:text-destructive"
          onClick={() => onRemove(task.id)}
          aria-label="移除记录"
          title="从列表移除（不影响任务本身）"
        >
          <Trash2 className="size-4" />
        </Button>
      </div>

      {/* 生成中动画：shimmer 占位 + 呼吸图标，不展示具体进度 */}
      {running && (
        <div className="relative aspect-video w-full overflow-hidden rounded-lg border bg-muted">
          <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-white/25 to-transparent" />
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 text-muted-foreground">
            <div className="relative flex size-12 items-center justify-center">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/20" />
              <div className="relative flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Clapperboard className="size-5 animate-pulse" />
              </div>
            </div>
            <p className="text-xs font-medium">视频生成中...</p>
          </div>
        </div>
      )}

      {/* 失败信息 */}
      {task.status === "failed" && (
        <p className="flex items-center gap-1.5 text-xs text-destructive">
          <CircleAlert className="size-3.5 shrink-0" />
          {typeof task.error === "string"
            ? task.error
            : task.error && typeof task.error === "object"
              ? ((task.error as Record<string, unknown>).message as string) ??
                "任务失败"
              : "任务失败"}
        </p>
      )}

      {/* 成功：视频播放 + 下载 */}
      {isSuccessStatus(task.status) && (
        <div className="space-y-2">
          {videoUrl ? (
            <video
              src={videoUrl}
              controls
              playsInline
              className="aspect-video w-full rounded-lg bg-black"
            />
          ) : (
            <div className="flex aspect-video w-full items-center justify-center rounded-lg bg-muted text-sm text-muted-foreground">
              {mediaError ? (
                <span className="flex items-center gap-1.5 text-destructive">
                  <CircleAlert className="size-4" />
                  {mediaError}
                </span>
              ) : (
                <Loading size="md" />
              )}
            </div>
          )}
          {videoUrl && (
            <Button variant="outline" size="sm" asChild>
              <a href={videoUrl} download={`${task.id}.mp4`}>
                <Download className="size-4" />
                下载视频
              </a>
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

export function VideoPlayground() {
  const [models, setModels] = useState<{ value: string; label: string }[]>([]);
  const [model, setModel] = useState("");
  /** API Token 仅存于组件内存，不写入 localStorage / Cookie / 日志 */
  const [apiToken, setApiToken] = useState("");
  const [prompt, setPrompt] = useState("");
  const [seconds, setSeconds] = useState("10");
  const [size, setSize] = useState("864x480");
  const [submitting, setSubmitting] = useState(false);
  const [tasks, setTasks] = useState<VideoTask[]>([]);
  const [listLoading, setListLoading] = useState(true);

  // 可选模型：仅取视频类
  useEffect(() => {
    getModels()
      .then((list) => {
        const videoModels = list
          .filter((m) => m.category === "video")
          .map((m) => ({ value: m.id, label: m.name }));
        setModels(videoModels);
        if (videoModels.length > 0) setModel((v) => v || videoModels[0].value);
      })
      .catch(() => {});
  }, []);

  // 历史任务列表（登录 JWT）
  const loadTasks = useCallback(async () => {
    setListLoading(true);
    try {
      setTasks(await listVideoTasks());
    } catch {
      // 列表失败不阻塞创建流程
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  /** 限流提示状态：message 含并发上限关键词时展示 */
  const [throttled, setThrottled] = useState(false);

  const onSubmit = async () => {
    const content = prompt.trim();
    if (!model || !content || submitting) return;
    if (!apiToken.trim()) {
      toast.warning("请填写 API Token（用于创建视频任务）");
      return;
    }
    const secondsNum = Number(seconds);
    if (!Number.isFinite(secondsNum) || secondsNum <= 0) {
      toast.warning("时长必须为正数");
      return;
    }
    setSubmitting(true);
    setThrottled(false);
    try {
      const task = await createVideoTask(
        apiToken.trim(),
        { model, prompt: content, seconds: secondsNum, size }
      );
      toast.success("任务已创建");
      setPrompt("");
      setTasks((prev) => [task, ...prev]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "任务创建失败";
      if (msg.includes("当前并发任务数已达上限") || msg.includes("并发")) {
        // 并发限流：保留表单，展示操作入口
        setThrottled(true);
      } else {
        toast.error(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onTaskUpdate = useCallback((updated: VideoTask) => {
    setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
  }, []);

  return (
    <div className="flex min-h-[calc(100vh-7.5rem)] w-full flex-col gap-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">视频生成</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            使用 API Token 创建任务，登录态查询与播放
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={loadTasks}
          disabled={listLoading}
        >
          <RefreshCw className={cn("size-4", listLoading && "animate-spin")} />
          刷新
        </Button>
      </div>

      {/* 创建表单 */}
      <div className="rounded-xl border border-border/60 bg-card/40 p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <span className="text-sm font-medium">模型</span>
            <Select
              aria-label="选择视频模型"
              value={model}
              onValueChange={setModel}
              options={models}
              placeholder="请选择视频模型"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="video-api-token" className="text-sm font-medium">
              API Token
              <span className="ml-1 text-xs font-normal text-muted-foreground">
                仅本次创建使用，不会被存储
              </span>
            </label>
            <Input
              id="video-api-token"
              type="password"
              autoComplete="off"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              placeholder="sk-..."
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <label htmlFor="video-prompt" className="text-sm font-medium">
              提示词
            </label>
            <textarea
              id="video-prompt"
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="描述要生成的视频内容"
              className="border-input dark:bg-input/30 w-full resize-none rounded-md border bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="video-seconds" className="text-sm font-medium">
              时长（秒）
            </label>
            <Input
              id="video-seconds"
              type="number"
              min={1}
              step={1}
              value={seconds}
              onChange={(e) => setSeconds(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="video-size" className="text-sm font-medium">
              分辨率
            </label>
            <Input
              id="video-size"
              value={size}
              onChange={(e) => setSize(e.target.value)}
              placeholder="如 864x480"
            />
          </div>
        </div>
        <div className="mt-4 flex justify-end">
          <Button
            onClick={() => onSubmit()}
            disabled={!model || !prompt.trim() || submitting}
          >
            {submitting ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <SendHorizonal className="size-4" />
            )}
            生成视频
          </Button>
        </div>

        {/* 并发限流提示：保留表单，提供查看任务与重试入口 */}
        {throttled && (
          <div className="mt-4 flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
            <CircleAlert className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-400" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
                当前模型正在处理的任务已达到并发上限
              </p>
              <p className="mt-0.5 text-xs text-amber-700/80 dark:text-amber-400/80">
                请等待任一任务完成后再试，已填写的参数不会被清空。
              </p>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadTasks}
                  className="border-amber-500/40 text-amber-800 hover:bg-amber-500/20 dark:text-amber-300"
                >
                  查看任务列表
                </Button>
                <Button
                  size="sm"
                  disabled={!model || !prompt.trim() || submitting}
                  onClick={() => onSubmit()}
                >
                  {submitting && <Loader2 className="size-4 animate-spin" />}
                  重试
                </Button>
              </div>
            </div>
            <button
              type="button"
              aria-label="关闭提示"
              onClick={() => setThrottled(false)}
              className="rounded-md p-0.5 text-amber-600/60 hover:text-amber-700 dark:text-amber-400/60"
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {/* 任务列表 */}
      <div className="relative">
        {tasks.length === 0 ? (
          <div className="flex items-center justify-center rounded-xl border border-border/60 bg-card/40 py-16 text-muted-foreground">
            {listLoading ? (
              <Loading size="lg" />
            ) : (
              <div className="flex flex-col items-center gap-2">
                <Clapperboard className="size-8 text-muted-foreground/50" />
                <p className="text-sm">暂无视频任务，提交上方表单开始生成</p>
              </div>
            )}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {tasks
              .filter((t): t is VideoTask => t != null && typeof t.id === "string")
              .map((t) => (
                <TaskCard
                  key={t.id}
                  task={t}
                  onUpdate={onTaskUpdate}
                onRemove={(id) =>
                  setTasks((prev) => prev.filter((x) => x.id !== id))
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
