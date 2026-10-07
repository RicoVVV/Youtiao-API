import type { Metadata } from "next";

import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export const metadata: Metadata = { title: "设置" };

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <Card className="shadow-card">
        <CardHeader>
          <CardTitle className="text-base">设置项建设中</CardTitle>
          <CardDescription>
            账户设置功能即将上线，敬请期待。
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
