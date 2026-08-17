/**
 * A-U4 W0 — Suspense fallbacks for the home's streamed sections.
 *
 * Two rules govern every block in this file.
 *
 * 1. RESERVE THE SPACE. A fallback shorter than the section it stands in for
 *    is a layout shift with extra steps. The home's measured CLS is 0.003 and
 *    that is not a number to spend, so each skeleton reserves the same
 *    envelope its section occupies — the grid skeletons reuse the SAME grid
 *    classes as the real section, so the two cannot drift when a breakpoint
 *    changes.
 * 2. SAY NOTHING. These are `aria-hidden` and carry no text. A screen reader
 *    should hear the section appear, not hear "loading" six times; the
 *    streamed content arrives in the same DOM position moments later.
 *
 * The sweep is the A1 reference's `.skeleton` treatment (cream-deep -> cream
 * -> cream-deep at 1.4s), now a token-built utility in the shared preset. It
 * stops at `prefers-reduced-motion`, where it degrades to a flat cream block.
 */

/** The A1 `.skeleton` sweep. `bg-[length:200%_100%]` is what gives the
 * gradient room to travel — without it the animation has nothing to move. */
const SHIMMER =
  "animate-shimmer bg-shimmer-gradient bg-[length:200%_100%] rounded-card motion-reduce:animate-none motion-reduce:bg-cream-deep";

function Bar({ className = "" }: { className?: string }) {
  return <div className={`${SHIMMER} ${className}`} />;
}

/** A card-shaped placeholder — the repeated unit of most home sections. */
function CardBlock({ className = "" }: { className?: string }) {
  return <div className={`${SHIMMER} ${className}`} />;
}

/** Section heading + N cards in the section's own grid. `gridClass` is passed
 * from the call site so it is literally the same string the real section
 * uses. */
function GridSkeleton({
  count,
  gridClass,
  cardClass,
}: {
  count: number;
  gridClass: string;
  cardClass: string;
}) {
  return (
    <div aria-hidden="true" className="pt-[22px]">
      <Bar className="mb-3.5 h-6 w-52" />
      <div className={gridClass}>
        {Array.from({ length: count }, (_, i) => (
          <CardBlock key={i} className={cardClass} />
        ))}
      </div>
    </div>
  );
}

/** §3 — the TODAY strip. Above the fold, so this one is the most important
 * height in the file: it is reserved to the real strip's four-tile envelope. */
export function TodayStripSkeleton() {
  return (
    <div aria-hidden="true" className="mt-3.5">
      <div className="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <CardBlock key={i} className="h-[104px]" />
        ))}
      </div>
    </div>
  );
}

/** §6b + §7 — mandi ticker and the eight price cards. */
export function MandiSkeleton() {
  return (
    <div aria-hidden="true">
      <Bar className="mt-4 h-9 w-full rounded-pill" />
      <GridSkeleton
        count={8}
        gridClass="grid gap-2.5 max-md:grid-cols-2 md:grid-cols-4"
        cardClass="h-[178px]"
      />
    </div>
  );
}

/** §7b — the season calendar. */
export function CalendarSkeleton() {
  return (
    <div aria-hidden="true" className="pt-[22px]">
      <Bar className="mb-3.5 h-6 w-52" />
      <CardBlock className="h-[188px] w-full" />
    </div>
  );
}

/** §8 — weather: 7-day strip + advisory, on the section's own 2fr/1.1fr grid. */
export function WeatherSkeleton() {
  return (
    <div aria-hidden="true" className="pt-[22px]">
      <Bar className="mb-3.5 h-6 w-44" />
      <div className="grid gap-2.5 md:[grid-template-columns:2fr_1.1fr]">
        <CardBlock className="h-[116px]" />
        <CardBlock className="h-[116px]" />
        <CardBlock className="h-[52px] md:col-span-2" />
      </div>
    </div>
  );
}

/** §9 — three scheme cards + the deadlines bar. */
export function SchemesSkeleton() {
  return (
    <div aria-hidden="true">
      <GridSkeleton
        count={3}
        gridClass="grid gap-2.5 md:grid-cols-3"
        cardClass="h-[164px]"
      />
      <Bar className="mt-2.5 h-[46px] w-full" />
    </div>
  );
}

/** §6 — the 36-tile category grid, five groups. Tall by nature; the reserve
 * matches the `contain-intrinsic-size` the real section already declares. */
export function CategoryGridSkeleton() {
  return (
    <div aria-hidden="true" className="pt-[22px]">
      <Bar className="mb-3.5 h-6 w-64" />
      <div className="flex flex-col gap-4">
        {[8, 8, 8, 6, 6].map((n, g) => (
          <div key={g}>
            <Bar className="mb-2 h-4 w-36" />
            <div className="grid gap-2.5 max-md:grid-cols-3 md:grid-cols-6">
              {Array.from({ length: n }, (_, i) => (
                <CardBlock key={i} className="h-[92px]" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** §10 — the three nearby-business cards. */
export function DirectorySkeleton() {
  return (
    <GridSkeleton
      count={3}
      gridClass="grid gap-2.5 md:grid-cols-2 lg:grid-cols-3"
      cardClass="h-[168px]"
    />
  );
}

/** §11 — knowledge cards beside the news rail. */
export function KnowledgeSkeleton() {
  return (
    <div aria-hidden="true" className="pt-[22px]">
      <Bar className="mb-3.5 h-6 w-56" />
      <div className="grid gap-3 lg:grid-cols-[2fr_1.2fr]">
        <div className="grid content-start gap-2.5 max-md:grid-cols-1 md:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <CardBlock key={i} className="h-[196px]" />
          ))}
        </div>
        <CardBlock className="h-[196px]" />
      </div>
    </div>
  );
}

/** §15 — the three-review strip. */
export function ReviewsSkeleton() {
  return (
    <GridSkeleton
      count={3}
      gridClass="grid gap-2.5 md:grid-cols-3"
      cardClass="h-[132px]"
    />
  );
}

/** §13 — the helpline band. */
export function HelplinesSkeleton() {
  return <Bar className="mt-5 h-[122px] w-full rounded-band" aria-hidden="true" />;
}

/** §14 — the stats band. */
export function StatsSkeleton() {
  return <Bar className="mt-5 h-[86px] w-full rounded-band" aria-hidden="true" />;
}
