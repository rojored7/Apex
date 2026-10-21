"""Prueba de humo: el paquete `app` se importa (US-002, T1)."""

import app


def test_app_package_importa() -> None:
    assert app.__name__ == "app"
