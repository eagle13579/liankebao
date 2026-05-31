"""Add Contact model and schemas to online server"""
import os, sys

# === 1. Add Contact model to models.py ===
models_path = "/opt/chainke/backend/app/models.py"
with open(models_path, "r") as f:
    models_content = f.read()

# Check if Contact already exists
if "class Contact" in models_content:
    print("Contact model already exists")
else:
    # Count closing parens/classes to find where to append
    contact_model = '''

class Contact(Base):
    """联系人模型"""
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(50), nullable=True, index=True)
    wechat_id = Column(String(100), nullable=True, index=True)
    company = Column(String(200), nullable=True)
    position = Column(String(100), nullable=True)
    email = Column(String(200), nullable=True)
    notes = Column(String(500), nullable=True)
    tags = Column(String(500), nullable=True)
    source = Column(String(50), nullable=True, default="import")
    import_batch_id = Column(String(36), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    owner = relationship("User", foreign_keys=[owner_id])


class Activity(Base):
    """联系人活动时间线模型"""
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False)
    summary = Column(String(500), nullable=True)
    detail = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    contact = relationship("Contact", backref="activities")
'''

    # Append after existing models (before any non-class content at end)
    models_content += contact_model

    with open(models_path, "w") as f:
        f.write(models_content)
    print("Added Contact model")

# === 2. Add schemas for contacts ===
schemas_path = "/opt/chainke/backend/app/schemas.py"
with open(schemas_path, "r") as f:
    schemas_content = f.read()

# Check if ContactCreate already exists
if "class ContactCreate" in schemas_content:
    print("Contact schemas already exist")
else:
    contact_schemas = '''


# ===== 联系人 =====
class ContactBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = ""
    wechat_id: str = ""
    company: str = ""
    position: str = ""
    email: str = ""
    notes: str = ""
    tags: str = ""
    source: str = "import"


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    name: str = ""
    phone: str = ""
    wechat_id: str = ""
    company: str = ""
    position: str = ""
    email: str = ""
    notes: str = ""
    tags: str = ""
    source: str = ""


class ContactResponse(ContactBase):
    id: int
    owner_id: int
    import_batch_id: str = ""
    created_at: str = ""
    updated_at: str = ""


class ContactListResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    items: list = []


# ===== 联系人活动 =====
class ActivityCreate(BaseModel):
    action_type: str = ""
    summary: str = ""
    detail: str = ""
'''

    schemas_content += contact_schemas

    with open(schemas_path, "w") as f:
        f.write(schemas_content)
    print("Added Contact schemas")

# === 3. Verify syntax ===
import ast
ast.parse(open(models_path).read())
print("models.py syntax OK")
ast.parse(open(schemas_path).read())
print("schemas.py syntax OK")

# === 4. Need to fix contacts.py to use correct import path ===
contacts_path = "/opt/chainke/backend/app/routers/contacts.py"
contacts_content = open(contacts_path).read()

# The online contacts.py imports ContactCreate etc - need to ensure schema import works
# Check if the import is correct
if "from app.schemas import" in contacts_content:
    # All good, the schemas are now available
    print("contacts.py imports OK")

print("Done! Restart service to apply")
