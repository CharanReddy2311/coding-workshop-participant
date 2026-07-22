"""Shared utilities for the ACME project tracker Lambda services.

This folder is prefixed with an underscore, so Terraform's service discovery
in infra/locals.tf skips it — it is never deployed as a Lambda of its own.
bin/sync-shared.sh copies it into each service directory before packaging,
which is what makes `from _shared.db import query_all` resolve at runtime.
"""

__all__ = ["auth", "db", "http", "validation"]
