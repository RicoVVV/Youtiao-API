"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Save, Search, Trash2, Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

import { AddPayMethodModal } from "./add-pay-method-modal";
import { SectionHeader, FieldLabel } from "./form-helpers";
import { formatProcessorLabel, type PaymentMethodItem } from "./types";

export function GeneralTab({
  minTopup,
  setMinTopup,
  maxTopup,
  setMaxTopup,
  amountOptions,
  setAmountOptions,
  amountDiscount,
  setAmountDiscount,
  payments,
  setPayments,
  onSave,
  saving,
  disabled,
}: {
  minTopup: string;
  setMinTopup: (v: string) => void;
  maxTopup: string;
  setMaxTopup: (v: string) => void;
  amountOptions: string[];
  setAmountOptions: (v: string[]) => void;
  amountDiscount: Record<string, string>;
  setAmountDiscount: (v: Record<string, string>) => void;
  payments: PaymentMethodItem[];
  setPayments: (v: PaymentMethodItem[]) => void;
  onSave: () => void;
  saving: boolean;
  disabled: boolean;
}) {
  const { t } = useTranslation("console");
  const [newAmount, setNewAmount] = useState("");
  const [methodSearch, setMethodSearch] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingEntry, setEditingEntry] = useState<PaymentMethodItem | null>(null);
  const [showDiscountForm, setShowDiscountForm] = useState(false);
  const [discountAmount, setDiscountAmount] = useState("");
  const [discountRate, setDiscountRate] = useState("");

  const filteredMethods = payments.filter(
    (m) =>
      m.payment_name.toLowerCase().includes(methodSearch.toLowerCase()) ||
      m.payment_method.toLowerCase().includes(methodSearch.toLowerCase())
  );

  const addAmount = () => {
    const val = parseFloat(newAmount);
    if (!isNaN(val) && val > 0) {
      const key = val.toFixed(2);
      if (!amountOptions.includes(key)) {
        setAmountOptions(
          [...amountOptions, key].sort(
            (a, b) => parseFloat(a) - parseFloat(b)
          )
        );
      }
      setNewAmount("");
    }
  };

  const removeAmount = (key: string) => {
    setAmountOptions(amountOptions.filter((a) => a !== key));
  };

  const addDiscount = () => {
    const amt = parseFloat(discountAmount);
    const rate = parseFloat(discountRate);
    if (!isNaN(amt) && !isNaN(rate) && amt > 0 && rate > 0 && rate <= 1) {
      setAmountDiscount({
        ...amountDiscount,
        [amt.toFixed(2)]: rate.toFixed(2),
      });
      setDiscountAmount("");
      setDiscountRate("");
      setShowDiscountForm(false);
    }
  };

  const removeDiscount = (key: string) => {
    const next = { ...amountDiscount };
    delete next[key];
    setAmountDiscount(next);
  };

  const discountEntries = Object.entries(amountDiscount).sort(
    ([a], [b]) => parseFloat(a) - parseFloat(b)
  );

  return (
    <div className="space-y-8">
      {/* 通用设置 */}
      <section className="space-y-4">
        <SectionHeader
          title={t("paymentGateway.general.sectionTitle")}
          description={t("paymentGateway.general.sectionDesc")}
        />
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <FieldLabel label={t("paymentGateway.general.minTopup")} hint={t("paymentGateway.general.minTopupHint")} />
            <Input
              type="number"
              min="0"
              step="0.01"
              value={minTopup}
              onChange={(e) => setMinTopup(e.target.value)}
              placeholder="1.00"
              className="mt-1.5"
            />
          </div>
          <div>
            <FieldLabel label={t("paymentGateway.general.maxTopup")} hint={t("paymentGateway.general.maxTopupHint")} />
            <Input
              type="number"
              min="0"
              step="0.01"
              value={maxTopup}
              onChange={(e) => setMaxTopup(e.target.value)}
              placeholder="5000.00"
              className="mt-1.5"
            />
          </div>
        </div>
      </section>

      {/* 付款方式 */}
      <section className="space-y-4">
        <SectionHeader title={t("paymentGateway.general.paymentMethods")} />
        <p className="text-sm text-muted-foreground">
          {t("paymentGateway.general.paymentMethodsDesc")}
        </p>
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={methodSearch}
              onChange={(e) => setMethodSearch(e.target.value)}
              placeholder={t("paymentGateway.general.searchPlaceholder")}
              className="pl-9"
            />
          </div>
          <Button size="sm" onClick={() => setShowAddModal(true)}>
            <Plus className="size-4" />
            {t("paymentGateway.general.addMethod")}
          </Button>
        </div>

        <div className="rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <th className="w-[22%] px-4 py-2.5">{t("paymentGateway.general.colName")}</th>
                <th className="w-[18%] px-4 py-2.5">{t("paymentGateway.general.colProcessor")}</th>
                <th className="w-[12%] px-4 py-2.5">{t("paymentGateway.general.colIcon")}</th>
                <th className="w-[12%] px-4 py-2.5">{t("paymentGateway.general.colMinTopup")}</th>
                <th className="w-[12%] px-4 py-2.5">{t("paymentGateway.general.colMaxTopup")}</th>
                <th className="w-[10%] px-4 py-2.5">{t("paymentGateway.general.colEnabled")}</th>
                <th className="w-20 px-4 py-2.5 text-right">{t("paymentGateway.general.colActions")}</th>
              </tr>
            </thead>
            <tbody>
              {filteredMethods.map((m) => (
                <tr key={`${m.payment_channel}:${m.payment_method}`} className="border-b last:border-0">
                  <td className="px-4 py-3 font-medium">{m.payment_name}</td>
                  <td className="px-4 py-3">
                    {formatProcessorLabel(t, m.payment_channel, m.payment_method)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{m.payment_icon || "—"}</td>
                  <td className="px-4 py-3">{m.min_topup || "—"}</td>
                  <td className="px-4 py-3">{m.max_topup || "—"}</td>
                  <td className="px-4 py-3">
                    <Switch
                      checked={m.enabled}
                      onCheckedChange={(v) =>
                        setPayments(
                          payments.map((x) =>
                            x.payment_channel === m.payment_channel && x.payment_method === m.payment_method
                              ? { ...x, enabled: v }
                              : x
                          )
                        )
                      }
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        onClick={() => {
                          setEditingEntry(m);
                          setShowAddModal(true);
                        }}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 text-destructive hover:text-destructive"
                        onClick={() =>
                          setPayments(payments.filter((x) => !(x.payment_channel === m.payment_channel && x.payment_method === m.payment_method)))
                        }
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredMethods.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-4 py-8 text-center text-muted-foreground"
                  >
                    {t("paymentGateway.general.emptyMethods")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <AddPayMethodModal
          open={showAddModal}
          onClose={() => {
            setShowAddModal(false);
            setEditingEntry(null);
          }}
          onAdd={(entry) => setPayments([...payments, entry])}
          onUpdate={(original, updated) =>
            setPayments(
              payments.map((x) =>
                x.payment_channel === original.payment_channel && x.payment_method === original.payment_method
                  ? updated
                  : x
              )
            )
          }
          editingEntry={editingEntry}
          existingProcessors={payments.map((m) => `${m.payment_channel}:${m.payment_method}`)}
        />
      </section>

      {/* 充值金额选项 */}
      <section className="space-y-4">
        <SectionHeader title={t("paymentGateway.general.amountOptions")} />
        <p className="text-sm text-muted-foreground">
          {t("paymentGateway.general.amountOptionsDesc")}
        </p>
        <div className="flex flex-wrap gap-2">
          {amountOptions.map((a) => (
            <span
              key={a}
              className="inline-flex items-center gap-1 rounded-full border bg-muted/50 px-3 py-1 text-sm"
            >
              {a}
              <button
                type="button"
                onClick={() => removeAmount(a)}
                className="ml-0.5 text-muted-foreground transition-colors hover:text-destructive"
              >
                ×
              </button>
            </span>
          ))}
          {amountOptions.length === 0 && (
            <p className="text-sm text-muted-foreground">{t("paymentGateway.general.emptyAmounts")}</p>
          )}
        </div>
        <div className="flex items-end gap-3 max-w-md">
          <div className="flex-1">
            <p className="text-sm font-medium">{t("paymentGateway.general.addNewAmount")}</p>
            <Input
              type="number"
              min="0"
              step="0.01"
              value={newAmount}
              onChange={(e) => setNewAmount(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addAmount()}
              placeholder={t("paymentGateway.general.addAmountPlaceholder")}
              className="mt-1.5"
            />
          </div>
          <Button variant="outline" onClick={addAmount}>
            <Plus className="size-4" />
            {t("paymentGateway.general.add")}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          {t("paymentGateway.general.amountOptionsHint")}
        </p>
      </section>

      {/* 金额折扣 */}
      <section className="space-y-4">
        <SectionHeader title={t("paymentGateway.general.discount")} />
        <p className="text-sm text-muted-foreground">
          {t("paymentGateway.general.discountDesc")}
        </p>
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => setShowDiscountForm(!showDiscountForm)}
          >
            <Plus className="size-4" />
            {t("paymentGateway.general.addDiscount")}
          </Button>
        </div>

        {discountEntries.length > 0 ? (
          <div className="space-y-2">
            {discountEntries.map(([amt, rate]) => (
              <div
                key={amt}
                className="flex items-center justify-between rounded-lg border px-4 py-2.5"
              >
                <span className="text-sm">
                  {t("paymentGateway.general.discountEntry", { amt, rate })}
                </span>
                <button
                  type="button"
                  onClick={() => removeDiscount(amt)}
                  className="text-muted-foreground transition-colors hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        ) : !showDiscountForm ? (
          <div className="rounded-lg border border-dashed bg-muted/30 px-4 py-8 text-center text-sm text-muted-foreground">
            {t("paymentGateway.general.discountEmpty")}
          </div>
        ) : null}

        {showDiscountForm && (
          <div className="flex items-end gap-3 rounded-lg border bg-muted/30 p-4">
            <div className="flex-1">
              <p className="text-xs font-medium text-muted-foreground">
                {t("paymentGateway.general.discountAmount")}
              </p>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={discountAmount}
                onChange={(e) => setDiscountAmount(e.target.value)}
                placeholder="100"
                className="mt-1"
              />
            </div>
            <div className="flex-1">
              <p className="text-xs font-medium text-muted-foreground">
                {t("paymentGateway.general.discountRate")}
              </p>
              <Input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={discountRate}
                onChange={(e) => setDiscountRate(e.target.value)}
                placeholder="0.90"
                className="mt-1"
              />
            </div>
            <Button onClick={addDiscount}>{t("paymentGateway.general.confirm")}</Button>
            <Button
              variant="ghost"
              onClick={() => setShowDiscountForm(false)}
            >
              {t("paymentGateway.general.cancel")}
            </Button>
          </div>
        )}
      </section>

      <div className="flex justify-end pt-2">
        <Button onClick={onSave} disabled={saving || disabled}>
          <Save className="size-4" />
          {saving ? t("paymentGateway.general.saving") : t("paymentGateway.general.save")}
        </Button>
      </div>
    </div>
  );
}
