//! ledgermind-common — Types partagés entre tous les crates MCP.
//!
//! Ce crate définit le protocole JSON-RPC 2.0 utilisé par les serveurs MCP,
//! ainsi que les types de réponse communs.

pub mod jsonrpc;
pub mod error;

pub use error::McpError;
pub use jsonrpc::{JsonRpcRequest, JsonRpcResponse, JsonRpcError};
