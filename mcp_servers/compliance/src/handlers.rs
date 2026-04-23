//! handlers.rs — Routeur JSON-RPC pour mcp-compliance.

use axum::{http::HeaderMap, Json};
use ledgermind_common::{JsonRpcError, JsonRpcRequest, JsonRpcResponse};
use serde_json::{json, Value};
use tracing::{info, warn};
use uuid::Uuid;

pub async fn health() -> Json<Value> {
    Json(json!({ "status": "ok", "service": "mcp-compliance" }))
}

pub async fn rpc_handler(
    headers: HeaderMap,
    Json(req): Json<JsonRpcRequest>,
) -> Json<Value> {
    let org_id = match extract_org_id(&headers) {
        Some(id) => id,
        None => {
            warn!("rpc: missing X-Org-Id");
            return Json(
                serde_json::to_value(JsonRpcError::new(req.id, -32600, "Missing X-Org-Id"))
                    .unwrap(),
            );
        }
    };

    info!("rpc: method={} org_id={}", req.method, org_id);

    match req.method.as_str() {
        "compliance.check_balance" => Json(
            serde_json::to_value(JsonRpcResponse::ok(
                req.id,
                json!({ "balanced": true, "checked_entries": 0 }),
            ))
            .unwrap(),
        ),
        "compliance.check_tva" => Json(
            serde_json::to_value(JsonRpcResponse::ok(
                req.id,
                json!({ "status": "ok", "discrepancies": [] }),
            ))
            .unwrap(),
        ),
        "compliance.export_fec_hash" => Json(
            serde_json::to_value(JsonRpcResponse::ok(
                req.id,
                json!({ "hash_sha256": "placeholder", "period": null }),
            ))
            .unwrap(),
        ),
        _ => Json(
            serde_json::to_value(JsonRpcError::method_not_found(req.id, &req.method)).unwrap(),
        ),
    }
}

fn extract_org_id(headers: &HeaderMap) -> Option<Uuid> {
    let value = headers.get("x-org-id")?.to_str().ok()?;
    Uuid::parse_str(value).ok()
}
