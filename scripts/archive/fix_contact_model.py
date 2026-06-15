"""Fix Contact model - add is_deleted field"""
with open("/opt/chainke/backend/app/models.py", "r") as f:
    content = f.read()

# Add is_deleted to Contact model
old_contact = '''class Contact(Base):
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
    owner = relationship("User", foreign_keys=[owner_id])'''

new_contact = '''class Contact(Base):
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
    is_deleted = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    owner = relationship("User", foreign_keys=[owner_id])'''

content = content.replace(old_contact, new_contact)

with open("/opt/chainke/backend/app/models.py", "w") as f:
    f.write(content)

import ast
ast.parse(content)
print("Syntax OK - Contact model updated with is_deleted")
