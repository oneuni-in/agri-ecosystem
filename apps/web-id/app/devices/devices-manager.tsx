"use client";

import { Button, Card, EmptyState, Modal, useToast } from "@agri/ui";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { getJson, postJson } from "../../lib/api";

interface Device {
  device_id: string;
  kind: string;
  label: string | null;
  current: boolean;
  created_at: string;
  last_seen_at: string | null;
}

export function DevicesManager({ agriId }: { agriId: string }) {
  const t = useTranslations("ui.auth.devices");
  const router = useRouter();
  const { toast } = useToast();
  const [devices, setDevices] = useState<Device[] | null>(null);

  const reload = useCallback(async () => {
    const body = await getJson("/auth/devices");
    setDevices(body.items as Device[]);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const revoke = async (device: Device) => {
    await postJson("/auth/devices/revoke", { device_id: device.device_id, kind: device.kind });
    toast({ title: t("revoked") });
    if (device.current) {
      router.push("/login");
      return;
    }
    await reload();
  };

  const rename = async (device: Device, label: string) => {
    if (!label.trim()) return;
    await postJson("/auth/devices/label", {
      device_id: device.device_id,
      kind: device.kind,
      label: label.trim(),
    });
    await reload();
  };

  const logout = async () => {
    await postJson("/auth/logout", {});
    router.push("/login");
  };

  const logoutEverywhere = async () => {
    await postJson("/auth/logout-everywhere", {});
    router.push("/login");
  };

  return (
    <main className="mx-auto flex w-full max-w-[560px] flex-col gap-4 px-4 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-xl font-bold text-ink">{t("title")}</h1>
          <p className="text-sm text-sub">@{agriId}</p>
        </div>
        <Button variant="ghost" className="flex-none" onClick={() => void logout()}>
          {t("logout")}
        </Button>
      </header>

      {devices !== null && devices.length === 0 && <EmptyState icon="💻" title={t("empty")} />}

      <ul className="flex flex-col gap-2" data-testid="device-list">
        {(devices ?? []).map((device) => (
          <li key={device.device_id}>
            <Card className="flex items-center justify-between gap-2 p-4">
              <div className="min-w-0">
                <p className="truncate font-bold text-ink">
                  {device.label ?? device.kind}
                  {device.current && (
                    <span className="ml-2 rounded-pill border border-line px-2 text-xs text-sub">
                      {t("current")}
                    </span>
                  )}
                </p>
                <p className="text-xs text-sub">{device.kind}</p>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    const input = event.currentTarget.elements.namedItem("label");
                    void rename(device, (input as HTMLInputElement).value);
                  }}
                  className="hidden sm:flex sm:gap-1.5"
                >
                  <input
                    name="label"
                    aria-label={t("rename")}
                    placeholder={t("renamePlaceholder")}
                    defaultValue={device.label ?? ""}
                    className="min-h-[44px] w-32 rounded-btn border border-line bg-card px-2 text-sm text-ink"
                  />
                  <Button variant="ghost" type="submit" className="flex-none">
                    {t("rename")}
                  </Button>
                </form>
                <Modal
                  trigger={
                    <Button variant="ghost" className="flex-none">
                      {t("revoke")}
                    </Button>
                  }
                  title={t("confirmRevoke")}
                  closeLabel={t("cancel")}
                >
                  <Button variant="brand" onClick={() => void revoke(device)}>
                    {t("revoke")}
                  </Button>
                </Modal>
              </div>
            </Card>
          </li>
        ))}
      </ul>

      {devices !== null && devices.length > 0 && (
        <Modal
          trigger={<Button variant="ghost">{t("revokeAll")}</Button>}
          title={t("confirmRevokeAll")}
          closeLabel={t("cancel")}
        >
          <Button variant="brand" onClick={() => void logoutEverywhere()}>
            {t("revokeAll")}
          </Button>
        </Modal>
      )}
    </main>
  );
}
