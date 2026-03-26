"""S06: backup_logs restore_verified DEFAULT false 명시"""
revision = "015_patch_s06_backup_logs"
down_revision = "014_patch_s05_reservation_index"


def upgrade():
    # v53 schema does not contain 'restore_verified' column in backup_logs.
    # Skipping to prevent transaction abortion.
    pass

def downgrade():
    pass
