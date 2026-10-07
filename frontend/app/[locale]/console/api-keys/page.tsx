import type { Metadata } from "next";

import { ApiKeysPanel } from "@/components/console/api-keys-panel";

export const metadata: Metadata = { title: "API 密钥" };

export default function ApiKeysPage() {
  return <ApiKeysPanel />;
}
