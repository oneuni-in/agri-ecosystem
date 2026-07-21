/** D15 mount point: the listings management surface lands in a later spec.
 * The registry entry + this stub prove the console mount contract. */
export const metadata = { title: "Listings", robots: { index: false } };

export default function ListingsPage() {
  return (
    <main>
      <h1 className="font-display text-[20px] font-extrabold text-ink">Listings</h1>
      <p className="mt-2 rounded-card border border-line bg-card p-4 text-[13px] text-sub">
        Manage your branches and coverage here soon. Your public listing stays live at your
        directory page.
      </p>
    </main>
  );
}
