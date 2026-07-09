/**
 * Compile-time contract: invalid JSON-LD shapes must FAIL typecheck
 * (SPEC D02 non-negotiable). Each @ts-expect-error line breaks the build
 * if the builders ever become permissive. Never imported at runtime.
 */
import {
  breadcrumbJsonLd,
  datasetJsonLd,
  faqPageJsonLd,
  localBusinessJsonLd,
  productJsonLd,
} from "./json-ld";

// Valid shapes compile.
void localBusinessJsonLd({
  name: "AgriSoil Lab",
  url: "https://agri.in/labs/agrisoil",
  address: { locality: "Coimbatore", region: "TN" },
});
void productJsonLd({
  name: "Mapillai Samba Rice 5kg",
  url: "https://organicstore.in/p/mapillai-samba",
  offers: { price: 480, priceCurrency: "INR" },
});
void breadcrumbJsonLd([{ name: "Home", url: "https://agri.in" }]);
void faqPageJsonLd({ questions: [{ question: "Q?", answer: "A." }] });
void datasetJsonLd({ name: "Mandi", description: "Prices", url: "https://agri.in/mandi" });

// @ts-expect-error — LocalBusiness requires an address.
void localBusinessJsonLd({ name: "No address", url: "https://agri.in/x" });

// @ts-expect-error — offers must carry priceCurrency.
void productJsonLd({ name: "P", url: "https://x.in", offers: { price: 10 } });

// @ts-expect-error — breadcrumb items require url.
void breadcrumbJsonLd([{ name: "Home" }]);

// @ts-expect-error — FAQ answers are required.
void faqPageJsonLd({ questions: [{ question: "Q?" }] });

// @ts-expect-error — datasets require a description.
void datasetJsonLd({ name: "Mandi", url: "https://agri.in/mandi" });
