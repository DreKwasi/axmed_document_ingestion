from main import app


def test_root_entrypoint_exposes_the_fastapi_application():
    assert app.title == "Axmed Document Intelligence"
