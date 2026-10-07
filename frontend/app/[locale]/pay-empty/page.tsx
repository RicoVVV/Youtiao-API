"use client";

import { useEffect } from "react";

export default function PayEmptyPage() {
  useEffect(() => {
    window.close();
  }, []);

  return <p className="p-4 text-sm text-muted-foreground">支付完成，正在关闭...</p>;
}
