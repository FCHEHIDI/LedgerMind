//! mcp-documents — Serveur MCP pour l'accès aux documents MinIO/S3.
//!
//! Port: 3001
//! Transport: JSON-RPC 2.0 over HTTP POST /rpc
//!
//! Methods:
//!   documents.get_upload_url  — génère une presigned URL pour upload PDF
//!   documents.get_download_url — génère une presigned URL pour téléchargement
//!
//! ADR-004: Object naming = {org_id}/{uuid}.pdf (jamais le nom original).
//! ADR-001: X-Org-Id obligatoire, validé avant tout accès MinIO.

mod handlers;
mod storage;

use axum::{routing::post, Router};
use std::net::SocketAddr;
use tracing::info;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .json()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    dotenvy::dotenv().ok();

    let state = storage::StorageState::from_env().await?;

    let app = Router::new()
        .route("/rpc", post(handlers::rpc_handler))
        .route("/health", axum::routing::get(handlers::health))
        .with_state(state);

    let addr = SocketAddr::from(([0, 0, 0, 0], 3001));
    info!("mcp-documents listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}
