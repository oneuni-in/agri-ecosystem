/**
 * @agri/ui — shared component library (SPEC D02).
 *
 * Anatomy and tokens are binding: docs/design-system.md, with the mockup at
 * docs/design-reference/preview_frontend.html as the visual source of truth.
 * Server-component-first; only Modal/Toast are client islands.
 */
export { AdImage } from "./components/ad-image";
export { Badge } from "./components/badge";
export { BottomNav } from "./components/bottom-nav";
export type { BottomNavItem } from "./components/bottom-nav";
export { Button, buttonVariants, CallButton, WhatsAppButton } from "./components/button";
export type { ButtonProps } from "./components/button";
export { Card } from "./components/card";
export type { CardProps } from "./components/card";
export { CategoryTile, tintClass } from "./components/category-tile";
export type { Tint } from "./components/category-tile";
export { ListingCard, PriceUnit } from "./components/listing-card";
export {
  DEFAULT_LIVE_LOCATION_STRINGS,
  LiveLocationPill,
} from "./components/live-location-pill";
export type { LiveLocationPillStrings } from "./components/live-location-pill";
export { Modal } from "./components/modal";
export { ToastProvider, useToast } from "./components/toast";
export { EmptyState } from "./components/empty-state";
export { NotificationBell, formatUnread } from "./components/notification-bell";
export { OtpInput } from "./components/otp-input";
export type { OtpInputProps } from "./components/otp-input";
export { Avatar, CoinsPill, GpsPill, LangSwitcher, LocationPill } from "./components/pills";
export { CoinsBalancePill, useCoinsBalance } from "./components/coins-balance-pill";
export { PincodeInput } from "./components/pincode-input";
export type { PincodeInputProps } from "./components/pincode-input";
export { ProfileNudge, clampScore } from "./components/profile-nudge";
export type { ProfileNudgeProps } from "./components/profile-nudge";
export { RatingStars } from "./components/rating-stars";
export { SearchBar } from "./components/search-bar";
export type { SearchBarProps } from "./components/search-bar";
export { Skeleton } from "./components/skeleton";
export { SponsoredBadge } from "./components/sponsored-badge";
export { cn } from "./lib/cn";
export { fetchCoinsBalance } from "./lib/coins-balance";
export {
  LOC_COOKIE,
  locLabel,
  parseLocationResponse,
  parseLocCookie,
  pincodeFromCookieHeader,
  serializeLocCookie,
} from "./lib/location";
export type { LocContext, LocSource } from "./lib/location";
export { LOW_DATA_COOKIE, lowDataCookieString, parseLowDataCookie } from "./lib/low-data-core";
export { LowDataToggle, setLowData, useLowData } from "./lib/low-data";
export {
  injectSponsored,
  isSafeMediaUrl,
  isSafeTargetUrl,
  MAX_SPONSORED_PER_PAGE,
  parseServedAd,
  parseServeResponse,
  serveQuery,
  SPONSORED_POSITIONS,
} from "./lib/sponsored";
export type { AdServeContext, ListEntry, ServedAd } from "./lib/sponsored";

// Composite patterns (design-system.md §2, "Composite patterns")
export { AD_CAROUSEL_INTERVAL_MS, AD_CAROUSEL_MAX, AdCarousel } from "./composites/ad-carousel";
export { AdSlot, AdUnit, sendAdBeacon, useImpression } from "./composites/ad-slot";
export { BigCtaGrid, BigCtaTile } from "./composites/big-cta-tile";
export { CategoryBar, CategoryBarLink } from "./composites/category-bar";
export { CategoryGroup } from "./composites/category-group";
export { CertBar, CertCard } from "./composites/cert-bar";
export { EcoPill, EcoStrip } from "./composites/eco-strip";
export { HeaderStack, SearchBand } from "./composites/header-stack";
export { HelplineBand } from "./composites/helpline-band";
export { NotificationsPanel } from "./composites/notifications-panel";
export type {
  NotificationItem,
  NotificationsApi,
  NotificationsStrings,
} from "./composites/notifications-panel";
export { PincodeHero } from "./composites/pincode-hero";
export { ProductCard, ProductGrid } from "./composites/product-card";
export { CardsRow, Section, Wrap } from "./composites/section";
export { SponsoredAd } from "./composites/sponsored-ad";
export { SponsoredListingCard } from "./composites/sponsored-listing-card";
export { TodayCard, TodayStrip } from "./composites/today-strip";
export { TypeFilter, TypeFilterRow } from "./composites/type-filter-row";
export { UtilityLink, UtilityStrip } from "./composites/utility-strip";
