class TransientError(Exception):
    """Falla pasajera (503, timeout, desconexión): se reintenta."""


class PermanentError(Exception):
    """Falla definitiva (destinatario inválido): termina como fallida sin reintentar."""
