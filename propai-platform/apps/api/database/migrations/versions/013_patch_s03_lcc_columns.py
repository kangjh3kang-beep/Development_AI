"""S03/S04: lcc_scenarios pv_energy_cost_krw 컬럼명 통일"""
revision = "013_patch_s03_lcc_columns"
down_revision = "012_patch_s02_sensor_index"


def upgrade():
    # v53 schema uses financial_analyses instead of lcc_scenarios
    pass

def downgrade():
    pass
