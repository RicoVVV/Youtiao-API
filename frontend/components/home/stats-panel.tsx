"use client";

import { useEffect, useRef, useState } from "react";
import { Activity, Layers, Timer } from "lucide-react";
import { useTranslation } from "react-i18next";

const MODEL_TAGS = [
  "GPT-5",
  "Claude Sonnet 4.5",
  "Gemini 2.5 Pro",
  "DeepSeek V3.2",
  "Qwen3 Max",
  "Sora 2",
  "Veo 3.1",
  "MiniMax H3",
  "Kling 2.5",
  "即梦 3.0",
  "Flux 1.1 Pro",
  "Seedream 4.0",
  "DALL·E 3",
];

function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3);
}

/** 数字从 0 滚动到目标值，目标变化时从当前值平滑过渡 */
function useCountUp(target: number, duration = 1600) {
  const [value, setValue] = useState(0);
  const fromRef = useRef(0);
  const firstRef = useRef(true);

  useEffect(() => {
    const from = fromRef.current;
    const dur = firstRef.current ? duration : 500;
    firstRef.current = false;

    let raf: number;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - start) / dur, 1);
      setValue(Math.round(from + (target - from) * easeOutCubic(p)));
      if (p < 1) {
        raf = requestAnimationFrame(tick);
      } else {
        fromRef.current = target;
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return value;
}

export function StatsPanel() {
  const { t } = useTranslation("home");
  const [calls, setCalls] = useState(1284062);
  const [latency, setLatency] = useState(268);
  const callsDisplay = useCountUp(calls);
  const modelsDisplay = useCountUp(32);
  const latencyDisplay = useCountUp(latency);

  // 模拟实时数据：调用量持续上涨，平均响应延迟小幅波动
  useEffect(() => {
    const timer = setInterval(() => {
      setCalls((v) => v + Math.floor(Math.random() * 40) + 10);
      setLatency(240 + Math.floor(Math.random() * 80));
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  const stats = [
    { icon: Activity, label: t("stats.todayCalls"), value: callsDisplay.toLocaleString(), unit: t("stats.unitCalls") },
    { icon: Layers, label: t("stats.onlineModels"), value: String(modelsDisplay), unit: t("stats.unitModels") },
    { icon: Timer, label: t("stats.avgLatency"), value: String(latencyDisplay), unit: t("stats.unitMs") },
  ];

  return (
    <div className="relative mx-auto mt-16 w-full max-w-4xl">
      <div className="absolute -inset-x-8 -top-8 h-40 bg-gradient-to-b from-primary/10 to-transparent blur-2xl" />

      <div className="shadow-card relative overflow-hidden rounded-2xl border bg-card">
        {/* 标题栏 */}
        <div className="flex items-center justify-between border-b px-5 py-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-success" />
            </span>
            {t("stats.title")}
          </div>
        </div>

        {/* 指标 */}
        <div className="grid grid-cols-1 divide-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {stats.map((stat) => (
            <div key={stat.label} className="flex items-center gap-4 px-6 py-5">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <stat.icon className="size-5" />
              </span>
              <div>
                <p className="text-xs text-muted-foreground">{stat.label}</p>
                <p className="mt-0.5 font-mono text-xl font-semibold tabular-nums">
                  {stat.value}
                  <span className="ml-1 text-xs font-normal text-muted-foreground">
                    {stat.unit}
                  </span>
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* 模型跑马灯 */}
        <div className="border-t bg-muted/40 py-3 [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
          <div className="animate-marquee flex w-max gap-3">
            {[...MODEL_TAGS, ...MODEL_TAGS].map((tag, i) => (
              <span
                key={`${tag}-${i}`}
                className="flex items-center gap-1.5 whitespace-nowrap rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground"
              >
                <span className="size-1.5 rounded-full bg-success" />
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
