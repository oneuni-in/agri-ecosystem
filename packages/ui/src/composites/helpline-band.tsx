import type { ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Helpline band (`.helpband`): deep-green 18px-radius band, 34px icon,
 * bold line + sub, right-aligned glowing call button.
 */
export function HelplineBand({
  icon,
  title,
  sub,
  callLabel,
  callHref,
  className,
}: {
  icon: ReactNode;
  title: ReactNode;
  sub: ReactNode;
  callLabel: ReactNode;
  callHref?: string;
  className?: string;
}) {
  const callClasses =
    "ml-auto flex min-h-[44px] items-center gap-2 rounded-icon bg-call px-[22px] py-3.5 text-base font-extrabold text-white no-underline shadow-callglow";
  return (
    <div
      className={cn(
        "my-5 flex flex-wrap items-center gap-3.5 rounded-band bg-helpband p-[18px] text-white",
        className,
      )}
    >
      <span aria-hidden="true" className="text-[34px] leading-none">
        {icon}
      </span>
      <div>
        <b className="block text-[17px]">{title}</b>
        <small className="opacity-85">{sub}</small>
      </div>
      {callHref ? (
        <a href={callHref} className={callClasses}>
          📞 {callLabel}
        </a>
      ) : (
        <button type="button" className={callClasses}>
          📞 {callLabel}
        </button>
      )}
    </div>
  );
}
