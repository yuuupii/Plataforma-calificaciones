from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
import sqlite3
import psycopg2
import psycopg2.extras
import pandas as pd
import plotly.express as px

# módulos propios (deja como estaban)
from materias_util import verificar_materia_duplicada as util_verificar_materia_duplicada, eliminar_materias_duplicadas
from models import Estudiante

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# ---------------------------
# Conexión: Postgres (psycopg2) o SQLite fallback
# ---------------------------
def get_db_connection():
    """
    Devuelve una conexión activa:
    - Si existe DATABASE_URL se intenta conectar via psycopg2 (Postgres).
    - Si no, se usa SQLite local 'database.db'.
    Guardamos la conexión en g.db_conn desde before_request.
    """
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        # SQLite fallback
        conn = sqlite3.connect("database.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn._flavor = "sqlite"
        return conn

    # A veces el URL viene con postgres://, psycopg quiere postgresql://
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    try:
        conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
        conn._flavor = "postgres"
        return conn
    except Exception as e:
        # Si falla Postgres, volvemos a SQLite (para desarrollo local)
        print("⚠️ Error conectando a PostgreSQL, usando SQLite como respaldo:", e)
        conn = sqlite3.connect("database.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn._flavor = "sqlite"
        return conn

# ---------------------------
# Helpers para consultas (adapta placeholders y devuelve dicts)
# ---------------------------
def db_execute(sql, params=None, fetchone=False, fetchall=False, commit=False):
    """
    Ejecuta una consulta usando g.db_conn.
    - Para Postgres usa %s placeholders.
    - Para SQLite usa ? placeholders.
    Devuelve filas en forma de lista/dict según fetch flags.
    """
    conn = g.get("db_conn")
    if conn is None:
        raise RuntimeError("No hay conexión a la base de datos en g.db_conn")

    # Adaptar placeholder para SQLite (si se escribió con %s)
    if getattr(conn, "_flavor", None) == "sqlite":
        # convertir %s -> ? para compatibilidad, SOLO si se usó %s en la query
        sql = sql.replace("%s", "?")

    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
    except Exception as e:
        # Si falla, intentar imprimir la consulta para debug
        cur.close()
        raise

    result = None
    if fetchone:
        result = cur.fetchone()
    elif fetchall:
        result = cur.fetchall()

    if commit:
        conn.commit()

    # Para Postgres con RealDictCursor, los rows ya son dict-like
    # Para SQLite con Row, convertir a dict si se pidieron rows
    if getattr(conn, "_flavor", None) == "sqlite":
        if fetchone and result is not None:
            # sqlite3.Row: convertir a dict
            result = dict(result)
        elif fetchall and result is not None:
            result = [dict(r) for r in result]

    cur.close()
    return result

# ---------------------------
# before_request / teardown para abrir/cerrar conexión en g
# ---------------------------
@app.before_request
def before_request():
    g.db_conn = get_db_connection()

@app.teardown_request
def teardown_request(exception):
    conn = g.pop("db_conn", None)
    try:
        if conn:
            # Si es psycopg2, commit no automático aquí (lo controlamos en helpers)
            conn.close()
    except Exception:
        pass

# ---------------------------
# Inicialización mínima de tablas (idempotente)
# ---------------------------
def inicializar_tablas_minimas():
    """
    Crea tablas básicas si no existen: maestros, administrativos, materias, estudiantes, calificaciones.
    - Usa sintaxis compatible con ambos motores (Postgres/SQLite).
    """
    # maestros, administrativos, materias, estudiantes, calificaciones, licenciaturas_materias
    # Usamos SQL generico: para PK autoincrement en sqlite usamos INTEGER PRIMARY KEY AUTOINCREMENT,
    # en Postgres usamos SERIAL.
    conn = get_db_connection()
    flavor = getattr(conn, "_flavor", None)
    cur = conn.cursor()

    if flavor == "sqlite":
        cur.execute('''
            CREATE TABLE IF NOT EXISTS maestros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                contrasena TEXT NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS administrativos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                contrasena TEXT NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS materias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                licenciatura TEXT NOT NULL,
                semestre INTEGER NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS estudiantes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                matricula TEXT NOT NULL UNIQUE,
                licenciatura TEXT NOT NULL,
                semestre INTEGER NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS calificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                materia INTEGER NOT NULL,
                calificacion INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES estudiantes (id),
                FOREIGN KEY (materia) REFERENCES materias (id)
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS licenciaturas_materias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                licenciatura TEXT NOT NULL,
                semestre INTEGER NOT NULL,
                materia_id INTEGER NOT NULL,
                FOREIGN KEY (materia_id) REFERENCES materias (id)
            );
        ''')
    else:
        # Postgres
        cur.execute('''
            CREATE TABLE IF NOT EXISTS maestros (
                id SERIAL PRIMARY KEY,
                usuario TEXT UNIQUE NOT NULL,
                contrasena TEXT NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS administrativos (
                id SERIAL PRIMARY KEY,
                usuario TEXT UNIQUE NOT NULL,
                contrasena TEXT NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS materias (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                licenciatura TEXT NOT NULL,
                semestre INTEGER NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS estudiantes (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                matricula TEXT NOT NULL UNIQUE,
                licenciatura TEXT NOT NULL,
                semestre INTEGER NOT NULL
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS calificaciones (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                materia INTEGER NOT NULL,
                calificacion INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES estudiantes (id),
                FOREIGN KEY (materia) REFERENCES materias (id)
            );
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS licenciaturas_materias (
                id SERIAL PRIMARY KEY,
                licenciatura TEXT NOT NULL,
                semestre INTEGER NOT NULL,
                materia_id INTEGER NOT NULL,
                FOREIGN KEY (materia_id) REFERENCES materias (id)
            );
        ''')

    conn.commit()
    cur.close()
    conn.close()

# inicializar tablas al arrancar (solo en entorno local o first-run)
inicializar_tablas_minimas()

# ---------------------------
# RUTAS (simplificadas y corregidas)
# ---------------------------

@app.route('/')
def index():
    if 'user_id' in session:
        rol = session.get('usuario_tipo')  # usábamos 'rol' en sitios distintos; unificar nombre
        if rol == 'estudiante':
            return redirect('/panel-alumno')
        elif rol == 'docente':
            return redirect('/panel-docente')
        elif rol == 'admin':
            return redirect('/panel-admin')
    return render_template('seleccionar_rol.html')

@app.route("/test_db")
def test_db():
    try:
        # Un test simple que trabaja con ambos motores
        if getattr(g.db_conn, "_flavor", None) == "postgres":
            res = db_execute("SELECT current_database() as db, current_user as usr", fetchone=True)
            return {"conexion": res}
        else:
            # sqlite: devolver version
            res = db_execute("select sqlite_version() as version", fetchone=True)
            return {"conexion": res}
    except Exception as e:
        return {"error": str(e)}

# --- Registro de usuarios (docentes/administrativos) ---
@app.route('/registrar_usuario', methods=['GET', 'POST'])
def registrar_usuario():
    # Acceso: se espera que solo admin pueda (según tu lógica)
    if session.get('usuario_tipo') != 'admin':
        return redirect(url_for('seleccionar_rol'))

    if request.method == 'POST':
        tipo = request.form.get('tipo', '').strip()
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        if not tipo or not usuario or not contrasena:
            flash('Todos los campos son obligatorios')
            return redirect(url_for('registrar_usuario'))

        tabla = "maestros" if tipo == "docente" else "administrativos" if tipo == "administrativo" else None
        if tabla is None:
            flash('Tipo de usuario no válido')
            return redirect(url_for('registrar_usuario'))

        existe = db_execute(f"SELECT * FROM {tabla} WHERE usuario = %s", (usuario,), fetchone=True)
        if existe:
            flash(f'El usuario "{usuario}" ya está registrado como {tipo}')
            return redirect(url_for('registrar_usuario'))

        contrasena_hash = generate_password_hash(contrasena)
        db_execute(f"INSERT INTO {tabla} (usuario, contrasena) VALUES (%s, %s)", (usuario, contrasena_hash), commit=True)
        flash(f'Usuario "{usuario}" registrado exitosamente como {tipo}')
        return redirect(url_for('registrar_usuario'))

    docentes = db_execute("SELECT id, usuario, contrasena FROM maestros ORDER BY id", fetchall=True) or []
    administrativos = db_execute("SELECT id, usuario, contrasena FROM administrativos ORDER BY id", fetchall=True) or []
    return render_template('registrar_usuario.html', docentes=docentes, administrativos=administrativos)

@app.route('/registro_usuario_publico', methods=['GET', 'POST'])
def registrar_usuario_publico():
    if request.method == 'POST':
        tipo = request.form.get('tipo', '').strip()
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        if not tipo or not usuario or not contrasena:
            flash('Todos los campos son obligatorios')
            return redirect(url_for('registrar_usuario_publico'))

        tabla = "maestros" if tipo == "docente" else "administrativos" if tipo == "administrativo" else None
        if tabla is None:
            flash('Tipo de usuario no válido')
            return redirect(url_for('registrar_usuario_publico'))

        existe = db_execute(f"SELECT * FROM {tabla} WHERE usuario = %s", (usuario,), fetchone=True)
        if existe:
            flash(f'El usuario "{usuario}" ya está registrado como {tipo}')
            return redirect(url_for('registrar_usuario_publico'))

        contrasena_hash = generate_password_hash(contrasena)
        db_execute(f"INSERT INTO {tabla} (usuario, contrasena) VALUES (%s, %s)", (usuario, contrasena_hash), commit=True)
        flash('¡Registro exitoso! Ahora puedes iniciar sesión.')
        return redirect(url_for('login_docente') if tipo == "docente" else url_for('login_admin'))

    return render_template('registrar_usuario_publico.html')

@app.route('/login/docente', methods=['GET', 'POST'])
def login_docente():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        docente = db_execute("SELECT id, usuario, contrasena FROM maestros WHERE usuario = %s", (usuario,), fetchone=True)
        if docente:
            # docente puede ser dict (postgres RealDictCursor) o sqlite dict
            if isinstance(docente, dict):
                pwd_hash = docente['contrasena']
                docente_id = docente['id']
                docente_usuario = docente['usuario']
            else:
                # si devuelve tupla/lista, adaptamos
                docente_id, docente_usuario, pwd_hash = docente

            if check_password_hash(pwd_hash, contrasena):
                session['user_id'] = docente_id
                session['usuario_tipo'] = 'docente'
                session['usuario'] = docente_usuario
                flash(f'Bienvenido, docente {docente_usuario} 👨‍🏫')
                return redirect(url_for('menu_docente'))

        flash('Credenciales incorrectas ❌')
        return redirect(url_for('login_docente'))

    return render_template('login_docente.html')

@app.route('/login/admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        admin = db_execute("SELECT id, usuario, contrasena FROM administrativos WHERE usuario = %s", (usuario,), fetchone=True)
        if admin:
            if isinstance(admin, dict):
                admin_id = admin['id']; admin_usuario = admin['usuario']; admin_pass = admin['contrasena']
            else:
                admin_id, admin_usuario, admin_pass = admin

            if check_password_hash(admin_pass, contrasena):
                session['user_id'] = admin_id
                session['usuario_tipo'] = 'admin'
                session['usuario'] = admin_usuario
                flash(f'Bienvenido, administrador {admin_usuario} 🧑‍💼')
                return redirect(url_for('menu_admin'))

        flash('Credenciales incorrectas ❌')
        return redirect(url_for('login_admin'))

    return render_template('login_admin.html')

@app.route('/menu/admin')
def menu_admin():
    if 'user_id' not in session or session.get('usuario_tipo') != 'admin':
        flash('Acceso restringido. Solo administradores.')
        return redirect(url_for('login_admin'))
    return render_template('menu_admin.html')

@app.route('/seleccionar-rol')
def seleccionar_rol():
    return render_template('seleccionar_rol.html')

# ---------- Estudiantes: login y ver calificaciones ----------
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        matricula = request.form.get('matricula', '').strip()
        usuario = db_execute("SELECT id, nombre, matricula FROM estudiantes WHERE nombre = %s AND matricula = %s", (nombre, matricula), fetchone=True)
        if usuario:
            if isinstance(usuario, dict):
                user_id = usuario['id']
            else:
                user_id = usuario[0]
            session['user_id'] = user_id
            session['usuario_tipo'] = 'estudiante'
            return redirect(url_for('ver_calificaciones'))
        flash('Nombre o matrícula incorrectos')
        return redirect(url_for('login'))
    return render_template('inicio_sesion.html')

@app.route('/ver_calificaciones', methods=['GET'])
def ver_calificaciones():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))

    estudiante = db_execute("SELECT nombre, semestre FROM estudiantes WHERE id = %s", (user_id,), fetchone=True)
    if not estudiante:
        return render_template('calificaciones.html', calificaciones=None)

    if isinstance(estudiante, dict):
        nombre_estudiante = estudiante['nombre']; semestre_actual = estudiante['semestre']
    else:
        nombre_estudiante, semestre_actual = estudiante

    calificaciones = db_execute('''
        SELECT c.calificacion, m.nombre AS materia_nombre
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        WHERE c.user_id = %s AND m.semestre = %s
        ORDER BY m.nombre
    ''', (user_id, semestre_actual), fetchall=True)

    # Si calificaciones vienen como lista de dicts (Postgres) o tuplas (SQLite adaptadas)
    return render_template('calificaciones.html', calificaciones=calificaciones, semestre_actual=semestre_actual)

# Añadir calificación (docente/admin) — ejemplo corregido
@app.route('/add_calificacion', methods=['POST'])
def add_calificacion():
    materia = request.form.get('materia')
    calificacion = request.form.get('calificacion')
    user_id = session.get('user_id')

    if not all([materia, calificacion, user_id]):
        return "Faltan datos", 400

    db_execute("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
               (user_id, materia, calificacion), commit=True)
    return redirect(url_for('ver_calificaciones'))

# Eliminar materia (y sus calificaciones)
@app.route('/delete_materia', methods=['POST'])
def delete_materia():
    materia_id = request.form.get('id')
    if not materia_id:
        return jsonify({'success': False, 'message': 'ID de materia no proporcionado.'})
    db_execute("DELETE FROM calificaciones WHERE materia = %s", (materia_id,), commit=True)
    db_execute("DELETE FROM materias WHERE id = %s", (materia_id,), commit=True)
    return jsonify({'success': True, 'message': 'Materia eliminada con éxito.'})

# Mostrar calificaciones (tabla completa del estudiante)
@app.route('/calificaciones')
def mostrar_calificaciones():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    filas = db_execute('''
        SELECT c.calificacion,
               m.nombre AS materia_nombre,
               m.licenciatura,
               m.semestre,
               e.nombre AS estudiante_nombre,
               e.semestre AS estudiante_semestre
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE c.user_id = %s
        ORDER BY m.licenciatura, m.semestre, m.nombre
    ''', (user_id,), fetchall=True)

    # calcular semestre_actual si hay filas
    if filas:
        # filas puede ser lista de dicts o de tuplas; normalizamos
        if isinstance(filas[0], dict):
            semestre_actual = max([row['semestre'] for row in filas])
        else:
            semestre_actual = max([row[3] for row in filas])
    else:
        semestre_actual = None

    return render_template('calificaciones.html', calificaciones=filas, semestre_actual=semestre_actual)

# Registrar / actualizar calificación (vía formulario)
@app.route('/registrar-calificacion', methods=['GET', 'POST'])
def registrar_calificacion():
    if request.method == 'POST':
        alumno_id = request.form.get('alumno_id')
        materia_id = request.form.get('materia_id')
        calificacion = request.form.get('calificacion')

        try:
            existe = db_execute("SELECT id FROM calificaciones WHERE user_id = %s AND materia = %s",
                                (alumno_id, materia_id), fetchone=True)
            if existe:
                db_execute("UPDATE calificaciones SET calificacion = %s WHERE user_id = %s AND materia = %s",
                           (calificacion, alumno_id, materia_id), commit=True)
                mensaje = '🔄 Calificación actualizada con éxito.'
            else:
                db_execute("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
                           (alumno_id, materia_id, calificacion), commit=True)
                mensaje = '✅ Calificación registrada con éxito.'
        except Exception as e:
            mensaje = f'⚠️ Error al guardar la calificación: {e}'

        return redirect(url_for('registrar_calificacion', mensaje=mensaje))

    mensaje = request.args.get('mensaje')
    alumnos = db_execute("SELECT * FROM estudiantes ORDER BY nombre", fetchall=True) or []
    materias = db_execute("SELECT * FROM materias ORDER BY licenciatura, semestre, nombre", fetchall=True) or []

    # Si filas son dicts (Postgres) quedan listas de dicts; si son tuplas, puedes adaptarlas en plantilla
    return render_template('registrar_calificacion.html', alumnos=alumnos, materias=materias, mensaje=mensaje)

# Guardar (AJAX o normal)
@app.route('/guardar-calificacion', methods=['POST'])
def guardar_calificacion():
    alumno_id = request.form.get('alumno_id')
    materia_id = request.form.get('materia_id')
    calificacion = request.form.get('calificacion')

    try:
        existe = db_execute("SELECT id FROM calificaciones WHERE user_id = %s AND materia = %s",
                            (alumno_id, materia_id), fetchone=True)
        if existe:
            db_execute("UPDATE calificaciones SET calificacion = %s WHERE user_id = %s AND materia = %s",
                       (calificacion, alumno_id, materia_id), commit=True)
            mensaje = '🔄 Calificación actualizada con éxito.'
        else:
            db_execute("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
                       (alumno_id, materia_id, calificacion), commit=True)
            mensaje = '✅ Calificación registrada con éxito.'

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'exito': True, 'mensaje': mensaje})
    except Exception as e:
        mensaje = f'⚠️ Error al guardar la calificación: {e}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'exito': False, 'mensaje': mensaje})

    return redirect(url_for('registrar_calificacion', mensaje=mensaje))

# Funciones administrativas y gestión de materias/alumnos:
@app.route('/alumnos')
def alumnos():
    filas = db_execute("SELECT * FROM estudiantes ORDER BY licenciatura, semestre, nombre", fetchall=True) or []
    # En plantilla puedes iterar sobre filas (dicts o tuplas). Si quieres uniformidad, conviene convertir a dicts.
    return render_template('alumnos.html', alumnos=filas)

@app.route('/add_materia', methods=['POST'])
def add_materia():
    nombre = request.form.get('nombre')
    licenciatura = request.form.get('licenciatura')
    semestre = request.form.get('semestre')

    if not nombre or not licenciatura or not semestre:
        flash('Por favor, completa todos los campos.', 'danger')
        return redirect(url_for('gestion_materias'))

    # usa tu utilidad si prefieres; aquí ejemplo básico
    existe = db_execute("SELECT 1 FROM materias WHERE nombre = %s AND licenciatura = %s AND semestre = %s",
                        (nombre, licenciatura, semestre), fetchone=True)
    if existe:
        flash('La materia ya existe para esa licenciatura y semestre.', 'warning')
        return redirect(url_for('gestion_materias'))

    db_execute("INSERT INTO materias (nombre, licenciatura, semestre) VALUES (%s, %s, %s)",
               (nombre, licenciatura, semestre), commit=True)
    flash('Materia añadida con éxito.', 'success')
    return redirect(url_for('gestion_materias'))

@app.route('/gestion_materias')
def gestion_materias():
    materias_duplicadas = db_execute('''
        SELECT id, nombre, licenciatura, semestre
        FROM materias
        WHERE id NOT IN (
            SELECT MIN(id) FROM materias GROUP BY nombre, licenciatura, semestre
        )
    ''', fetchall=True) or []
    return render_template('gestionar_materias.html', materias_duplicadas=materias_duplicadas)

@app.route('/ver_materias')
def ver_materias():
    materias = db_execute("SELECT * FROM materias ORDER BY licenciatura, semestre, nombre", fetchall=True) or []
    return render_template('ver_materias.html', materias=materias)

@app.route('/eliminar_materia/<int:materia_id>', methods=['POST'])
def eliminar_materia(materia_id):
    db_execute("DELETE FROM calificaciones WHERE materia = %s", (materia_id,), commit=True)
    db_execute("DELETE FROM materias WHERE id = %s", (materia_id,), commit=True)
    flash('Materia eliminada exitosamente.', 'success')
    return redirect(url_for('ver_materias'))

# eliminar duplicados (ejemplo)
@app.route('/eliminar_duplicados', methods=['GET', 'POST'])
def eliminar_duplicados():
    if request.method == 'GET':
        rows = db_execute('''
            WITH cte AS (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id, materia ORDER BY id) AS rn
                FROM calificaciones
            )
            SELECT id FROM cte WHERE rn > 1;
        ''', fetchall=True) or []
        duplicados = [r['id'] if isinstance(r, dict) else r[0] for r in rows]
        detalles = []
        if duplicados:
            # crear placeholders dinámicos según flavor
            placeholders = ",".join(["%s"] * len(duplicados))
            detalles = db_execute(f'''
                SELECT c.id, c.calificacion, m.nombre AS materia_nombre, e.nombre AS estudiante_nombre
                FROM calificaciones c
                JOIN materias m ON c.materia = m.id
                JOIN estudiantes e ON c.user_id = e.id
                WHERE c.id IN ({placeholders})
            ''', tuple(duplicados), fetchall=True)
        return render_template('eliminar_duplicados.html', calificaciones=detalles)
    else:
        ids = request.form.getlist('duplicados')
        for _id in ids:
            db_execute("DELETE FROM calificaciones WHERE id = %s", (_id,), commit=True)
        flash(f'Se eliminaron {len(ids)} calificaciones duplicadas.', 'success')
        return redirect(url_for('eliminar_duplicados'))

# ---------------------------
# Run
# ---------------------------
if __name__ == '__main__':
    # Inicializar tablas en el entorno de ejecución local
    inicializar_tablas_minimas()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
