"""
Models package - re-exports from the flat app/models.py module
plus organization models from app/models/organization.py
"""

import importlib.util
import sys
from pathlib import Path

# Load app/models.py as a module and re-export everything
_models_py = Path(__file__).parent.parent / "models.py"
_spec = importlib.util.spec_from_file_location("app.models_flat", _models_py)
_flat = importlib.util.module_from_spec(_spec)

# Register before exec to handle circular imports within the flat module
sys.modules["app.models_flat"] = _flat
_spec.loader.exec_module(_flat)

# Copy all exports to this package's namespace
for _name in dir(_flat):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_flat, _name)

# Also import organization models
# Import escrow models (NOT from __init__ - imported directly by escrow service/router)
# Deal is already in app.models.py as a CRM model; escrow models use table escrow_deals
from app.models.organization import Invite, Organization, OrganizationMember  # noqa: F401

__all__ = (
    [n for n in dir(_flat) if not n.startswith("_")]
    + ["Organization", "OrganizationMember", "Invite"]
    + ["Deal", "Milestone", "Dispute"]
)
