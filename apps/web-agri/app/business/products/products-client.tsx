"use client";

import { Button, Card, EmptyState, Skeleton, cn } from "@agri/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { ApiError, getJson, patchJson, postJson } from "@/lib/api";

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
}

const FIELD =
  "mt-1 block min-h-[44px] w-full rounded-btn border border-line bg-card px-3 py-2 text-[13px] text-ink";
const LABEL = "block text-[13px] font-semibold text-ink";

function AlertNotice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-card border border-alert-line bg-alert-bg p-3 text-[13px] font-semibold text-ink">
      {children}
    </div>
  );
}

function fieldLabel(field: SpecField): string {
  return field.label.en ?? field.key;
}

function formErrorFromApiError(err: ApiError): string {
  const data = err.detailData;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const { code, field } = data as { code?: unknown; field?: unknown };
    if (typeof code === "string") {
      return `Check the form — ${typeof field === "string" && field ? `'${field}': ` : ""}${code}`;
    }
  }
  return `Check the form: ${err.detail}`;
}

function ModerationChip({ status }: { status: string }) {
  const classes =
    status === "approved"
      ? "bg-verified-bg text-verified-fg"
      : status === "rejected"
        ? "bg-alert-bg text-ink"
        : "bg-sponsored-bg text-sponsored-fg";
  return (
    <span className={cn("inline-flex items-center rounded-pill px-[9px] py-[3px] text-[11px] font-extrabold", classes)}>
      {status}
    </span>
  );
}

export function ProductsClient() {
  const [businesses, setBusinesses] = useState<BusinessRef[] | null>(null);
  const [businessError, setBusinessError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [verticals, setVerticals] = useState<Vertical[]>([]);
  const [verticalSlug, setVerticalSlug] = useState<string>("");
  const [fields, setFields] = useState<SpecField[] | null>(null);

  const [products, setProducts] = useState<Product[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [listLoading, setListLoading] = useState(false);

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
          ? formErrorFromApiError(err)
          : "Could not save the product — please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const archive = async (productId: string) => {
    const forBusiness = selectedIdRef.current;
    try {
      await patchJson(`/api/catalog/products/${productId}`, { status: "archived" });
      if (forBusiness && selectedIdRef.current === forBusiness) void loadProducts(forBusiness, null, false);
    } catch {
      // list stays actionable; owner can retry
    }
  };

  if (businessError) {
    return (
      <div className="mt-4">
        <AlertNotice>Could not load your businesses — please try again.</AlertNotice>
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
        title="Create a listing first"
        action={
          <a href="/business/listings" className="text-[13px] font-semibold text-ink underline">
            Go to listings
          </a>
        }
      />
    );
  }

  return (
    <div className="mt-4 space-y-4">
      <label className={LABEL}>
        Business
        <select className={FIELD} value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
          {businesses.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>

      {listLoading ? (
        <Skeleton width="100%" height="120px" />
      ) : products.length === 0 ? (
        <EmptyState icon="🧺" title="No products yet — add your first below." />
      ) : (
        <div className="space-y-3">
          {products.map((product) => (
            <Card key={product.id} className="space-y-1 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-extrabold text-ink">{product.name}</span>
                <ModerationChip status={product.moderation_status} />
              </div>
              <p className="text-[12px] text-sub">
                {product.vertical_slug}
                {product.price_display ? ` · ${product.price_display}` : ""} · {product.status}
              </p>
              {product.status !== "archived" ? (
                <Button type="button" variant="ghost" onClick={() => void archive(product.id)}>
                  Archive
                </Button>
              ) : null}
            </Card>
          ))}
          {cursor ? (
            <Button
              type="button"
              variant="ghost"
              onClick={() => selectedId && void loadProducts(selectedId, cursor, true)}
            >
              Load more
            </Button>
          ) : null}
        </div>
      )}

      <Card className="space-y-3 p-4">
        <p className="text-[13px] font-extrabold text-ink">Add a product</p>
        <label className={LABEL}>
          Vertical
          <select className={FIELD} value={verticalSlug} onChange={(e) => setVerticalSlug(e.target.value)}>
            {verticals.map((v) => (
              <option key={v.slug} value={v.slug}>
                {v.name.en ?? v.slug}
              </option>
            ))}
          </select>
        </label>
        <label className={LABEL}>
          Name
          <input
            className={FIELD}
            value={productName}
            maxLength={200}
            onChange={(e) => setProductName(e.target.value)}
          />
        </label>
        <label className={LABEL}>
          Price (display text)
          <input
            className={FIELD}
            value={priceDisplay}
            maxLength={100}
            onChange={(e) => setPriceDisplay(e.target.value)}
            placeholder="₹60/litre"
          />
        </label>

        {fields === null ? (
          <Skeleton width="100%" height="60px" />
        ) : (
          fields.map((field) => (
            <label key={field.key} className={LABEL}>
              {fieldLabel(field)}
              {field.required ? " *" : ""}
              {field.type === "boolean" ? (
                <input
                  type="checkbox"
                  className="ml-2 min-h-[20px] min-w-[20px] align-middle"
                  checked={specValues[field.key] === true}
                  onChange={(e) => setSpecValues((s) => ({ ...s, [field.key]: e.target.checked }))}
                />
              ) : field.type === "enum" ? (
                <select
                  className={FIELD}
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
                  className={FIELD}
                  type={field.type === "number" ? "number" : "text"}
                  value={String(specValues[field.key] ?? "")}
                  onChange={(e) => setSpecValues((s) => ({ ...s, [field.key]: e.target.value }))}
                />
              )}
            </label>
          ))
        )}

        {formError ? <AlertNotice>{formError}</AlertNotice> : null}
        <Button
          type="button"
          variant="brand"
          disabled={submitting || !productName.trim() || !verticalSlug}
          onClick={() => void createProduct()}
        >
          {submitting ? "Saving..." : "Add product"}
        </Button>
        <p className="text-[12px] text-sub">New products are reviewed before they appear publicly.</p>
      </Card>
    </div>
  );
}
