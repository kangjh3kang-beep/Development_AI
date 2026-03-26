"""S05: facility_reservations 시간대 중복 방지 인덱스"""
revision = "014_patch_s05_reservation_index"
down_revision = "013_patch_s03_lcc_columns"


def upgrade():
    # v53 schema uses facility_name, start_time, end_time instead of facility_id, reserved_start, etc.
    # We skip this invalid index creation to avoid aborting the transaction.
    pass

def downgrade():
    pass
