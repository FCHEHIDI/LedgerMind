//! handlers.rs — Routeur JSON-RPC pour mcp-documents.

use axum::{extract::State, http::HeaderMap, Json};
use ledgermind_common::{JsonRpcError, JsonRpcRequest, JsonRpcResponse};
use serde_json::{json, Value};
use tracing::{info, warn};
use uuid::Uuid;

use crate::storage::StorageState;

pub async fn health() -> Json<Value> {
    Json(json!({ "status": "ok", "service": "mcp-documents" }))
}

pub async fn rpc_handler(
    State(state): State<StorageState>,
    headers: HeaderMap,
    Json(req): Json<JsonRpcRequest>,
) -> Json<Value> {
    let org_id = match extract_org_id(&headers) {
        Some(id) => id,
        None => {
            warn!("rpc: missing or invalid X-Org-Id header");
            return Json(
                serde_json::to_value(JsonRpcError::new(
                    req.id,
                    -32600,
                    "Missing or invalid X-Org-Id header",
                ))
                .unwrap(),
            );
        }
    };

    info!("rpc: method={} org_id={}", req.method, org_id);

    let result = match req.method.as_str() {
        "documents.get_upload_url" => get_upload_url(&state, org_id).await,
        "documents.get_download_url" => get_download_url(&state, org_id, req.params).await,
        _ => {
            return Json(
                serde_json::to_value(JsonRpcError::method_not_found(req.id, &req.method))
                    .unwrap(),
            );
        }
    };

    match result {
        Ok(value) => Json(
            serde_json::to_value(JsonRpcResponse::ok(req.id, value)).unwrap(),
        ),
        Err(e) => {
            warn!("rpc: error method={} err={}", req.method, e);
            Json(serde_json::to_value(JsonRpcError::internal(req.id)).unwrap())
        }
    }
}

fn extract_org_id(headers: &HeaderMap) -> Option<Uuid> {
    let value = headers.get("x-org-id")?.to_str().ok()?;
    Uuid::parse_str(value).ok()
}

/// Génère une clé S3 sécurisée : {org_id}/{uuid}.pdf — ADR-004.
fn safe_object_key(org_id: Uuid) -> String {
    format!("{}/{}.pdf", org_id, Uuid::new_v4())
}

async fn get_upload_url(state: &StorageState, org_id: Uuid) -> anyhow::Result<Value> {
    let key = safe_object_key(org_id);
    // TODO: generate presigned PUT URL via aws-sdk-s3 presigned
    // Placeholder until presigned URL impl
    Ok(json!({
        "key": key,
        "upload_url": format!("PRESIGNED_URL_PLACEHOLDER/{}", key),
        "expires_in": 900
    }))
}

async fn get_download_url(
    state: &StorageState,
    org_id: Uuid,
    params: Option<Value>,
) -> anyhow::Result<Value> {
    let key = params
        .as_ref()
        .and_then(|p| p.get("key"))
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow::anyhow!("missing key param"))?;

    // Validate that the key belongs to this org (ADR-001)
    if !key.starts_with(&org_id.to_string()) {
        return Err(anyhow::anyhow!("cross-tenant key access denied"));
    }

    // TODO: generate presigned GET URL via aws-sdk-s3 presigned
    Ok(json!({
        "download_url": format!("PRESIGNED_URL_PLACEHOLDER/{}", key),
        "expires_in": 300
    }))
}
