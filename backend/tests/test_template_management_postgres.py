import os
from pathlib import Path
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


class TemplateManagementPostgresMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ.get("TEMPLATE_MANAGEMENT_POSTGRES_URL")
        if not url:
            raise unittest.SkipTest("TEMPLATE_MANAGEMENT_POSTGRES_URL is not configured")
        if not any(marker in url.lower() for marker in ("test", "disposable")) or "railway" in url.lower():
            raise RuntimeError("Refusing a non-disposable PostgreSQL target")
        cls.engine = create_engine(url)
        os.environ["DATABASE_URL"] = url
        import models
        from database import Base
        Base.metadata.drop_all(cls.engine)
        Base.metadata.create_all(cls.engine)
        with cls.engine.begin() as connection:
            connection.execute(text("DROP TABLE character_template_audits"))
            connection.execute(text("DROP TABLE character_template_reviews"))
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
        cls.config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_upgrade_downgrade_and_reupgrade(self):
        command.stamp(self.config, "e6b8c1d2f3a4")
        command.upgrade(self.config, "head")
        self.assertIn("character_template_reviews", inspect(self.engine).get_table_names())
        checks = inspect(self.engine).get_check_constraints("character_template_reviews")
        self.assertIn("ck_template_review_status", {item["name"] for item in checks})
        command.downgrade(self.config, "e6b8c1d2f3a4")
        self.assertNotIn("character_template_reviews", inspect(self.engine).get_table_names())
        command.upgrade(self.config, "head")
        self.assertIn("character_template_audits", inspect(self.engine).get_table_names())


if __name__ == "__main__":
    unittest.main()
