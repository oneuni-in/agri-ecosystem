const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

/** Reads milk:last-seen (written by LastSeenWriter on covered pincode
 * pages) and fills the card. textContent assignment only - localStorage
 * content can never become markup. */
const READER_JS = `(function(){try{
var raw=localStorage.getItem("milk:last-seen");if(!raw)return;
var s=JSON.parse(raw);
var card=document.getElementById("offline-last-seen");
var line=document.getElementById("offline-last-seen-line");
var ts=document.getElementById("offline-last-seen-ts");
if(!card||!line||!ts)return;
line.textContent=(s.district||s.pincode)+" ("+s.pincode+"): "+s.banner;
ts.textContent=new Date(s.ts).toLocaleString();
card.hidden=false;
}catch(e){}})();`;

/**
 * Last-seen prices card, deliberately NOT a client component: when the SW
 * serves the cached /offline HTML, page-level JS chunks are not reliably in
 * cache, so a hydrated island may never mount. An inline script in the
 * cached HTML always runs. The whole subtree renders via
 * dangerouslySetInnerHTML so React hydration never reconciles (and never
 * reverts) the script's DOM writes. Public price data only (no-PII rule).
 */
export function OfflineStatus({ title }: { title: string }) {
  const html = `<section id="offline-last-seen" data-testid="offline-last-seen" hidden
 class="rounded-card border border-dashed border-line bg-brand-soft p-4 flex flex-col gap-1">
<h2 class="font-display text-[16px] font-extrabold text-ink">${escapeHtml(title)}</h2>
<p class="text-[13px] font-bold text-ink" id="offline-last-seen-line"></p>
<p class="text-[12px] text-sub" id="offline-last-seen-ts"></p>
</section><script>${READER_JS}</script>`;
  return <div dangerouslySetInnerHTML={{ __html: html }} />;
}
