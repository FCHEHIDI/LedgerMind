//! mcp-pdf — Serveur MCP de génération PDF (journaux, bilans, FEC).
//!
//! Port: 3002
//! Transport: JSON-RPC 2.0 over HTTP POST /rpc
//!
//! Methods:
//!   pdf.generate_journal   — génère le PDF du journal comptable
//!   pdf.generate_fec       — génère le FEC (Fichier des Écritures Comptables)
//!
//! ADR-005: les données de génération (montants, fournisseurs) ne sont
//! jamais loggées — uniquement les UUIDs des jobs.

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

    let addr = SocketAddr::from(([0, 0, 0, 0], 3002));
    info!("mcp-pdf listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
