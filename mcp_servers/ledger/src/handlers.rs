//! handlers.rs — Routeur JSON-RPC 2.0 pour mcp-ledger.

use axum::{extract::State, http::HeaderMap, Json};
use ledgermind_common::{JsonRpcError, JsonRpcRequest, JsonRpcResponse};
use serde_json::{json, Value};
use tracing::{info, warn};
use uuid::Uuid;

use crate::db::AppState;

/// Endpoint de santé.
pub async fn health() -> Json<Value> {
    Json(json!({ "status": "ok", "service": "mcp-ledger" }))
}

/// Routeur JSON-RPC 2.0 principal.
///
/// Vérifie X-Org-Id, route vers la méthode correspondante.
/// ADR-001: org_id validé avant tout accès DB.
/// ADR-005: jamais de données métier dans les traces.
pub async fn rpc_handler(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<JsonRpcRequest>,
) -> Json<Value> {
    // Validate org_id from header — ADR-001
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
        "ledger.list_entries" => list_entries(&state, org_id, req.params).await,
        "ledger.get_entry" => get_entry(&state, org_id, req.params).await,
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

async fn list_entries(
    state: &AppState,
    org_id: Uuid,
    _params: Option<Value>,
) -> anyhow::Result<Value> {
    // Double protection: WHERE org_id = $1 + PostgreSQL RLS — ADR-001
    let rows = sqlx::query!(
        r#"
        SELECT id, reference, journal_code, entry_date, status
        FROM ledger_journalentry
        WHERE org_id = $1
        ORDER BY entry_date DESC
        LIMIT 100
        "#,
        org_id
    )
    .fetch_all(&state.pool)
    .await?;

    let entries: Vec<Value> = rows
        .into_iter()
        .map(|r| {
            json!({
                "id": r.id,
                "reference": r.reference,
                "journal_code": r.journal_code,
                "entry_date": r.entry_date.to_string(),
                "status": r.status,
            })
        })
        .collect();

    Ok(json!({ "entries": entries }))
}

async fn get_entry(
    state: &AppState,
    org_id: Uuid,
    params: Option<Value>,
) -> anyhow::Result<Value> {
    let id_str = params
        .as_ref()
        .and_then(|p| p.get("id"))
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow::anyhow!("missing id param"))?;

    let entry_id = Uuid::parse_str(id_str)?;

    let row = sqlx::query!(
        r#"
        SELECT id, reference, journal_code, entry_date, status
        FROM ledger_journalentry
        WHERE id = $1 AND org_id = $2
        "#,
        entry_id,
        org_id
    )
    .fetch_optional(&state.pool)
    .await?;

    match row {
        Some(r) => Ok(json!({
            "id": r.id,
            "reference": r.reference,
            "journal_code": r.journal_code,
            "entry_date": r.entry_date.to_string(),
            "status": r.status,
        })),
        None => Err(anyhow::anyhow!("entry not found")),
    }
}
