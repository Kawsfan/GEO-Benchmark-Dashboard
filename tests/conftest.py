import os
import tempfile

# Moet vóór elke import van app.database/app.main gezet worden: beide lezen
# hun configuratie uit de omgeving op importtijd.
_tmp_dir = tempfile.mkdtemp(prefix="geo_dashboard_test_")
os.environ.setdefault("GEO_DASHBOARD_DB_URL", f"sqlite:///{_tmp_dir}/test.db")
os.environ.setdefault("GEO_DASHBOARD_DISABLE_SCHEDULER", "1")
