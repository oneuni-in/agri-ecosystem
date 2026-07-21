/** D17 mount point: the product management surface lands in a later spec. */
export const metadata = { title: "Products", robots: { index: false } };

export default function ProductsPage() {
  return (
    <main>
      <h1 className="font-display text-[20px] font-extrabold text-ink">Products</h1>
      <p className="mt-2 rounded-card border border-line bg-card p-4 text-[13px] text-sub">
        Manage your product catalog here soon. Approved products stay visible in the public
        catalog.
      </p>
    </main>
  );
}
