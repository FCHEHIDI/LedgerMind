//! storage.rs — Client MinIO/S3 pour mcp-documents.

use aws_config::{BehaviorVersion, Region};
use aws_sdk_s3::Client;

/// État applicatif partagé — client S3 et bucket name.
#[derive(Clone)]
pub struct StorageState {
    pub s3: Client,
    pub bucket: String,
}

impl StorageState {
    /// Construit le state depuis les variables d'environnement.
    ///
    /// Variables requises:
    ///   MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, MINIO_BUCKET
    pub async fn from_env() -> anyhow::Result<Self> {
        let endpoint = std::env::var("MINIO_ENDPOINT")
            .unwrap_or_else(|_| "http://minio:9000".to_string());
        let bucket = std::env::var("MINIO_BUCKET")
            .unwrap_or_else(|_| "ledgermind-invoices".to_string());

        let config = aws_config::defaults(BehaviorVersion::latest())
            .region(Region::new("us-east-1"))
            .endpoint_url(endpoint)
            .load()
            .await;

        Ok(Self {
            s3: Client::new(&config),
            bucket,
        })
    }
}
