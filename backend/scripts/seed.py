"""Genera datos SINTETICOS de RRHH (24 meses) de Nordika Logistica, la
empresa ficticia de la demostracion, y los carga en PostgreSQL.

Nordika Logistica: operador logistico en Guadalajara, ~350 personas.

Uso (desde la carpeta backend, con el entorno virtual activo):
    python -m scripts.seed

ADVERTENCIA: borra y recrea las tablas de db/schema.sql.
Es reproducible: con la misma SEED siempre salen las mismas cifras.
No se generan nombres ni datos personales, solo codigos de empleado.
"""
import random
from datetime import date, timedelta

from sqlalchemy import text

from app.database import DB_URL, ES_REMOTA, RAIZ, ejecutar_sql, engine

SEED = 42
random.seed(SEED)

# Periodo simulado: sep-2024 ... ago-2026 (24 meses completos).
# Se necesitan 24 meses para comparar contra el periodo anterior y contra
# el mismo periodo del anio anterior (seccion 10.1 del PRD).
PRIMER_MES = date(2024, 9, 1)
N_MESES = 24

# Headcount inicial por area. Juridico tiene menos de 5 personas a proposito,
# para mostrar la regla de tamano minimo de grupo (10.3.4).
# El orden y los tamanos no se cambian: con la misma SEED producen las mismas
# cifras, y las pruebas dependen de ellas.
AREAS = {
    "Ventas": 90,
    "Operaciones": 120,
    "Transporte": 60,
    "Finanzas": 40,
    "Almacén": 35,
    "Jurídico": 4,
}
NOMBRE_AREA = {i: nombre for i, nombre in enumerate(AREAS, start=1)}

TASA_BAJA_MENSUAL = 0.014  # ~16% anual, valor normal

# ---- Escenario sembrado: crisis en Operaciones -------------------------
# Primero baja el clima laboral (ene-may 2026) y despues sube la rotacion
# (mar-may 2026). Sirve para probar umbrales (10.3.3) y para que la IA
# distinga correlacion de causalidad (10.3.5).
OLA_BAJAS = {date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)}
TASA_OLA = 0.05
PENALIZACION_CLIMA = {
    date(2026, 1, 1): 2.0,
    date(2026, 2, 1): 2.0,
    date(2026, 3, 1): 2.0,
    date(2026, 4, 1): 1.2,
    date(2026, 5, 1): 1.2,
}
# -------------------------------------------------------------------------


def sumar_meses(d, n):
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


MESES = [sumar_meses(PRIMER_MES, i) for i in range(N_MESES)]


def fin_de_mes(mes):
    return sumar_meses(mes, 1) - timedelta(days=1)


def dia_al_azar(mes):
    return mes + timedelta(days=random.randint(0, (fin_de_mes(mes) - mes).days))


def recortar(x, minimo, maximo):
    return max(minimo, min(maximo, x))


def en_ola(area_id, mes):
    return NOMBRE_AREA[area_id] == "Operaciones" and mes in OLA_BAJAS


# ============================================================
# 1. Empleados, vacantes y candidatos (HRIS + ATS)
# ============================================================
empleados, vacantes, candidatos = [], [], []


def crear_empleado(area_id, fecha_ingreso):
    n = len(empleados) + 1
    emp = {
        "id": n,
        "codigo": f"E{n:04d}",
        "area_id": area_id,
        "fecha_ingreso": fecha_ingreso,
        "fecha_baja": None,
        "tipo_baja": None,
    }
    empleados.append(emp)
    return emp


def crear_vacante(area_id, fecha_apertura, fecha_contratacion):
    vac = {
        "id": len(vacantes) + 1,
        "area_id": area_id,
        "fecha_apertura": fecha_apertura,
        "fecha_contratacion": fecha_contratacion,
        "costo_proceso": round(random.uniform(8000, 25000), 2),
    }
    vacantes.append(vac)

    # Embudo de candidatos: aplicado -> entrevista -> oferta -> contratado
    n_total = random.randint(8, 40)
    etapas = []
    if fecha_contratacion is not None:
        etapas.append("contratado")
        etapas += ["oferta"] * random.randint(0, 2)
    etapas += ["entrevista"] * random.randint(2, 6)
    etapas += ["aplicado"] * max(0, n_total - len(etapas))
    for etapa in etapas:
        candidatos.append(
            {"id": len(candidatos) + 1, "vacante_id": vac["id"], "etapa_final": etapa}
        )


# Plantilla inicial: gente que ya trabajaba en la empresa antes de la simulacion
for area_id, (nombre, headcount) in enumerate(AREAS.items(), start=1):
    for _ in range(headcount):
        crear_empleado(area_id, PRIMER_MES - timedelta(days=random.randint(30, 3650)))

# Simulacion mes a mes: bajas y contrataciones para reemplazarlas
for mes in MESES:
    for area_id, nombre in NOMBRE_AREA.items():
        activos = [
            e for e in empleados
            if e["area_id"] == area_id and e["fecha_baja"] is None and e["fecha_ingreso"] < mes
        ]
        tasa = TASA_OLA if en_ola(area_id, mes) else TASA_BAJA_MENSUAL
        prob_voluntaria = 0.85 if en_ola(area_id, mes) else 0.70

        bajas = [e for e in activos if random.random() < tasa]
        for e in bajas:
            e["fecha_baja"] = dia_al_azar(mes)
            e["tipo_baja"] = "voluntaria" if random.random() < prob_voluntaria else "involuntaria"

        n_contrataciones = len(bajas)
        if nombre != "Jurídico" and random.random() < 0.15:
            n_contrataciones += 1  # crecimiento del area
        # Transporte tarda mas en contratar: operadores con licencia federal
        dias_medios = 55 if nombre == "Transporte" else 35

        for _ in range(n_contrataciones):
            ingreso = dia_al_azar(mes)
            dias = max(10, int(random.gauss(dias_medios, 10)))
            crear_empleado(area_id, ingreso)
            crear_vacante(area_id, ingreso - timedelta(days=dias), ingreso)

        if random.random() < 0.10:  # vacante que sigue abierta
            crear_vacante(area_id, dia_al_azar(mes), None)


def activo_en(e, mes):
    return e["fecha_ingreso"] <= fin_de_mes(mes) and (
        e["fecha_baja"] is None or e["fecha_baja"] >= mes
    )


activos_por_mes = {mes: [e for e in empleados if activo_en(e, mes)] for mes in MESES}

# ============================================================
# 2. Desempeno
# ============================================================
metas = []
for mes in MESES:
    for e in activos_por_mes[mes]:
        asignadas = random.randint(4, 8)
        media = 0.82 - (0.08 if en_ola(e["area_id"], mes) else 0)
        logradas = round(asignadas * recortar(random.gauss(media, 0.15), 0, 1))
        ratio = logradas / asignadas
        if ratio < 0.4:
            calificacion = 1
        elif ratio < 0.6:
            calificacion = 2
        elif ratio < 0.8:
            calificacion = 3
        elif ratio < 0.95:
            calificacion = 4
        else:
            calificacion = 5
        metas.append(
            {
                "id": len(metas) + 1,
                "empleado_id": e["id"],
                "periodo": mes,
                "metas_asignadas": asignadas,
                "metas_logradas": logradas,
                "calificacion": calificacion,
            }
        )

# ============================================================
# 3. Capacitacion (LMS)
# ============================================================
PROGRAMAS_GENERALES = [
    "Seguridad de la información",
    "Cultura y valores",
    "Prevención de riesgos",
    "Ética y cumplimiento",
]
PROGRAMAS_DE_AREA = [
    "Herramientas de trabajo",
    "Habilidades técnicas",
    "Atención a clientes",
    "Gestión del tiempo",
]

programas, inscripciones = [], []
for mes in MESES:
    definiciones = [
        (random.choice(PROGRAMAS_GENERALES), None),  # para toda la empresa
        (random.choice(PROGRAMAS_DE_AREA), random.choice(list(NOMBRE_AREA))),
    ]
    for nombre, area_id in definiciones:
        prog = {
            "id": len(programas) + 1,
            "nombre": nombre,
            "horas": float(random.choice([2, 4, 8, 12, 16])),
            "periodo": mes,
            "area_id": area_id,
        }
        programas.append(prog)
        objetivo = [
            e for e in activos_por_mes[mes] if area_id is None or e["area_id"] == area_id
        ]
        prob_inscripcion = random.uniform(0.55, 0.90)
        for e in objetivo:
            if random.random() < prob_inscripcion:
                completado = random.random() < 0.85
                horas = (
                    prog["horas"]
                    if completado
                    else round(prog["horas"] * random.uniform(0.1, 0.7), 1)
                )
                inscripciones.append(
                    {
                        "id": len(inscripciones) + 1,
                        "programa_id": prog["id"],
                        "empleado_id": e["id"],
                        "completado": completado,
                        "horas_cursadas": horas,
                    }
                )

# ============================================================
# 4. Clima laboral (respuestas anonimas) y 5. Productividad
# ============================================================
DIMENSIONES = ["enps", "satisfaccion", "liderazgo", "carga_trabajo"]
clima, productividad = [], []

for mes in MESES:
    for area_id, nombre in NOMBRE_AREA.items():
        activos_area = [e for e in activos_por_mes[mes] if e["area_id"] == area_id]
        n = len(activos_area)

        penalizacion = PENALIZACION_CLIMA.get(mes, 0) if nombre == "Operaciones" else 0
        for _ in range(round(n * 0.75)):  # ~75% de participacion
            for dim in DIMENSIONES:
                media = (8.0 if dim == "enps" else 7.2) - penalizacion
                puntaje = int(recortar(round(random.gauss(media, 1.8)), 0, 10))
                clima.append(
                    {
                        "id": len(clima) + 1,
                        "area_id": area_id,
                        "periodo": mes,
                        "dimension": dim,
                        "puntaje": puntaje,
                    }
                )

        caida = 0.08 if en_ola(area_id, mes) else 0
        disponibles = n * 160.0
        planificados = max(1, round(n * 2.5))
        productividad.append(
            {
                "id": len(productividad) + 1,
                "area_id": area_id,
                "periodo": mes,
                "horas_efectivas": round(
                    disponibles * recortar(random.gauss(0.72 - caida, 0.04), 0.4, 0.95), 1
                ),
                "horas_disponibles": disponibles,
                "entregables_planificados": planificados,
                "entregables_completados": round(
                    planificados * recortar(random.gauss(0.88 - caida, 0.06), 0.3, 1.0)
                ),
            }
        )


# ============================================================
# Carga en PostgreSQL
# ============================================================
def insertar(conn, tabla, filas):
    if not filas:
        return
    cols = list(filas[0].keys())
    sql = text(
        f"INSERT INTO {tabla} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)})"
    )
    conn.execute(sql, filas)


TABLAS = [
    ("areas", [{"id": i, "nombre": n} for i, n in NOMBRE_AREA.items()]),
    ("empleados", empleados),
    ("vacantes", vacantes),
    ("candidatos", candidatos),
    ("metas_desempeno", metas),
    ("programas_capacitacion", programas),
    ("inscripciones_capacitacion", inscripciones),
    ("respuestas_clima", clima),
    ("productividad", productividad),
]


def cargar():
    esquema = (RAIZ / "db" / "schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        # conexion nativa de psycopg: permite varias sentencias en un solo execute
        conn.connection.driver_connection.execute(esquema)
        for tabla, filas in TABLAS:
            insertar(conn, tabla, filas)
            # los ids se asignaron aqui: avanzar la secuencia para futuros INSERT
            conn.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), "
                    f"(SELECT MAX(id) FROM {tabla}))"
                )
            )


def resumen():
    """Verificacion rapida leyendo desde la base (no desde memoria)."""
    with engine.connect() as conn:
        print("\nFilas cargadas por tabla:")
        for tabla, _ in TABLAS:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar()
            print(f"  {tabla:<28}{n:>8}")

        print("\nHeadcount activo actual por area:")
        filas = conn.execute(
            text(
                "SELECT a.nombre, COUNT(*) FROM empleados e "
                "JOIN areas a ON a.id = e.area_id WHERE e.fecha_baja IS NULL "
                "GROUP BY a.nombre ORDER BY 2 DESC"
            )
        )
        for nombre, n in filas:
            print(f"  {nombre:<14}{n:>5}")

        bajas = dict(
            conn.execute(
                text(
                    "SELECT to_char(date_trunc('month', e.fecha_baja), 'YYYY-MM'), COUNT(*) "
                    "FROM empleados e JOIN areas a ON a.id = e.area_id "
                    "WHERE a.nombre = 'Operaciones' AND e.fecha_baja IS NOT NULL GROUP BY 1"
                )
            ).all()
        )
        enps = dict(
            conn.execute(
                text(
                    "SELECT to_char(r.periodo, 'YYYY-MM'), "
                    "ROUND(100 * (AVG((r.puntaje >= 9)::int) - AVG((r.puntaje <= 6)::int))) "
                    "FROM respuestas_clima r JOIN areas a ON a.id = r.area_id "
                    "WHERE a.nombre = 'Operaciones' AND r.dimension = 'enps' GROUP BY 1"
                )
            ).all()
        )
        print("\nEscenario sembrado - Operaciones (clima baja primero, rotacion despues):")
        print("  mes       bajas   eNPS")
        for mes in MESES[-10:]:
            clave = mes.strftime("%Y-%m")
            print(f"  {clave}   {bajas.get(clave, 0):>4}   {int(enps.get(clave, 0)):>5}")


if __name__ == "__main__":
    if ES_REMOTA:
        # en una base compartida (Supabase) borrar por error afecta a todos
        print(f"ATENCION: vas a BORRAR y recrear las tablas de datos en {DB_URL.host}.")
        print("Los usuarios y las narrativas no se tocan.")
        if input("Escribe BORRAR para continuar: ").strip() != "BORRAR":
            raise SystemExit("Cancelado.")
    print(f"Generando datos sinteticos (SEED={SEED})...")
    cargar()
    ejecutar_sql("rls.sql")  # tablas recien creadas: cerrar la Data API de Supabase
    resumen()
    print("\nListo.")
