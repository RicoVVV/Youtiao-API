"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toaster";

import { PROCESSOR_PRESETS, formatProcessorLabel, type PaymentMethodItem } from "./types";
import { FieldLabel } from "./form-helpers";

export function AddPayMethodModal({
  open,
  onClose,
  onAdd,
  onUpdate,
  editingEntry,
  existingProcessors,
}: {
  open: boolean;
  onClose: () => void;
  onAdd: (entry: PaymentMethodItem) => void;
  onUpdate: (original: PaymentMethodItem, updated: PaymentMethodItem) => void;
  editingEntry: PaymentMethodItem | null;
  existingProcessors: string[];
}) {
  const { t } = useTranslation("console");
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("");
  const [processor, setProcessor] = useState("");
  const [method, setMethod] = useState("");
  const [icon, setIcon] = useState("");
  const [minTopup, setMinTopup] = useState("");
  const [maxTopup, setMaxTopup] = useState("");
  const [search, setSearch] = useState("");
  const [openSelect, setOpenSelect] = useState(false);

  const isEditing = editingEntry !== null;

  useEffect(() => {
    if (editingEntry) {
      setName(editingEntry.payment_name);
      setChannel(editingEntry.payment_channel);
      setMethod(editingEntry.payment_method);
      setProcessor(formatProcessorLabel(t, editingEntry.payment_channel, editingEntry.payment_method));
      setIcon(editingEntry.payment_icon);
      setMinTopup(editingEntry.min_topup ?? "");
      setMaxTopup(editingEntry.max_topup ?? "");
    } else {
      setName("");
      setChannel("epay");
      setMethod("");
      setProcessor("");
      setIcon("");
      setMinTopup("");
      setMaxTopup("");
    }
    setSearch("");
    setOpenSelect(false);
  }, [editingEntry, t]);

  const filteredPresets = PROCESSOR_PRESETS.filter(
    (p) =>
      !existingProcessors.includes(`${p.channel}:${p.method}`) &&
      (t(`paymentGateway.processor.${p.key}`).toLowerCase().includes(search.toLowerCase()) ||
        p.method.toLowerCase().includes(search.toLowerCase()) ||
        p.channel.toLowerCase().includes(search.toLowerCase()))
  );

  const handleSubmit = () => {
    const p = method.trim();
    const n = name.trim() || p || channel;
    if (!p && !channel) return;

    const entry: PaymentMethodItem = {
      payment_name: n,
      payment_channel: channel,
      payment_method: p,
      payment_icon: icon.trim(),
      min_topup: minTopup.trim(),
      max_topup: maxTopup.trim(),
      enabled: true,
    };

    if (isEditing && editingEntry) {
      onUpdate(editingEntry, entry);
    } else {
      if (existingProcessors.includes(`${channel}:${p}`)) {
        toast.error(t("paymentGateway.modal.methodExists"));
        return;
      }
      onAdd(entry);
    }

    setName("");
    setChannel("epay");
    setMethod("");
    setProcessor("");
    setIcon("");
    setMinTopup("");
    setMaxTopup("");
    setSearch("");
    onClose();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-200 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl border bg-background p-6 shadow-xl">
        <div className="mb-5 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">
              {isEditing ? t("paymentGateway.modal.editTitle") : t("paymentGateway.modal.addTitle")}
            </h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {t("paymentGateway.modal.desc")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="mt-0.5 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
          >
            ✕
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <FieldLabel label={t("paymentGateway.modal.name")} hint={t("paymentGateway.modal.nameHint")} />
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("paymentGateway.modal.namePlaceholder")}
              className="mt-1.5"
            />
          </div>

          <div>
            <FieldLabel
              label={t("paymentGateway.modal.processor")}
              hint={t("paymentGateway.modal.processorHint")}
            />
            <div className="relative mt-1.5">
              <Input
                value={processor}
                onChange={(e) => {
                  setProcessor(e.target.value);
                  setMethod(e.target.value);
                  setSearch(e.target.value);
                  setOpenSelect(true);
                }}
                onFocus={() => setOpenSelect(true)}
                placeholder={t("paymentGateway.modal.processorSearch")}
                disabled={isEditing}
              />
              {!isEditing && openSelect && (
                <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border bg-popover p-1 shadow-lg">
                  {filteredPresets.length > 0 ? (
                    filteredPresets.map((p) => (
                      <button
                        key={`${p.channel}:${p.method}`}
                        type="button"
                        className="flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-accent"
                        onClick={() => {
                          setChannel(p.channel);
                          setMethod(p.method);
                          setProcessor(formatProcessorLabel(t, p.channel, p.method));
                          if (!name) setName(t(`paymentGateway.processor.${p.key}`));
                          setOpenSelect(false);
                          setSearch("");
                        }}
                      >
                        <span className="truncate">{formatProcessorLabel(t, p.channel, p.method)}</span>
                        {method === p.method && channel === p.channel && (
                          <span className="text-xs text-primary">✓</span>
                        )}
                      </button>
                    ))
                  ) : (
                    <div className="px-2.5 py-3 text-center text-sm text-muted-foreground">
                      {t("paymentGateway.modal.customProcessor")}<code className="font-mono">{method}</code>
                    </div>
                  )}
                </div>
              )}
            </div>
            {openSelect && (
              <div
                className="fixed inset-0 z-[-1]"
                onClick={() => setOpenSelect(false)}
              />
            )}
          </div>

          <div>
            <FieldLabel label={t("paymentGateway.modal.icon")} hint={t("paymentGateway.modal.iconHint")} />
            <Input
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              placeholder={t("paymentGateway.modal.iconPlaceholder")}
              className="mt-1.5"
            />
          </div>

          <div>
            <FieldLabel label={t("paymentGateway.modal.minTopup")} hint={t("paymentGateway.modal.minTopupHint")} />
            <Input
              type="number"
              min="0"
              step="1"
              value={minTopup}
              onChange={(e) => setMinTopup(e.target.value)}
              placeholder={t("paymentGateway.modal.minTopupPlaceholder")}
              className="mt-1.5"
            />
          </div>

          <div>
            <FieldLabel label={t("paymentGateway.modal.maxTopup")} hint={t("paymentGateway.modal.maxTopupHint")} />
            <Input
              type="number"
              min="0"
              step="1"
              value={maxTopup}
              onChange={(e) => setMaxTopup(e.target.value)}
              placeholder={t("paymentGateway.modal.maxTopupPlaceholder")}
              className="mt-1.5"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose}>
            {t("paymentGateway.modal.cancel")}
          </Button>
          <Button onClick={handleSubmit}>{isEditing ? t("paymentGateway.modal.save") : t("paymentGateway.modal.add")}</Button>
        </div>
      </div>
    </div>
  );
}
