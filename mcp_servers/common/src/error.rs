//! McpError — domain error type for all MCP servers.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum McpError {
    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),

    #[error("S3 error: {0}")]
    Storage(String),

    #[error("Not found: {0}")]
    NotFound(String),

    #[error("Unauthorized: tenant isolation violation")]
    Unauthorized,

    #[error("Invalid input: {0}")]
    InvalidInput(String),

    #[error("Internal error")]
    Internal(#[from] anyhow::Error),
}
