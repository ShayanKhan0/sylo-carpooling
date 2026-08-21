"""
Prompt 11C — Driver Earnings & Reports Module

Provides drivers with financial insights including:
- Monthly earnings summaries
- Lifetime earnings statistics
- Daily earnings charts
- CSV export functionality

Author: Smart Carpooling Backend Team
Date: December 20, 2025
"""

from app.modules.earnings import routers, schemas, service, crud

__all__ = ["routers", "schemas", "service", "crud"]
