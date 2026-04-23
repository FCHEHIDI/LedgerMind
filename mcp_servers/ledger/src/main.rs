//! mcp-ledger — Serveur MCP pour les écritures comptables.
//!
//! Port: 3000
//! Transport: JSON-RPC 2.0 over HTTP POST /rpc
//!
//! Methods:
//!   ledger.list_entries   — liste les écritures d'un tenant
//!   ledger.get_entry      — détail d'une écriture par UUID
//!   ledger.post_entry     — enregistre une écriture (draft → posted)
//!
//! Sécurité ADR-001:
//!   Chaque requête doit fournir X-Org-Id header — validé UUID v4.
//!   Toutes les requêtes SQL incluent WHERE org_id = $org_id en double
//!   protection (le RLS PostgreSQL est la protection primaire).

mod handlers;
mod db;

use axum::{routing::post, Router};
use std::net::SocketAddr;
use tracing::info;
use tracing_subscriber::{fmt, EnvFilter};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // JSON structured logging — ADR-005
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    dotenvy::dotenv().ok();

    let database_url = std::env::var("DATABASE_URL")
        .expect("DATABASE_URL must be set");

    let pool = sqlx::PgPool::connect(&database_url).await?;
    let state = db::AppState { pool };

    let app = Router::new()
        .route("/rpc", post(handlers::rpc_handler))
        .route("/health", axum::routing::get(handlers::health))
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], 3000));
    info!("mcp-ledger listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
