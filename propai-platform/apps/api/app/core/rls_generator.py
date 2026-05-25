"""Row-Level Security(RLS) SQL 정책 생성기."""


class RLSGenerator:
    """RLS CREATE POLICY 문 자동 생성."""

    POLICY_TYPES = ["tenant_isolation", "soft_delete", "read_only", "owner_only"]

    @staticmethod
    def tenant_isolation(table_name: str, tenant_column: str = "tenant_id") -> dict:
        """테넌트 격리 정책."""
        sq = chr(39)
        return {
            "enable": f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;",
            "policy": (
                f"CREATE POLICY tenant_isolation_{table_name} ON {table_name} "
                f"USING ({tenant_column} = current_setting("
                f"{sq}app.current_tenant{sq})::uuid);"
            ),
            "force": f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;",
        }

    @staticmethod
    def soft_delete(table_name: str, deleted_column: str = "deleted_at") -> dict:
        """소프트 삭제 정책."""
        return {
            "enable": f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;",
            "policy": (
                f"CREATE POLICY soft_delete_{table_name} ON {table_name} "
                f"USING ({deleted_column} IS NULL);"
            ),
        }

    @staticmethod
    def owner_only(table_name: str, owner_column: str = "owner_id") -> dict:
        """소유자 전용 정책."""
        sq = chr(39)
        return {
            "enable": f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;",
            "policy": (
                f"CREATE POLICY owner_only_{table_name} ON {table_name} "
                f"USING ({owner_column} = current_setting("
                f"{sq}app.current_user{sq})::uuid);"
            ),
        }

    @staticmethod
    def read_only(table_name: str, role: str = "viewer") -> dict:
        """읽기 전용 정책."""
        return {
            "enable": f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;",
            "policy": (
                f"CREATE POLICY read_only_{table_name} ON {table_name} "
                f"FOR SELECT TO {role} USING (true);"
            ),
        }

    @staticmethod
    def generate_all(
        table_name: str,
        tenant_column: str = "tenant_id",
        include_soft_delete: bool = True,
    ) -> list:
        """테이블에 대한 전체 RLS 정책 SQL 배열."""
        policies = [RLSGenerator.tenant_isolation(table_name, tenant_column)]
        if include_soft_delete:
            policies.append(RLSGenerator.soft_delete(table_name))
        return policies

    @staticmethod
    def drop_policy(table_name: str, policy_name: str) -> str:
        """정책 삭제 SQL."""
        return f"DROP POLICY IF EXISTS {policy_name} ON {table_name};"

    @staticmethod
    def list_policies_sql(table_name: str = None) -> str:
        """정책 목록 조회 SQL."""
        sq = chr(39)
        if table_name:
            return f"SELECT * FROM pg_policies WHERE tablename = {sq}{table_name}{sq};"
        return "SELECT * FROM pg_policies;"
