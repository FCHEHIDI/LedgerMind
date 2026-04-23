# =============================================================================
# mcp-ledger — Dockerfile multi-stage Rust
# Même pattern pour les 4 crates MCP : remplacer mcp-ledger par le crate cible
# =============================================================================

# Stage 1: builder — compile le workspace Rust complet
FROM rust:1.82-slim AS builder

WORKDIR /workspace

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cache des dépendances Cargo (layer stable)
COPY Cargo.toml Cargo.lock ./
COPY common/Cargo.toml common/
COPY ledger/Cargo.toml ledger/
COPY documents/Cargo.toml documents/
COPY pdf/Cargo.toml pdf/
COPY compliance/Cargo.toml compliance/

# Stub sources pour le cache du resolver
RUN mkdir -p common/src ledger/src documents/src pdf/src compliance/src \
    && echo "pub fn main() {}" | tee \
        common/src/lib.rs \
        ledger/src/main.rs \
        documents/src/main.rs \
        pdf/src/main.rs \
        compliance/src/main.rs > /dev/null \
    && cargo build --release --bin mcp-ledger \
    && rm -rf common/src ledger/src documents/src pdf/src compliance/src

# Copie le code réel et recompile
COPY . .
RUN touch common/src/lib.rs ledger/src/main.rs \
    && cargo build --release --bin mcp-ledger

# =============================================================================
# Stage 2: runner — image minimale Debian
FROM debian:bookworm-slim AS runner

RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --no-create-home appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    libpq5 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /workspace/target/release/mcp-ledger /usr/local/bin/mcp-ledger

USER appuser

EXPOSE 3000

CMD ["mcp-ledger"]
