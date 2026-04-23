//! mcp-compliance — Serveur MCP pour les contrôles de conformité comptable.
//!
//! Port: 3003
//! Transport: JSON-RPC 2.0 over HTTP POST /rpc
//!
//! Methods:
//!   compliance.check_balance    — vérifie l'équilibre des écritures d'une période
//!   compliance.check_tva        — contrôle TVA déclarée vs calculée
//!   compliance.export_fec_hash  — hash SHA-256 du FEC pour archivage légal
//!
//! Rétention légale: art. L123-22 — 10 ans pour les pièces comptables.

use axum::{routing::post, Router};
use std::net::SocketAddr;
use tracing::info;
use tracing_subscriber::EnvFilter;

mod handlers;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    dotenvy::dotenv().ok();

    let app = Router::new()
        .route("/rpc", post(handlers::rpc_handler))
        .route("/health", axum::routing::get(handlers::health));

    let addr = SocketAddr::from(([0, 0, 0, 0], 3003));
    info!("mcp-compliance listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
