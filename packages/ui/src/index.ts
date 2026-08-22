/**
 * @agri/ui — shared component library (SPEC D02).
 *
 * Anatomy and tokens are binding: docs/design-system.md, with the mockup at
 * docs/design-reference/preview_frontend.html as the visual source of truth.
 * Server-component-first; only Modal/Toast are client islands.
 */
export { AdImage } from "./components/ad-image";
export { AvatarMenu, AvatarMenuItem } from "./composites/avatar-menu";
export { Badge } from "./components/badge";
export { BottomNav } from "./components/bottom-nav";
export type { BottomNavItem } from "./components/bottom-nav";
export {
  Button,
  buttonVariants,
  CallButton,
  WhatsAppButton,
} from "./components/button";
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
export {
  Avatar,
  CoinsPill,
  GpsPill,
  LangSwitcher,
  LocationPill,
} from "./components/pills";
export {
  CoinsBalancePill,
  useCoinsBalance,
} from "./components/coins-balance-pill";
export { PincodeInput } from "./components/pincode-input";
export type { PincodeInputProps } from "./components/pincode-input";
export { ProfileNudge, clampScore } from "./components/profile-nudge";
export type { ProfileNudgeProps } from "./components/profile-nudge";
export { RatingStars } from "./components/rating-stars";
export { SearchBar } from "./components/search-bar";
export type { SearchBarProps } from "./components/search-bar";
export { Skeleton } from "./components/skeleton";
export { SponsoredBadge } from "./components/sponsored-badge";
export {
  acresToHectares,
  emi,
  fertilizerPlan,
  HA_PER_ACRE,
  NPK_PRESETS_KG_PER_HA,
  SEED_RATE_KG_PER_HA,
  seedRequirementKg,
  SPRAY_VOLUME_L_PER_ACRE,
  sprayMlPerTank,
  tanksPerAcre,
} from "./lib/agri-calculators";
export type {
  FertilizerPlan,
  NpkCrop,
  NpkDose,
  SeedCrop,
} from "./lib/agri-calculators";
export { cn } from "./lib/cn";
// A-U3 content-surface formatting (tested here; web-agri has no runner).
export {
  extractFaq,
  formatDuration,
  helplineStamp,
} from "./lib/content-format";
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
export {
  LOW_DATA_COOKIE,
  lowDataCookieString,
  parseLowDataCookie,
} from "./lib/low-data-core";
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
export {
  AD_CAROUSEL_INTERVAL_MS,
  AD_CAROUSEL_MAX,
  AdCarousel,
} from "./composites/ad-carousel";
export {
  AdSlot,
  AdUnit,
  sendAdBeacon,
  useImpression,
} from "./composites/ad-slot";
export { BigCtaGrid, BigCtaTile } from "./composites/big-cta-tile";
export { CategoryBar, CategoryBarLink } from "./composites/category-bar";
export { CategoryGroup } from "./composites/category-group";
export { CertBar, CertCard } from "./composites/cert-bar";
export { EcoPill, EcoStrip } from "./composites/eco-strip";
export { HeaderStack, SearchBand } from "./composites/header-stack";
// U1 home patterns — shared so the kitchen sink and the page render the same
// components rather than two copies of the same markup.
export {
  AlertCard,
  AppBand,
  IconTile,
  Marquee,
  NeedStrip,
  ReviewCard,
  StatBand,
  StatCell,
  VendorCard,
} from "./composites/home-patterns";
// A-U1 agri home patterns — the A1 FINAL v4 shapes. Same kitchen-sink rule
// as the milk U1 set above.
export {
  CropChip,
  DeadlineItem,
  DeadlinesBar,
  EarnCard,
  Eyebrow,
  KnowledgeCard,
  LiveDot,
  MandiCard,
  NewsList,
  SeasonCalendar,
  SeasonNote,
  SevereAlertStrip,
  ShareChip,
  Spark,
  sparkPoints,
  StoryCard,
  TipCard,
  TrustPillar,
  WaveDivider,
} from "./composites/agri-home-patterns";
export type { PriceTone, SeasonMonth } from "./composites/agri-home-patterns";
export { CountUp, formatCount } from "./composites/count-up";
export { Reveal } from "./composites/reveal";
// U2 console patterns — the write-side sibling catalog. Same rule: the
// kitchen sink and the console render the same components, never copies.
export {
  AdminDataTable,
  AdminShell,
  ConsoleCell,
  ConsoleCheckRow,
  ConsoleField,
  ConsoleFieldRow,
  ConsoleGrid2,
  ConsoleHeadCell,
  ConsoleKpi,
  ConsoleKpiRow,
  ConsoleLabel,
  ConsoleLeadRow,
  ConsoleMiniNote,
  ConsoleModuleCard,
  ConsoleNavCount,
  ConsoleNavIcon,
  ConsoleNavItem,
  ConsoleNavList,
  ConsoleNotice,
  ConsolePageHeader,
  ConsolePanel,
  ConsolePolicyNote,
  ConsoleProgress,
  ConsoleRow,
  ConsoleShell,
  ConsoleSidebarBrand,
  ConsoleSlotCard,
  ConsoleSlotGrid,
  ConsoleStatRow,
  ConsoleStatTile,
  ConsoleSummaryRow,
  ConsoleTable,
  ConsoleTagOption,
  ConsoleTagPick,
  ConsoleTopbar,
  ConsoleUploadDrop,
  ConsoleWizardActions,
  ConsoleWizardSteps,
  consoleControlClass,
  consoleGhostButtonClass,
  consoleMoneyButtonClass,
  consoleNavLinkClass,
  consolePrimaryButtonClass,
  StateChip,
} from "./composites/console-patterns";
export type {
  AdminColumn,
  ConsoleNavBreakpoint,
  ConsoleStateTone,
} from "./composites/console-patterns";
export { ConfirmAction } from "./composites/confirm-action";
export { ConfirmDialog } from "./composites/confirm-dialog";
export { DetailDrawer } from "./composites/detail-drawer";
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
export { TodayCard, TodayStrip, TodayTile } from "./composites/today-strip";
export { TypeFilter, TypeFilterRow } from "./composites/type-filter-row";
export { UtilityLink, UtilityStrip } from "./composites/utility-strip";
