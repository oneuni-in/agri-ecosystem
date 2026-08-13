"use client";

/**
 * U2 Group B: rebuilt onto the shared console catalog (ConsoleField /
 * ConsolePanel / ConsoleNotice / ConsoleTable / StateChip / ConfirmAction)
 * and localized via ui.console.products.*. Adds the two Group B abilities
 * the D26 page lacked: product photos (upload/remove through the shared
 * media pipeline — a rejected file type is refused SERVER-side and surfaced
 * here) and true soft-delete (distinct from Archive: archived stays in the
 * console, deleted leaves it). Data flow (refs against stale async
 * clobbering, schema-driven spec fields) is D26's, unchanged.
 */

import {
  Button,
  ConfirmAction,
  ConsoleField,
  ConsoleNotice,
  ConsolePanel,
  EmptyState,
  Skeleton,
  StateChip,
  cn,
  consoleControlClass,
} from "@agri/ui";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ApiError, deleteJson, getJson, patchJson, postForm, postJson } from "@/lib/api";

interface BusinessRef {
  id: string;
  name: string;
}

interface Vertical {
  slug: string;
  name: Record<string, string>;
}

interface SpecField {
  key: string;
  label: Record<string, string>; // i18n, must include "en"
  type: "string" | "number" | "boolean" | "enum";
  unit?: string; // number fields only
  options?: string[]; // enum fields only
  min?: number; // number fields only
  max?: number; // number fields only
  required?: boolean;
  filterable?: boolean;
  comparable?: boolean;
  facet?: boolean;
  group?: string | null;
}

interface Product {
  id: string;
  vertical_slug: string;
  name: string;
  specs: Record<string, unknown>;
  price_display: string | null;
  status: string;
  moderation_status: string;
  images: string[];
}

const MODERATION_TONE = {
  approved: "ok",
  rejected: "alert",
  pending: "pending",
} as const;

export function ProductsClient() {
  const t = useTranslations("ui.console.products");
  const locale = useLocale();
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [businessError, setBusinessError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [verticals, setVerticals] = useState<Vertical[]>([]);
  const [verticalSlug, setVerticalSlug] = useState<string>("");
  const [fields, setFields] = useState<SpecField[] | null>(null);

  const [products, setProducts] = useState<Product[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listNotice, setListNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(
    null,
  );
  const [busyProductId, setBusyProductId] = useState<string | null>(null);

  const [productName, setProductName] = useState("");
  const [priceDisplay, setPriceDisplay] = useState("");
  const [specValues, setSpecValues] = useState<Record<string, string | boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Refs for Task 11 lesson: capture current state for validation in async callbacks
  const selectedIdRef = useRef<string | null>(null);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  useEffect(() => {
    void (async () => {
      try {
        const [bizBody, vertBody] = await Promise.all([
          getJson("/api/directory/businesses?limit=50"),
          getJson("/api/catalog/verticals?limit=50"),
        ]);
        const list = (bizBody.items as BusinessRef[] | undefined) ?? [];
        setBusinesses(list);
        if (list[0]) setSelectedId(list[0].id);
        const verts = (vertBody.items as Vertical[] | undefined) ?? [];
        setVerticals(verts);
        if (verts[0]) setVerticalSlug(verts[0].slug);
      } catch {
        setBusinessError(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!verticalSlug) return;
    setFields(null);
    let cancelled = false;
    void (async () => {
      try {
        const body = await getJson(`/api/catalog/verticals/${verticalSlug}/schema`);
        if (cancelled) return;
        setFields((body.fields as SpecField[] | undefined) ?? []);
        setSpecValues({});
      } catch {
        if (!cancelled) setFields([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [verticalSlug]);

  const loadProducts = async (businessId: string, cursorParam: string | null, append: boolean) => {
    setListLoading(!append);
    try {
      const params = new URLSearchParams({ business_id: businessId, limit: "20" });
      if (cursorParam) params.set("cursor", cursorParam);
      const body = await getJson(`/api/catalog/my/products?${params.toString()}`);
      if (selectedIdRef.current !== businessId) return;
      const items = (body.items as Product[] | undefined) ?? [];
      setProducts((prev) => (append ? [...prev, ...items] : items));
      setCursor((body.next_cursor as string | null | undefined) ?? null);
    } catch {
      if (selectedIdRef.current !== businessId) return;
      if (!append) setProducts([]);
    } finally {
      if (selectedIdRef.current === businessId) setListLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedId) return;
    setCursor(null);
    setListNotice(null);
    void loadProducts(selectedId, null, false);
  }, [selectedId]);

  const buildSpecs = (): Record<string, unknown> => {
    const specs: Record<string, unknown> = {};
    for (const field of fields ?? []) {
      const raw = specValues[field.key];
      if (field.type === "boolean") {
        specs[field.key] = raw === true;
        continue;
      }
      if (raw === undefined || raw === "") continue; // omitted optional
      specs[field.key] = field.type === "number" ? Number(raw) : raw;
    }
    return specs;
  };

  const createProduct = async () => {
    if (!selectedId || !productName.trim()) return;
    const savedFor = selectedId;
    setSubmitting(true);
    setFormError(null);
    try {
      await postJson(`/api/catalog/businesses/${savedFor}/products`, {
        vertical_slug: verticalSlug,
        name: productName.trim(),
        specs: buildSpecs(),
        price_display: priceDisplay.trim() || null,
      });
      if (selectedIdRef.current !== savedFor) return;
      setProductName("");
      setPriceDisplay("");
      setSpecValues({});
      void loadProducts(savedFor, null, false);
    } catch (err) {
      if (selectedIdRef.current !== savedFor) return;
      setFormError(
        err instanceof ApiError && err.status === 422
          ? t("form422", { detail: formErrorDetail(err) })
          : t("formFailed"),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const archive = async (productId: string) => {
    const forBusiness = selectedIdRef.current;
    try {
      await patchJson(`/api/catalog/products/${productId}`, { status: "archived" });
      if (forBusiness && selectedIdRef.current === forBusiness)
        void loadProducts(forBusiness, null, false);
    } catch {
      // list stays actionable; owner can retry
    }
  };

  const deleteProduct = async (productId: string) => {
    const forBusiness = selectedIdRef.current;
    setListNotice(null);
    try {
      await deleteJson(`/api/catalog/products/${productId}`);
    } catch {
      setListNotice({ kind: "error", text: t("deleteFailed") });
      throw new Error("delete_failed"); // keeps the confirm dialog open
    }
    if (forBusiness && selectedIdRef.current === forBusiness)
      void loadProducts(forBusiness, null, false);
  };

  const uploadPhoto = async (productId: string, file: File) => {
    const forBusiness = selectedIdRef.current;
    setBusyProductId(productId);
    setListNotice(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await postForm(`/api/catalog/products/${productId}/images`, form);
      if (forBusiness && selectedIdRef.current === forBusiness)
        await loadProducts(forBusiness, null, false);
    } catch (err) {
      // The SERVER refuses bad files (shared.media.reencode_image → 422) and
      // enforces the per-product cap (409) — the client only translates.
      const text =
        err instanceof ApiError && err.status === 422
          ? t("photoRejected")
          : err instanceof ApiError && err.status === 409
            ? t("photoCap")
            : t("photoFailed");
      setListNotice({ kind: "error", text });
    } finally {
      setBusyProductId(null);
    }
  };

  const removePhoto = async (productId: string, index: number) => {
    const forBusiness = selectedIdRef.current;
    setBusyProductId(productId);
    setListNotice(null);
    try {
      await deleteJson(`/api/catalog/products/${productId}/images/${index}`);
      if (forBusiness && selectedIdRef.current === forBusiness)
        await loadProducts(forBusiness, null, false);
    } catch {
      setListNotice({ kind: "error", text: t("photoFailed") });
    } finally {
      setBusyProductId(null);
    }
  };

  const localized = (labels: Record<string, string>, fallback: string): string =>
    labels[locale] ?? labels.en ?? fallback;

  const fieldLabel = (field: SpecField): string => localized(field.label, field.key);

  const formErrorDetail = (err: ApiError): string => {
    const data = err.detailData;
    if (data && typeof data === "object" && !Array.isArray(data)) {
      const { code, field } = data as { code?: unknown; field?: unknown };
      if (typeof code === "string") {
        return `${typeof field === "string" && field ? `'${field}': ` : ""}${code}`;
      }
    }
    return err.detail;
  };

  if (businessError) {
    return (
      <div className="mt-4">
        <ConsoleNotice tone="alert">{t("loadFailed")}</ConsoleNotice>
      </div>
    );
  }
  if (businesses === null) {
    return (
      <div className="mt-4 space-y-3">
        <Skeleton width="100%" height="44px" />
        <Skeleton width="100%" height="160px" />
      </div>
    );
  }
  if (businesses.length === 0) {
    return (
      <EmptyState
        className="mt-4"
        icon="📦"
        title={t("createListingFirst")}
        action={
          <a href="/business/listings" className="text-[13px] font-semibold text-ink underline">
            {t("goToListings")}
          </a>
        }
      />
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <ConsoleField id="products-business" label={t("businessPicker")}>
        <select
          id="products-business"
          className={consoleControlClass}
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </ConsoleField>

      {listNotice ? (
        <ConsoleNotice tone={listNotice.kind === "ok" ? "ok" : "alert"}>
          {listNotice.text}
        </ConsoleNotice>
      ) : null}

      {listLoading ? (
        <Skeleton width="100%" height="120px" />
      ) : products.length === 0 ? (
        <EmptyState icon="🧺" title={t("empty")} />
      ) : (
        <div className="space-y-3">
          {products.map((product) => (
            <ConsolePanel key={product.id}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-extrabold text-ink">{product.name}</span>
                <StateChip
                  tone={
                    MODERATION_TONE[product.moderation_status as keyof typeof MODERATION_TONE] ??
                    "pending"
                  }
                >
                  {t(
                    `moderation.${
                      product.moderation_status in MODERATION_TONE
                        ? product.moderation_status
                        : "pending"
                    }`,
                  )}
                </StateChip>
              </div>
              <p className="text-[12px] text-sub">
                {product.vertical_slug}
                {product.price_display ? ` · ${product.price_display}` : ""}
                {" · "}
                {product.status === "archived"
                  ? t("productStatus.archived")
                  : t("productStatus.active")}
              </p>

              {product.images.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {product.images.map((url, index) => (
                    <span key={url} className="relative inline-block">
                      {/* eslint-disable-next-line @next/next/no-img-element -- media-domain
                          thumbnails; next/image needs remotePatterns config per env */}
                      <img
                        src={url}
                        alt=""
                        className="h-16 w-16 rounded-btn border border-line object-cover"
                      />
                      <button
                        type="button"
                        aria-label={t("removePhoto", { index: index + 1 })}
                        disabled={busyProductId === product.id}
                        className="absolute -right-1.5 -top-1.5 flex h-6 w-6 items-center justify-center rounded-pill bg-ink text-[11px] font-extrabold text-card"
                        onClick={() => void removePhoto(product.id, index)}
                      >
                        ✕
                      </button>
                    </span>
                  ))}
                </div>
              ) : null}

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <label
                  className={cn(
                    "inline-flex min-h-[44px] cursor-pointer items-center rounded-btn bg-ghost px-4 text-sm font-extrabold text-ink",
                    busyProductId === product.id ? "opacity-60" : "",
                  )}
                >
                  {busyProductId === product.id ? t("uploading") : t("addPhoto")}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="sr-only"
                    disabled={busyProductId === product.id}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (file) void uploadPhoto(product.id, file);
                    }}
                  />
                </label>
                {product.status !== "archived" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    className="flex-none px-4"
                    onClick={() => void archive(product.id)}
                  >
                    {t("archive")}
                  </Button>
                ) : null}
                <ConfirmAction
                  trigger={
                    <Button type="button" variant="ghost" className="flex-none px-4">
                      {t("deleteCta")}
                    </Button>
                  }
                  title={t("deleteConfirmTitle")}
                  description={t("deleteConfirmBody", { name: product.name })}
                  confirmLabel={t("deleteCta")}
                  cancelLabel={t("deleteCancel")}
                  onConfirm={() => deleteProduct(product.id)}
                />
              </div>
            </ConsolePanel>
          ))}
          {cursor ? (
            <Button
              type="button"
              variant="ghost"
              onClick={() => selectedId && void loadProducts(selectedId, cursor, true)}
            >
              {t("loadMore")}
            </Button>
          ) : null}
        </div>
      )}

      <ConsolePanel title={t("addTitle")}>
        <div className="space-y-3">
          <ConsoleField id="product-vertical" label={t("vertical")}>
            <select
              id="product-vertical"
              className={consoleControlClass}
              value={verticalSlug}
              onChange={(e) => setVerticalSlug(e.target.value)}
            >
              {verticals.map((v) => (
                <option key={v.slug} value={v.slug}>
                  {localized(v.name, v.slug)}
                </option>
              ))}
            </select>
          </ConsoleField>
          <ConsoleField id="product-name" label={t("name")}>
            <input
              id="product-name"
              className={consoleControlClass}
              value={productName}
              maxLength={200}
              onChange={(e) => setProductName(e.target.value)}
            />
          </ConsoleField>
          <ConsoleField id="product-price" label={t("price")}>
            <input
              id="product-price"
              className={consoleControlClass}
              value={priceDisplay}
              maxLength={100}
              onChange={(e) => setPriceDisplay(e.target.value)}
              placeholder={t("pricePlaceholder")}
            />
          </ConsoleField>

          {fields === null ? (
            <Skeleton width="100%" height="60px" />
          ) : (
            fields.map((field) => (
              <ConsoleField
                key={field.key}
                id={`spec-${field.key}`}
                label={`${fieldLabel(field)}${field.required ? " *" : ""}`}
              >
                {field.type === "boolean" ? (
                  <input
                    id={`spec-${field.key}`}
                    type="checkbox"
                    className="ml-2 min-h-[20px] min-w-[20px] align-middle"
                    checked={specValues[field.key] === true}
                    onChange={(e) =>
                      setSpecValues((s) => ({ ...s, [field.key]: e.target.checked }))
                    }
                  />
                ) : field.type === "enum" ? (
                  <select
                    id={`spec-${field.key}`}
                    className={consoleControlClass}
                    value={String(specValues[field.key] ?? "")}
                    onChange={(e) => setSpecValues((s) => ({ ...s, [field.key]: e.target.value }))}
                  >
                    <option value="">—</option>
                    {(field.options ?? []).map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={`spec-${field.key}`}
                    className={consoleControlClass}
                    type={field.type === "number" ? "number" : "text"}
                    value={String(specValues[field.key] ?? "")}
                    onChange={(e) => setSpecValues((s) => ({ ...s, [field.key]: e.target.value }))}
                  />
                )}
              </ConsoleField>
            ))
          )}

          {formError ? <ConsoleNotice tone="alert">{formError}</ConsoleNotice> : null}
          <Button
            type="button"
            variant="brand"
            disabled={submitting || !productName.trim() || !verticalSlug}
            onClick={() => void createProduct()}
          >
            {submitting ? t("adding") : t("addCta")}
          </Button>
          <p className="text-[12px] text-sub">{t("reviewedNote")}</p>
        </div>
      </ConsolePanel>
    </div>
  );
}
