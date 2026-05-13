-- ============================================================
-- KOBİ Operasyon Otomasyonu
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ----------------------- customers --------------------------
CREATE TABLE customers (
    id               BIGSERIAL PRIMARY KEY,
    name             VARCHAR(120) NOT NULL,
    phone            VARCHAR(20),
    email            VARCHAR(120),
    telegram_chat_id BIGINT UNIQUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_customers_tg_chat ON customers (telegram_chat_id);

-- ----------------------- suppliers --------------------------
CREATE TABLE suppliers (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(120) NOT NULL,
    email      VARCHAR(120) NOT NULL,
    phone      VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------- products ---------------------------
CREATE TABLE products (
    sku         VARCHAR(40) PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    description TEXT,
    supplier_id BIGINT REFERENCES suppliers(id),
    price       NUMERIC(10,2),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_products_supplier ON products (supplier_id);

-- ----------------------- stock ------------------------------
CREATE TABLE stock (
    sku         VARCHAR(40) PRIMARY KEY REFERENCES products(sku),
    current_qty INTEGER NOT NULL DEFAULT 0,
    threshold   INTEGER NOT NULL DEFAULT 10,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_stock_low ON stock (sku) WHERE current_qty <= threshold;

-- ----------------------- orders -----------------------------
CREATE TABLE orders (
    id          BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status      VARCHAR(20) NOT NULL DEFAULT 'created',
    total       NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_order_status CHECK (status IN
        ('created','processing','shipped','delivered','cancelled'))
);

CREATE INDEX idx_orders_customer ON orders (customer_id);
CREATE INDEX idx_orders_status   ON orders (status);

-- ----------------------- shipments --------------------------
CREATE TABLE shipments (
    id                    BIGSERIAL PRIMARY KEY,
    order_id              BIGINT NOT NULL UNIQUE REFERENCES orders(id),
    tracking_id           VARCHAR(50) NOT NULL UNIQUE,
    carrier               VARCHAR(30) NOT NULL,
    status                VARCHAR(30) NOT NULL DEFAULT 'created',
    current_branch        VARCHAR(120),
    last_status_change_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    eta                   DATE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_shipment_status CHECK (status IN
        ('created','picked_up','in_transit','branch_arrived',
         'out_for_delivery','delivered','returned')),
    CONSTRAINT chk_carrier CHECK (carrier IN
        ('Aras','MNG','Yurtiçi','PTT','Sürat','HepsiJET'))
);

CREATE INDEX idx_shipments_anomaly_scan
    ON shipments (status, last_status_change_at)
    WHERE status = 'branch_arrived';

CREATE INDEX idx_shipments_tracking ON shipments (tracking_id);

-- ----------------------- notification_log -------------------
CREATE TABLE notification_log (
    id          BIGSERIAL PRIMARY KEY,
    notif_type  VARCHAR(40) NOT NULL,
    entity_type VARCHAR(20) NOT NULL,
    entity_ref  VARCHAR(40) NOT NULL,
    channel     VARCHAR(30) NOT NULL,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload     JSONB,

    CONSTRAINT chk_notif_type CHECK (notif_type IN
        ('cargo_anomaly','low_stock','briefing','custom')),
    CONSTRAINT chk_notif_entity CHECK (entity_type IN ('order','sku')),
    CONSTRAINT chk_notif_channel CHECK (channel IN
        ('tg_customer','tg_owner','email'))
);

CREATE INDEX idx_notif_dedup
    ON notification_log (notif_type, entity_type, entity_ref, sent_at DESC);

-- ----------------------- outgoing_emails (P2) ---------------
CREATE TABLE outgoing_emails (
    id          BIGSERIAL PRIMARY KEY,
    to_email    VARCHAR(200) NOT NULL,
    subject     VARCHAR(300) NOT NULL,
    body        TEXT NOT NULL,
    related_sku VARCHAR(40),
    status      VARCHAR(20) NOT NULL DEFAULT 'sent_mock',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_email_status CHECK (status IN
        ('sent_mock','rejected_by_owner','failed'))
);

-- ----------------------- kb_documents (P2 stretch) ----------
CREATE TABLE kb_documents (
    id          BIGSERIAL PRIMARY KEY,
    source_type VARCHAR(30) NOT NULL,
    source_ref  VARCHAR(60),
    content     TEXT NOT NULL,
    embedding   vector(768),
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_kb_source CHECK (source_type IN ('product_description','faq'))
);


-- Embed sayısı 100+ olursa şu satır açılabilir:
-- CREATE INDEX idx_kb_embedding ON kb_documents USING hnsw (embedding vector_cosine_ops);
