"""Generates a comprehensive PDF document of the Agri-Ecosystem full folder structure,
architecture, modules, and workflows for executive and technical presentation.
"""

from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos


class AgriArchitecturePDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(15, 15, 15)

    def header(self):
        if self.page_no() == 1:
            return  # Cover banner on page 1
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 6, "AGRI-ECOSYSTEM  |  COMPLETE END-TO-END ARCHITECTURE & DIRECTORY BLUEPRINT", align="L")
        self.ln(4)
        self.set_draw_color(226, 232, 240)
        self.set_line_width(0.3)
        self.line(15, 12, 195, 12)
        self.ln(6)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 6, f"Confidential - Internal Technical Architecture Reference  |  Page {self.page_no()}", align="C")

    def section_heading(self, title, subtitle=None):
        self.ln(4)
        self.set_fill_color(27, 67, 50)  # Forest Green
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 10.5)
        self.cell(0, 7.5, f"  {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        if subtitle:
            self.set_text_color(100, 116, 139)
            self.set_font("Helvetica", "I", 8.5)
            self.ln(1)
            self.multi_cell(0, 4.5, subtitle)
        self.ln(2.5)

    def sub_heading(self, title):
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(30, 41, 59)
        self.cell(0, 5.5, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(51, 65, 85)
        self.multi_cell(0, 4.5, text)
        self.ln(2)

    def key_value_box(self, items):
        self.set_draw_color(226, 232, 240)
        for k, v in items:
            self.set_fill_color(241, 245, 249)
            self.set_font("Helvetica", "B", 8.5)
            self.set_text_color(15, 23, 42)
            self.cell(48, 6.2, f" {k}", border=1, fill=True)
            self.set_font("Helvetica", "", 8.5)
            self.set_text_color(51, 65, 85)
            self.cell(132, 6.2, f" {v}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)

    def code_tree(self, text):
        self.set_fill_color(15, 23, 42)  # Dark Navy
        self.set_text_color(226, 232, 240)
        self.set_font("Courier", "", 7.5)
        lines = text.strip().split("\n")
        
        box_height = len(lines) * 3.8 + 4
        if self.get_y() + box_height > 275:
            self.add_page()
            
        start_y = self.get_y()
        self.rect(15, start_y, 180, box_height, style="F")
        self.set_xy(17, start_y + 2)
        
        for line in lines:
            self.set_x(17)
            self.cell(176, 3.8, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(start_y + box_height + 4)


def build_pdf(output_path: str):
    pdf = AgriArchitecturePDF()
    pdf.add_page()

    # --- COVER BANNER ---
    pdf.set_fill_color(27, 67, 50)
    pdf.rect(15, 15, 180, 36, style="F")
    pdf.set_xy(20, 19)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 8, "AGRI-ECOSYSTEM", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(209, 250, 229)
    pdf.cell(0, 6, "Full End-to-End Folder Structure, Architecture & Technical Blueprint", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, f"Generated: {datetime.now().strftime('%d %B %Y')} | Version: 2.0 (Blueprint v7)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(56)

    # --- 1. EXECUTIVE SUMMARY ---
    pdf.section_heading("1. EXECUTIVE SUMMARY & PLATFORM TOPOLOGY", "Multi-portal agricultural and dairy ecosystem with centralized identity and localized discovery.")
    pdf.body_text(
        "The Agri-Ecosystem is an asset-light, discovery-and-lead platform serving Indian agriculture and dairy markets. "
        "It operates 5 specialized Next.js 15 web applications sharing a tokenized UI library and unified Single Sign-On (AgriID), "
        "backed by a high-performance Python FastAPI modular monolith with PostgreSQL 16, Redis 7 Streams, and Meilisearch."
    )

    pdf.key_value_box([
        ("Architecture Pattern", "Backend-For-Frontend (BFF) + Modular Monolith + Redis Event Bus"),
        ("Frontend Tier", "5 Next.js 15 Apps (React 19, TailwindCSS, next-intl, Sentry)"),
        ("Backend Core", "FastAPI (Python 3.12, async SQLAlchemy 2.0, asyncpg, Pydantic v2)"),
        ("Database & Schema", "PostgreSQL 16 with 11 isolated domain schemas + UUIDv7 PKs"),
        ("Async Event Bus", "Redis 7 Streams with Consumer Groups & Dead-Letter Queue (DLQ)"),
        ("Search Engine", "Meilisearch v1.13 (Typo-tolerant, multi-lingual, spatial filters)"),
        ("Media & Invoices", "MinIO / Cloudflare R2 S3-compatible Object Storage"),
        ("Monorepo Tooling", "Turborepo + pnpm 11 workspace with zero-build internal packages")
    ])

    # --- 2. MASTER REPOSITORY TREE ---
    pdf.section_heading("2. MASTER END-TO-END DIRECTORY TREE", "Complete repository layout across apps, shared packages, backend modules, tests, and DevOps.")
    
    tree_text = """
agri-ecosystem/
|-- apps/                        # Next.js 15 Web Applications (Ports 3000-3004)
|   |-- web-milk/                # Milk.in (Dairy discovery, collection centers, feeds)
|   |-- web-organic/             # TheOrganic.in (Certified organic produce & bio-inputs)
|   |-- web-agri/                # Agri.in (Flagship hub: mandi, weather, calculators)
|   |-- web-id/                  # AgriID (Centralized OAuth2 SSO, login, devices)
|   |-- web-admin/               # Admin Console (KYC claims, ad moderation, payments)
|   `-- Dockerfile               # Multi-stage Docker builder for all web apps
|-- packages/                    # Shared TypeScript Monorepo Packages
|   |-- ui/                      # Design System Component Library (@agri/ui)
|   |-- auth-client/             # BFF OAuth2/PKCE client & JWE session cookies (@agri/auth-client)
|   |-- types/                   # OpenAPI-generated TypeScript interfaces (@agri/types)
|   |-- config/                  # ESLint 9, Tailwind CSS preset, TSConfig bases (@agri/config)
|   `-- observability/           # Sentry error tracking and telemetry (@agri/observability)
|-- backend/
|   `-- core/                    # Python FastAPI Modular Monolith
|       |-- main.py              # Application factory, router assembly, DI seams
|       |-- settings.py          # Environment settings (Pydantic BaseSettings)
|       |-- shared/              # Cross-cutting DB, security, events, cache, storage
|       |-- modules/             # 11 isolated domain modules (pyproject.toml enforced)
|       |   |-- identity/        # Users, OTP auth, OAuth2/OIDC provider, sessions
|       |   |-- directory/       # Listings, branches, coverage radius, catalog, reviews
|       |   |-- leads/           # Buyer requests ("Post My Need"), lead dispatch
|       |   |-- ads/             # Self-serve ad campaigns, auction rotation, geo-boost
|       |   |-- billing/         # Razorpay subscriptions, dunning, GST invoice PDFs
|       |   |-- coins/           # AgriCoins gamification ledger & balance rewards
|       |   |-- market_data/     # Mandi spot prices (Agmarknet), MSP, weather feeds
|       |   |-- notify/          # SMS (MSG91), Email (ZeptoMail), WebPush (VAPID)
|       |   |-- search/          # Meilisearch index management & multi-vertical search
|       |   |-- content/         # Agricultural news, pest alerts, advisory guides
|       |   |-- ai/              # Ask-AI assistant with agronomic safety grounding
|       |   `-- ops/             # Audit logs, health probes, nightly geo-tiering
|       |-- alembic/             # Database migration versions (DDL scripts)
|       |-- tests/               # Over 1,000 unit, integration, and contract tests
|       `-- pyproject.toml       # Python dependencies, Ruff, Mypy, and import-linter rules
|-- docs/                        # Architectural truth, blueprints, runbooks, and QA
|   |-- adr/                     # Architecture Decision Records (ADR 0001 - 0011)
|   |-- Sprint/                  # Master blueprints (Blueprint v7), gap analyses, specs
|   |-- design-reference/        # HTML visual mockups and layout truth
|   |-- runbooks/                # Ops manuals (JWKS rotation, staging deploys, backups)
|   |-- security/                # Threat models, security audit logs, DPDP policies
|   `-- qa/                      # Manual testing checklists, bug trackers, device matrix
|-- e2e/                         # Playwright End-to-End browser test suite
|-- load/                        # k6 stress and concurrency benchmark scripts
|-- scripts/                     # Operational, backup, verification, and deployment scripts
|-- secrets/                     # SOPS-encrypted staging/prod environment credentials
`-- .github/workflows/           # GitHub Actions CI/CD pipelines (ci.yml, deploy-staging.yml)
"""
    pdf.code_tree(tree_text)

    # --- 3. APPS FOLDER BREAKDOWN ---
    pdf.section_heading("3. APPS/ DETAILED FOLDER & FILE RESPONSIBILITIES", "Breakdown of the 5 Next.js applications and their key routes.")
    
    pdf.sub_heading("A. apps/web-agri (Port 3002) - Central Agri.in Hub")
    pdf.body_text(
        "- app/page.tsx (1,220+ lines): Flagship homepage aggregating Location header pill, Today weather/mandi strip, "
        "36-vertical category grid, hyperlocal businesses row, and Sarkari Services hub (PM-Kisan, Patta/Chitta links).\n"
        "- app/tools/: Client-side offline agronomic calculators (Tractor EMI, Seed rate per acre, Fertilizer dosage).\n"
        "- app/categories/: Directory browser for all 36 agricultural verticals (Essentials, Inputs, Services, Community, Buy-Sell).\n"
        "- app/business/[slug]/: Business profile page with verified status badges, WhatsApp reveals, and approved reviews.\n"
        "- lib/home.ts & lib/ads.ts: Resilient server-side data layer fetching mandi prices, weather, and ad banners."
    )

    pdf.sub_heading("B. apps/web-milk (Port 3000) - Milk.in Dairy Portal")
    pdf.body_text(
        "- app/[locale]/[city]/[pincode]/: Dynamic SEO landing pages rendering covering dairy businesses and veterinary doctors.\n"
        "- app/[locale]/directory/: Meilisearch-powered dairy directory browser with category filters.\n"
        "- app/[locale]/post-need/: Buyer lead intake form for bulk milk, cattle feed, and chilling equipment procurement.\n"
        "- app/[locale]/pwa-client.tsx: Service worker registration for offline fallback functionality."
    )

    pdf.sub_heading("C. apps/web-id (Port 3003) - AgriID Single Sign-On Server")
    pdf.body_text(
        "- app/login/: Mobile phone OTP login interface integrating with MSG91 SMS gateways.\n"
        "- app/account/: Profile editing, primary language selection (en/ta/hi), and district/pincode preferences.\n"
        "- app/devices/: Device manager displaying active sessions with one-click 'Logout Everywhere' token revocation.\n"
        "- app/coins/: AgriCoins wallet balance display and rewards activity ledger."
    )

    pdf.sub_heading("D. apps/web-admin (Port 3004) - Admin & Moderation Console")
    pdf.body_text(
        "- app/businesses/ & app/claims/: Business verification KYC workflows (verifying GSTIN, Aadhaar, and electricity bills).\n"
        "- app/ads/ & app/ad-performance/: Self-serve campaign manager, creative approvals, and real-time impression/CTR analytics.\n"
        "- app/reviews/: Unified moderation queue for User-Generated Content (UGC) customer reviews.\n"
        "- app/payments/: Subscription dunning monitors and GST invoice download reconciliation.\n"
        "- app/audit/: Read-only append-only audit log inspection interface."
    )

    pdf.sub_heading("E. apps/web-organic (Port 3001) - TheOrganic.in")
    pdf.body_text(
        "- Specialized marketplace and directory for certified organic farmers, bio-fertilizers, and chemical-free produce."
    )

    # --- 4. PACKAGES FOLDER BREAKDOWN ---
    pdf.section_heading("4. PACKAGES/ DETAILED SHARED LIBRARIES BREAKDOWN", "Modular libraries shared across all web applications.")

    pdf.key_value_box([
        ("@agri/ui", "Shared design system components (MandiCard, AdCarousel, CountUp, Header, Footer, Modals)"),
        ("@agri/auth-client", "BFF OAuth2 PKCE code exchange, encrypted JWE session cookies, silent SSO probing, token rotation"),
        ("@agri/types", "Auto-generated OpenAPI contracts and TypeScript interfaces (TodayPayload, MandiCommodity, BusinessProfile)"),
        ("@agri/config", "Shared ESLint 9 flat rules, Tailwind CSS color tokens, and base tsconfig presets"),
        ("@agri/observability", "Client-side Sentry error logging and performance tracing wrappers")
    ])

    pdf.body_text(
        "Key File Highlight - packages/auth-client/src/handlers.ts:\n"
        "Implements the Backend-For-Frontend (BFF) security contract. The browser only ever receives a 302 redirect, an encrypted "
        "HTTP-only JWE session cookie, or a JSON projection. Raw OAuth2 access and refresh tokens are strictly hidden server-side."
    )

    # --- 5. BACKEND CORE & 11 MODULES ---
    pdf.section_heading("5. BACKEND/CORE/ & THE 11 DOMAIN MODULES", "Python FastAPI Modular Monolith structure and schema isolation.")

    pdf.body_text(
        "The backend is structured under backend/core/modules/ with 11 isolated domain modules. In accordance with pyproject.toml's "
        "import-linter rules, modules are strictly forbidden from importing each other directly. Cross-module communication is "
        "handled via Redis Streams or dependency-inversion lookups in shared/lookups.py."
    )

    modules_data = [
        ("modules/identity", "identity.*", "Users, OtpRequest (peppered hash), SessionRefresh, Profile, Role (RBAC)"),
        ("modules/directory", "directory.*", "Business, Branch, Coverage (radius query), Product, Review, Claim"),
        ("modules/leads", "leads.*", "NeedPost (buyer requests), Lead routing, Anti-spam daily caps"),
        ("modules/ads", "ads.*", "Campaign (budget, targeting), Creative, DailyPartition (impression logs)"),
        ("modules/billing", "billing.*", "Subscription (Growth/Pro), PaymentOrder, Invoice (GST PDF generator)"),
        ("modules/coins", "coins.*", "CoinLedger (immutable double-entry), CoinBalance rewards"),
        ("modules/market_data", "market_data.*", "MandiPrice (Agmarknet spot rates), Commodity (MSP), WeatherSnapshot"),
        ("modules/notify", "notify.*", "Notification queues, SMS (MSG91), Email (ZeptoMail), WebPush (VAPID)"),
        ("modules/search", "N/A (Meili)", "Meilisearch synchronizer worker & federated search router"),
        ("modules/content", "content.*", "Agricultural news, seasonal pest alerts, livestock advisory guides"),
        ("modules/ai", "N/A (LLM)", "Ask-AI assistant with strict agronomic safety guardrails"),
        ("modules/ops", "ops.* & audit.*", "AuditLog (append-only), PincodeTier (T1-T5 economic classification)")
    ]

    for mod, schema, desc in modules_data:
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(27, 67, 50)
        pdf.cell(38, 5.2, mod, border=0)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(32, 5.2, f"Schema: {schema}", border=0)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(51, 65, 85)
        pdf.cell(110, 5.2, desc, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    pdf.sub_heading("Shared Infrastructure (backend/core/shared/)")
    pdf.body_text(
        "- shared/db.py: Async SQLAlchemy engine, session generator, UUIDv7PKMixin, TimestampMixin, and SoftDeleteMixin.\n"
        "- shared/security.py: SecureRouter enforcing private-by-default endpoints, fixed-window rate limiting, and RBAC gates.\n"
        "- shared/events.py: Redis Streams event bus publisher and consumer groups with poison-message DLQ harvesting.\n"
        "- shared/lookups.py: Decoupled dependency-inversion registry connecting modules without direct imports.\n"
        "- shared/storage.py & shared/cache.py: S3/MinIO cloud storage and Redis connection pool singletons."
    )

    # --- 6. CORE WORKFLOWS ---
    pdf.section_heading("6. CORE END-TO-END DATA WORKFLOWS", "How data and requests flow across the system.")

    pdf.body_text(
        "1. Unified AgriID SSO Flow:\n"
        "   User clicks Login -> Next.js BFF generates PKCE verifier -> Redirects to id.agri.in/login -> User enters phone -> "
        "   MSG91 delivers OTP -> User verifies -> Backend issues Auth Code -> BFF exchanges code for JWT tokens -> "
        "   Tokens sealed inside HTTP-only JWE session cookie -> User authenticated across all subdomains.\n\n"
        "2. Hyperlocal Discovery & Search Flow:\n"
        "   Visitor arrives on Agri.in/Milk.in -> Header location pill reads agri_loc cookie / GPS -> Next.js server queries "
        "   GET /directory/covers/{pincode} -> Backend runs indexed geospatial coverage query -> Nearest verified businesses returned "
        "   -> Search bar queries Meilisearch engine for instant typo-tolerant matches.\n\n"
        "3. Self-Serve Ad Monetization Flow:\n"
        "   Dealer creates banner campaign in Admin Console -> Selects vertical & geo-tiers -> Pays via Razorpay Payment Link -> "
        "   Webhook activates campaign -> GET /ads/serve rotates banners with 2.0x Local Geo-Boost -> Daily partition tables log "
        "   impressions -> fpdf2 generates automated GST tax invoice PDF and uploads to MinIO/R2 S3 storage."
    )

    # --- 7. BLUEPRINT ROADMAP ---
    pdf.section_heading("7. MASTER EXECUTION BLUEPRINT (v7)", "Chronological implementation schedule across 130 days.")

    pdf.key_value_box([
        ("Days 1 - 39 (COMPLETED)", "Foundation, Monorepo, AgriID SSO, Directory Engine, Ad Monetization, Milk.in Live"),
        ("Days 40 - 57 (CURRENT)", "Agri.in Hub Launch (A-U1 to A-U4): Mandi workers, Weather, Sarkari Hub, Tools, Agri AI"),
        ("Days 58 - 62", "Milk.in Correction Batch: Performance floor restoration, Razorpay test closure, checklist signed"),
        ("Days 63 - 74", "TheOrganic.in Production Launch: Certified organic marketplace inheriting proven ad & directory engine"),
        ("Days 75 - 130 (Stages B-E)", "Custom Hiring Centers (Machinery rental), Used Equipment Classifieds, Photo Crop Doctor")
    ])

    pdf.output(output_path)
    print(f"Successfully generated PDF at: {output_path}")


if __name__ == "__main__":
    build_pdf("d:/agri-ecosystem/agri-ecosystem-full-structure.pdf")
