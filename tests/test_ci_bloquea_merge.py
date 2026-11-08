"""Prueba rota A PROPÓSITO para demostrar que el CI bloquea el merge (DEV-03). No mergear."""


def test_falla_a_proposito():
    assert False, "Falla a propósito: el PR debe quedar bloqueado por la protección de main"
