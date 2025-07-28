import sqlite3
from flask import Flask, g

app = Flask(__name__)

# Configuración del manejo de la conexión de la base de datos en Flask
def get_db_connection():
    """
    Obtiene una conexión a la base de datos, reutilizando la misma conexión por solicitud si es posible.
    """
    if 'db' not in g:
        g.db = sqlite3.connect('database.db', timeout=5)  # Espera hasta 5 segundos si la base de datos está bloqueada
        g.db.row_factory = sqlite3.Row                   # Devuelve los resultados como diccionarios
        g.db.execute('PRAGMA busy_timeout = 5000')       # Configura tiempo de espera para evitar bloqueos
    return g.db

# Cierre automático de la conexión después de cada solicitud
@app.teardown_appcontext
def close_db_connection(exception):
    """
    Cierra la conexión a la base de datos después de cada solicitud.
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Actualización o inserción de calificaciones
def actualizar_calificacion(user_id, materia_id, nueva_calificacion):
    """
    Actualiza una calificación existente o inserta una nueva si no existe.
    """
    conn = get_db_connection()
    try:
        # Verificar si ya existe la calificación
        query = '''
            SELECT id FROM calificaciones
            WHERE user_id = ? AND materia = ?
        '''
        cur = conn.execute(query, (user_id, materia_id))
        calificacion_existente = cur.fetchone()

        if calificacion_existente:
            # Si existe, actualiza la calificación
            conn.execute('''
                UPDATE calificaciones
                SET calificacion = ?
                WHERE id = ?
            ''', (nueva_calificacion, calificacion_existente['id']))
        else:
            # Si no existe, inserta una nueva calificación
            conn.execute('''
                INSERT INTO calificaciones (user_id, materia, calificacion)
                VALUES (?, ?, ?)
            ''', (user_id, materia_id, nueva_calificacion))

        conn.commit()  # Confirma los cambios
    except Exception as e:
        conn.rollback()  # Revertir cambios en caso de error
        raise e
    finally:
        conn.close()  # Cierra la conexión

# Verificación de duplicados en materias
def verificar_materia_duplicada(nombre, licenciatura, semestre):
    """
    Verifica si una materia duplicada ya existe en la base de datos.
    """
    conn = get_db_connection()
    try:
        query = '''
            SELECT id FROM materias
            WHERE nombre = ? AND licenciatura = ? AND semestre = ?
        '''
        cur = conn.execute(query, (nombre, licenciatura, semestre))
        materia_existente = cur.fetchone()
    finally:
        conn.close()  # Garantiza el cierre de la conexión

    # Retorna True si la materia ya existe
    return materia_existente is not None

# Eliminación de materias duplicadas
def eliminar_materias_duplicadas():
    """
    Elimina materias duplicadas, manteniendo solo una entrada única por grupo de datos.
    """
    conn = get_db_connection()
    try:
        query = '''
            WITH cte AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY nombre, licenciatura, semestre ORDER BY id
                ) AS rn
                FROM materias
            )
            DELETE FROM materias WHERE id IN (
                SELECT id FROM cte WHERE rn > 1
            )
        '''
        conn.execute(query)
        conn.commit()  # Confirmar transacción
    finally:
        conn.close()  # Asegurar cierre de la conexión

    return "Materias duplicadas eliminadas."

# Eliminación de calificaciones duplicadas
def eliminar_calificaciones_duplicadas():
    """
    Elimina calificaciones duplicadas, dejando solo una entrada única para cada user_id y materia.
    """
    conn = get_db_connection()
    try:
        query = '''
            WITH cte AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY user_id, materia ORDER BY id
                ) AS rn
                FROM calificaciones
            )
            DELETE FROM calificaciones WHERE id IN (
                SELECT id FROM cte WHERE rn > 1
            )
        '''
        conn.execute(query)
        conn.commit()  # Confirmar transacción
    finally:
        conn.close()  # Asegurar cierre de la conexión

    return "Calificaciones duplicadas eliminadas."

# Obtención de todas las calificaciones para revisión
def obtener_calificaciones(user_id):
    """
    Obtiene todas las calificaciones de un estudiante específico.
    """
    conn = get_db_connection()
    try:
        query = '''
            SELECT c.calificacion, m.nombre AS materia_nombre
            FROM calificaciones c
            JOIN materias m ON c.materia = m.id
            WHERE c.user_id = ?
        '''
        calificaciones = conn.execute(query, (user_id,)).fetchall()
    finally:
        conn.close()  # Asegurar el cierre de la conexión

    return calificaciones
