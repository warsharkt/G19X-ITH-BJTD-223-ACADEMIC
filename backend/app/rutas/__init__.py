"""Endpoints de la API, un modulo por tema. app/main.py los junta.

Cada modulo solo traduce HTTP <-> funciones de app/ (validar la peticion,
revisar permisos, convertir errores en codigos HTTP). La logica vive en los
modulos de app/ (kpis, narrativa, cargas, seguridad...), no aqui.
"""
