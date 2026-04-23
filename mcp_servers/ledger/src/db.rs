//! db.rs — Pool PostgreSQL partagé pour mcp-ledger.

use sqlx::PgPool;

/// État applicatif partagé via Axum State.
#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
}
