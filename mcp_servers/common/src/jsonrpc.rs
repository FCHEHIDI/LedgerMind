//! JSON-RPC 2.0 types — protocol envelope for all MCP servers.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Incoming JSON-RPC 2.0 request.
#[derive(Debug, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub method: String,
    pub params: Option<Value>,
    pub id: Option<Value>,
}

/// Successful JSON-RPC 2.0 response.
#[derive(Debug, Serialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    pub result: Value,
    pub id: Option<Value>,
}

impl JsonRpcResponse {
    /// Build a successful response.
    pub fn ok(id: Option<Value>, result: impl Serialize) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            result: serde_json::to_value(result).unwrap_or(Value::Null),
            id,
        }
    }
}

/// JSON-RPC 2.0 error object.
#[derive(Debug, Serialize)]
pub struct JsonRpcError {
    pub jsonrpc: String,
    pub error: RpcErrorBody,
    pub id: Option<Value>,
}

/// JSON-RPC 2.0 error body.
#[derive(Debug, Serialize)]
pub struct RpcErrorBody {
    pub code: i32,
    pub message: String,
}

impl JsonRpcError {
    pub fn new(id: Option<Value>, code: i32, message: impl Into<String>) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            error: RpcErrorBody {
                code,
                message: message.into(),
            },
            id,
        }
    }

    /// -32601: Method not found
    pub fn method_not_found(id: Option<Value>, method: &str) -> Self {
        Self::new(id, -32601, format!("Method not found: {method}"))
    }

    /// -32602: Invalid params
    pub fn invalid_params(id: Option<Value>, detail: &str) -> Self {
        Self::new(id, -32602, format!("Invalid params: {detail}"))
    }

    /// -32603: Internal error
    pub fn internal(id: Option<Value>) -> Self {
        Self::new(id, -32603, "Internal error")
    }
}
