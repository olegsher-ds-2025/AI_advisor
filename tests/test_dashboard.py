import pytest
from streamlit.testing.v1 import AppTest

from collector.store import DATA_DIR


@pytest.mark.skipif(not (DATA_DIR / "scores").exists(), reason="needs the advisor parquet lake")
def test_dashboard_renders_without_errors():
    app = AppTest.from_file("../dashboard/app.py", default_timeout=60).run()

    assert not app.exception
    assert len(app.dataframe) >= 5
