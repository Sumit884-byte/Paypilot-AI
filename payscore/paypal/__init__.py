"""PayPal REST integration (sandbox-only foundation for the PayScore hackathon)."""

from .client import PayPalClient, PayPalError
from .routes import mount as mount_paypal

__all__ = ["PayPalClient", "PayPalError", "mount_paypal"]
