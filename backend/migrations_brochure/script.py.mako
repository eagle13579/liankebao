"""Digital Brochure 迁移模板"""
revision = "${up_revision}"
down_revision = "${down_revision}"
branch_labels = "${branch_labels}"
depends_on = "${depends_on}"


def upgrade() -> None:
    """${upgrades if upgrades else "pass"}"""


def downgrade() -> None:
    """${downgrades if downgrades else "pass"}"""
