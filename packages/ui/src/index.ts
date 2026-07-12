/**
 * @agri/ui — shared component library (SPEC D02).
 *
 * Anatomy and tokens are binding: docs/design-system.md, with the mockup at
 * docs/design-reference/preview_frontend.html as the visual source of truth.
 * Server-component-first; only Modal/Toast are client islands.
 */
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
export { Modal } from "./components/modal";
export { ToastProvider, useToast } from "./components/toast";
export { EmptyState } from "./components/empty-state";
export { OtpInput } from "./components/otp-input";
export type { OtpInputProps } from "./components/otp-input";
export { Avatar, CoinsPill, GpsPill, LangSwitcher, LocationPill } from "./components/pills";
export { PincodeInput } from "./components/pincode-input";
export type { PincodeInputProps } from "./components/pincode-input";
export { ProfileNudge, clampScore } from "./components/profile-nudge";
export type { ProfileNudgeProps } from "./components/profile-nudge";
export { RatingStars } from "./components/rating-stars";
export { SearchBar } from "./components/search-bar";
export type { SearchBarProps } from "./components/search-bar";
export { Skeleton } from "./components/skeleton";
export { cn } from "./lib/cn";

// Composite patterns (design-system.md §2, "Composite patterns")
export { BigCtaGrid, BigCtaTile } from "./composites/big-cta-tile";
export { CategoryGroup } from "./composites/category-group";
export { CertBar, CertCard } from "./composites/cert-bar";
export { EcoPill, EcoStrip } from "./composites/eco-strip";
export { HeaderStack, SearchBand } from "./composites/header-stack";
export { HelplineBand } from "./composites/helpline-band";
export { PincodeHero } from "./composites/pincode-hero";
export { ProductCard, ProductGrid } from "./composites/product-card";
export { CardsRow, Section, Wrap } from "./composites/section";
export { TodayCard, TodayStrip } from "./composites/today-strip";
export { TypeFilter, TypeFilterRow } from "./composites/type-filter-row";
