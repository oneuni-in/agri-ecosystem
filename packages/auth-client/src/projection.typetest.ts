/**
 * Non-negotiable 3, type level: AgriUser can never grow a UUID or phone
 * field without this file failing `tsc`.
 */
import type { AgriUser } from "./session";

type Equal<A, B> =
  (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;
type Expect<T extends true> = T;

// Exported (never imported) so `noUnusedLocals` doesn't flag these
// assertion-only aliases as dead code — the check lives in the type, not in
// a runtime call site.
export type _ExactKeys = Expect<
  Equal<keyof AgriUser, "agriId" | "name" | "roles" | "coinsBalance">
>;
export type _NoUuidOrPhone = Expect<
  Equal<
    Extract<keyof AgriUser, "sub" | "userId" | "uuid" | "id" | "phone" | "phoneNumber">,
    never
  >
>;
