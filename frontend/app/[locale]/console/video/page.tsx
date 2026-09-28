import type { Metadata } from "next";

import { VideoPlayground } from "@/components/console/video-playground";

export const metadata: Metadata = { title: "视频生成" };

export default function VideoPlaygroundPage() {
  return <VideoPlayground />;
}
