# app.py
"""
Versión corregida y completa de app.py
- Compatible con PostgreSQL (psycopg2) y fallback a SQLite.
- Usa db_query(...) para todas las consultas (unifica placeholders y cursores).
- Mantiene la estructura y endpoints originales del proyecto.
"""

import os
import sqlite3
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, jsonify, redirect, url_for,
    session, flash, g
)
from werkzeug.security import generate_password_hash, check_password_hash

# carga .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# ---------------------------
# Conexión a DB + helper db_query
# ---------------------------
def get_db_connection():
    """
    Devuelve una conexión a Postgres si DATABASE_URL existe,
    si no, devuelve conexión sqlite3.
    NO modifica atributos internos de la conexión (evita _flavor).
    """
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        # render y otros providers a veces usan postgres:// -> psycopg2 espera postgresql://
        if dsn.startswith("postgres://"):
            dsn = dsn.replace("postgres://", "postgresql://", 1)
        try:
            conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
            # No establecer atributos custom en la conexión
            return conn
        except Exception as e:
            print("❌ Error conectando a PostgreSQL, fallback SQLite:", e)

    # fallback a sqlite
    try:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print("❌ Error conectando a SQLite:", e)
        raise

def _is_sqlite_conn(conn):
    return isinstance(conn, sqlite3.Connection)

def db_query(query, params=None, one=False, commit=False):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(query, params)

    if commit:
        conn.commit()
        cur.close()
        conn.close()
        return True

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows[0] if one and rows else rows

# ---------------------------
# BEFORE / TEARDOWN
# ---------------------------
@app.before_request
def before_request():
    # create/attach a db connection to g
    try:
        g.db_conn = get_db_connection()
    except Exception as e:
        print("Error al abrir conexión:", e)
        return "Error conectando a la base de datos", 500

@app.teardown_request
def teardown_request(exception):
    conn = getattr(g, "db_conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass

# ---------------------------
# Inicialización de tablas mínimas
# ---------------------------
def inicializar_tablas_minimas():
    """
    Crea las tablas principales si no existen.
    Compatible con Postgres y SQLite.
    """
    conn = get_db_connection()
    try:
        if _is_sqlite_conn(conn):
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS maestros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    contrasena TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS administrativos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT UNIQUE NOT NULL,
                    contrasena TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS estudiantes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    matricula TEXT UNIQUE NOT NULL,
                    licenciatura TEXT,
                    semestre INTEGER
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS materias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    licenciatura TEXT NOT NULL,
                    semestre INTEGER NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS calificaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    materia INTEGER NOT NULL,
                    calificacion REAL,
                    FOREIGN KEY(user_id) REFERENCES estudiantes(id),
                    FOREIGN KEY(materia) REFERENCES materias(id)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS licenciaturas_materias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    materia_id INTEGER,
                    licenciatura TEXT,
                    semestre INTEGER
                );
            """)
            conn.commit()
            cur.close()
        else:
            cur = conn.cursor()
            # Postgres: usar SERIAL / small changes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS maestros (
                    id SERIAL PRIMARY KEY,
                    usuario TEXT UNIQUE NOT NULL,
                    contrasena TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS administrativos (
                    id SERIAL PRIMARY KEY,
                    usuario TEXT UNIQUE NOT NULL,
                    contrasena TEXT NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS estudiantes (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    matricula TEXT UNIQUE NOT NULL,
                    licenciatura TEXT,
                    semestre INTEGER
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS materias (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    licenciatura TEXT NOT NULL,
                    semestre INTEGER NOT NULL
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS calificaciones (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    materia INTEGER NOT NULL,
                    calificacion numeric,
                    FOREIGN KEY(user_id) REFERENCES estudiantes(id),
                    FOREIGN KEY(materia) REFERENCES materias(id)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS licenciaturas_materias (
                    id SERIAL PRIMARY KEY,
                    materia_id INTEGER,
                    licenciatura TEXT,
                    semestre INTEGER
                );
            """)
            conn.commit()
            cur.close()
    finally:
        conn.close()

# inicializar tablas al arrancar (solo en ejecución directa)
# NOTA: si usás gunicorn en render, la inicialización puede repetirse en workers.
# Lo hacemos de forma segura (CREATE IF NOT EXISTS).
if __name__ == '__main__':
    inicializar_tablas_minimas()

# ---------------------------
# Rutas
# ---------------------------

@app.route('/')
def index():
    # 🔥 Redirección directa y temporal al menú de administradores
    return redirect(url_for('menu_admin'))

# Mantener endpoint solicitado por plantillas
@app.route('/seleccionar-rol')
def seleccionar_rol():
    return render_template('seleccionar_rol.html')

# --------------------------------------------------
# Menús (docente / admin)
# --------------------------------------------------
@app.route('/menu/docente')
def menu_docente():
    if session.get('usuario_tipo') != 'docente':
        flash('Acceso restringido. Inicia sesión como docente.')
        return redirect(url_for('index'))
    return render_template('menu_docente.html')

@app.route('/menu_admin')
def menu_admin():
    return render_template('menu_admin.html')   # 🔓 ACCESO LIBRE TEMPORAL

# --------------------------------------------------
# Registro y gestión de usuarios (admin crea usuarios)
# --------------------------------------------------
@app.route('/registrar_usuario', methods=['GET', 'POST'])
def registrar_usuario():
    # Seguridad: solo admins pueden acceder
    if session.get('usuario_tipo') != 'admin':
        flash('Acceso restringido. Solo administradores.')
        return redirect(url_for('seleccionar_rol'))

    if request.method == 'POST':
        tipo = request.form.get('tipo', '').strip()
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        if not tipo or not usuario or not contrasena:
            flash('Todos los campos son obligatorios')
            return redirect(url_for('registrar_usuario'))

        tabla = 'maestros' if tipo == 'docente' else 'administrativos' if tipo == 'administrativo' else None
        if tabla is None:
            flash('Tipo de usuario no válido')
            return redirect(url_for('registrar_usuario'))

        existe = db_query(f"SELECT * FROM {tabla} WHERE usuario = %s", (usuario,), one=True)
        if existe:
            flash(f'El usuario "{usuario}" ya está registrado como {tipo}')
            return redirect(url_for('registrar_usuario'))

        contrasena_hash = generate_password_hash(contrasena)
        db_query(f"INSERT INTO {tabla} (usuario, contrasena) VALUES (%s, %s)", (usuario, contrasena_hash), commit=True)
        flash(f'Usuario "{usuario}" registrado exitosamente como {tipo}')
        return redirect(url_for('registrar_usuario'))

    docentes = db_query("SELECT id, usuario, contrasena FROM maestros ORDER BY id", many=True) or []
    administrativos = db_query("SELECT id, usuario, contrasena FROM administrativos ORDER BY id", many=True) or []
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

        tabla = 'maestros' if tipo == 'docente' else 'administrativos' if tipo == 'administrativo' else None
        if tabla is None:
            flash('Tipo de usuario no válido')
            return redirect(url_for('registrar_usuario_publico'))

        existe = db_query(f"SELECT * FROM {tabla} WHERE usuario = %s", (usuario,), one=True)
        if existe:
            flash(f'El usuario "{usuario}" ya está registrado como {tipo}')
            return redirect(url_for('registrar_usuario_publico'))

        contrasena_hash = generate_password_hash(contrasena)
        db_query(f"INSERT INTO {tabla} (usuario, contrasena) VALUES (%s, %s)", (usuario, contrasena_hash), commit=True)
        flash('¡Registro exitoso! Ahora puedes iniciar sesión.')
        return redirect(url_for('login_docente') if tipo == 'docente' else url_for('login_admin'))

    return render_template('registrar_usuario_publico.html')

@app.route('/ver_usuarios')
def ver_usuarios():
    if 'user_id' not in session or session.get('usuario_tipo') != 'admin':
        flash('Acceso restringido')
        return redirect(url_for('login_admin'))

    docentes = db_query("SELECT id, usuario FROM maestros ORDER BY usuario", many=True) or []
    admins = db_query("SELECT id, usuario FROM administrativos ORDER BY usuario", many=True) or []

    tipo = request.args.get('tipo')
    user_id = request.args.get('user_id')
    usuario_editar = None
    tipo_edicion = None
    if tipo in ['docente', 'administrativo'] and user_id:
        tabla = 'maestros' if tipo == 'docente' else 'administrativos'
        usuario_editar = db_query(f"SELECT * FROM {tabla} WHERE id = %s", (user_id,), one=True)
        tipo_edicion = tipo

    return render_template('ver_usuarios.html', docentes=docentes, admins=admins,
                           usuario_editar=usuario_editar, tipo_edicion=tipo_edicion)

@app.route('/eliminar_usuario')
def eliminar_usuario():
    if 'user_id' not in session or session.get('usuario_tipo') != 'admin':
        flash('Acceso restringido. Solo administradores pueden eliminar usuarios.')
        return redirect(url_for('login_admin'))

    tipo = request.args.get('tipo')
    user_id = request.args.get('user_id')

    if tipo not in ['docente', 'administrativo'] or not user_id or not user_id.isdigit():
        flash('Datos inválidos para eliminar usuario ❌')
        return redirect(url_for('registrar_usuario'))

    tabla = 'maestros' if tipo == 'docente' else 'administrativos'
    resultado = db_query(f"SELECT usuario FROM {tabla} WHERE id = %s", (user_id,), one=True)

    if resultado:
        db_query(f"DELETE FROM {tabla} WHERE id = %s", (user_id,), commit=True)
        # resultado puede ser dict o tuple según connector; manejamos ambos
        usuario_str = resultado.get('usuario') if isinstance(resultado, dict) else resultado[0]
        flash(f'Usuario "{usuario_str}" eliminado correctamente ✅')
    else:
        flash('Usuario no encontrado ❌')

    return redirect(url_for('registrar_usuario'))

@app.route('/actualizar_usuario', methods=['POST'])
def actualizar_usuario():
    tipo = request.form.get('tipo')
    user_id = request.form.get('user_id')
    nuevo_usuario = request.form.get('usuario', '').strip()
    nueva_contrasena = request.form.get('contrasena', '').strip()

    if tipo not in ['docente', 'administrativo'] or not user_id or not nuevo_usuario:
        flash('Datos inválidos')
        return redirect(url_for('ver_usuarios'))

    tabla = 'maestros' if tipo == 'docente' else 'administrativos'
    if nueva_contrasena:
        nueva_hash = generate_password_hash(nueva_contrasena)
        db_query(f"UPDATE {tabla} SET usuario = %s, contrasena = %s WHERE id = %s",
                 (nuevo_usuario, nueva_hash, user_id), commit=True)
    else:
        db_query(f"UPDATE {tabla} SET usuario = %s WHERE id = %s",
                 (nuevo_usuario, user_id), commit=True)

    flash('✅ Usuario actualizado correctamente')
    return redirect(url_for('ver_usuarios'))

# --------------------------------------------------
# Cambiar contraseña (docente/admin)
# --------------------------------------------------
@app.route('/cambiar-contrasena', methods=['GET', 'POST'])
def cambiar_contrasena():
    if 'user_id' not in session or session.get('usuario_tipo') not in ['docente', 'admin']:
        flash('Acceso restringido.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        actual = request.form.get('contrasena_actual', '').strip()
        nueva = request.form.get('nueva_contrasena', '').strip()
        confirmar = request.form.get('confirmar_contrasena', '').strip()

        # buscamos en maestros (si es docente)
        if session.get('usuario_tipo') == 'docente':
            docente = db_query("SELECT contrasena FROM maestros WHERE id = %s", (session['user_id'],), one=True)
            hashed = docente.get('contrasena') if isinstance(docente, dict) else (docente[0] if docente else None)
            if not hashed or not check_password_hash(hashed, actual):
                flash('❌ La contraseña actual no es correcta.')
                return redirect(url_for('cambiar_contrasena'))
        else:
            # admin: buscar en administrativos
            admin = db_query("SELECT contrasena FROM administrativos WHERE id = %s", (session['user_id'],), one=True)
            hashed = admin.get('contrasena') if isinstance(admin, dict) else (admin[0] if admin else None)
            if not hashed or not check_password_hash(hashed, actual):
                flash('❌ La contraseña actual no es correcta.')
                return redirect(url_for('cambiar_contrasena'))

        if nueva != confirmar:
            flash('⚠️ Las nuevas contraseñas no coinciden.')
            return redirect(url_for('cambiar_contrasena'))

        if not nueva:
            flash('🚫 La nueva contraseña no puede estar vacía.')
            return redirect(url_for('cambiar_contrasena'))

        nueva_hash = generate_password_hash(nueva)
        if session.get('usuario_tipo') == 'docente':
            db_query("UPDATE maestros SET contrasena = %s WHERE id = %s", (nueva_hash, session['user_id']), commit=True)
        else:
            db_query("UPDATE administrativos SET contrasena = %s WHERE id = %s", (nueva_hash, session['user_id']), commit=True)

        flash('✅ Contraseña actualizada con éxito.')
        return redirect(url_for('cambiar_contrasena'))

    return render_template('cambiar_contrasena.html', tipo=session.get('usuario_tipo'))

# --------------------------------------------------
# Logouts y sesiones
# --------------------------------------------------
@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada exitosamente')
    return redirect(url_for('seleccionar_rol'))

# --------------------------------------------------
# Login docente/admin/estudiante
# --------------------------------------------------
@app.route('/login/docente', methods=['GET', 'POST'])
def login_docente():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contrasena = request.form.get('contrasena', '').strip()

        docente = db_query("SELECT * FROM maestros WHERE usuario = %s", (usuario,), one=True)
        if docente:
            hashed = docente.get('contrasena') if isinstance(docente, dict) else docente[2]
            docente_id = docente.get('id') if isinstance(docente, dict) else docente[0]
            docente_usuario = docente.get('usuario') if isinstance(docente, dict) else docente[1]
            if hashed and check_password_hash(hashed, contrasena):
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

        admin = db_query(
            "SELECT id, usuario, contrasena FROM administrativos WHERE usuario = %s",
            (usuario,),
            one=True
        )

        if admin:
            hashed = admin['contrasena']
            if check_password_hash(hashed, contrasena):
                session['user_id'] = admin['id']
                session['usuario_tipo'] = 'admin'
                session['usuario'] = admin['usuario']
                flash(f"Bienvenido, administrador {admin['usuario']} 🧑‍💼")
                return redirect(url_for('menu_admin'))

        flash('Credenciales incorrectas ❌')
        return redirect(url_for('login_admin'))

    return render_template('login_admin.html')

# Student login: endpoint name used in templates puede variar.
# Nosotros definimos dos endpoints por compatibilidad:
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        matricula = request.form.get('matricula', '').strip()
        user = db_query("SELECT id, nombre, matricula, semestre, licenciatura FROM estudiantes WHERE nombre = %s AND matricula = %s",
                        (nombre, matricula), one=True)
        if user:
            # user is dict
            session['user_id'] = user.get('id') if isinstance(user, dict) else user[0]
            session['usuario_tipo'] = 'estudiante'
            session['usuario'] = user.get('nombre') if isinstance(user, dict) else user[1]
            return redirect(url_for('ver_calificaciones'))
        else:
            flash('Nombre o matrícula incorrectos ❌')
            return redirect(url_for('login'))
    return render_template('inicio_sesion.html')

# an alias para compatibilidad con templates que pedían mostrar_login_estudiante
@app.route('/mostrar_login_estudiante')
def mostrar_login_estudiante():
    return redirect(url_for('login'))

# --------------------------------------------------
# Dashboard (ejemplo con plotly)
# --------------------------------------------------
@app.route('/dashboard')
def dashboard():
    calificaciones = db_query("SELECT * FROM calificaciones", many=True) or []
    if not calificaciones:
        return render_template('dashboard.html', graph_html=None)
    # construimos DataFrame cuidando las keys
    import pandas as pd
    df = pd.DataFrame(calificaciones)
    import plotly.express as px
    fig = px.histogram(df, x='calificacion', nbins=10, title='Distribución de Calificaciones')
    graph_html = fig.to_html(full_html=False)
    return render_template('dashboard.html', graph_html=graph_html)

# --------------------------------------------------
# Ver y gestionar calificaciones (varias rutas)
# --------------------------------------------------
@app.route('/ver_calificaciones', methods=['GET'])
def ver_calificaciones():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('index'))

        estudiante = db_query("SELECT nombre, semestre FROM estudiantes WHERE id = %s", (user_id,), one=True)
        if not estudiante:
            return render_template('calificaciones.html', calificaciones=None)

        nombre_estudiante = estudiante.get('nombre') if isinstance(estudiante, dict) else estudiante[0]
        semestre_actual = estudiante.get('semestre') if isinstance(estudiante, dict) else estudiante[1]

        calificaciones = db_query('''
            SELECT c.calificacion, m.nombre AS materia_nombre, %s AS estudiante_nombre, %s AS estudiante_semestre, m.semestre
            FROM calificaciones c
            JOIN materias m ON c.materia = m.id
            WHERE c.user_id = %s AND m.semestre = %s
        ''', (nombre_estudiante, semestre_actual, user_id, semestre_actual), many=True)

        return render_template('calificaciones.html', calificaciones=calificaciones, semestre_actual=semestre_actual)
    except Exception as e:
        return f"Ha ocurrido un error: {str(e)}", 500

@app.route('/add_calificacion', methods=['POST'])
def add_calificacion():
    try:
        materia = request.form.get('materia')
        calificacion = request.form.get('calificacion')
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('login'))
        db_query("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
                 (user_id, materia, calificacion), commit=True)
        return redirect(url_for('ver_calificaciones'))
    except Exception as e:
        print("Error al añadir calificación:", e)
        return str(e), 500

@app.route('/guardar-calificacion', methods=['POST'])
def guardar_calificacion():
    alumno_id = request.form.get('alumno_id')
    materia_id = request.form.get('materia_id')
    calificacion = request.form.get('calificacion')

    try:
        registro = db_query("SELECT id FROM calificaciones WHERE user_id = %s AND materia = %s",
                            (alumno_id, materia_id), one=True)
        if registro:
            # registro es dict
            registro_id = registro.get('id') if isinstance(registro, dict) else registro[0]
            db_query("UPDATE calificaciones SET calificacion = %s WHERE id = %s", (calificacion, registro_id), commit=True)
            mensaje = '🔄 Calificación actualizada con éxito.'
        else:
            db_query("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
                     (alumno_id, materia_id, calificacion), commit=True)
            mensaje = '✅ Calificación registrada con éxito.'

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'exito': True, 'mensaje': mensaje})
        return redirect(url_for('registrar_calificacion', mensaje=mensaje))
    except Exception as e:
        mensaje = f'⚠️ Error al guardar la calificación: {e}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'exito': False, 'mensaje': mensaje})
        return redirect(url_for('registrar_calificacion', mensaje=mensaje))

# --------------------------------------------------
# Eliminar materia (AJAX)
# --------------------------------------------------
@app.route('/delete_materia', methods=['POST'])
def delete_materia():
    try:
        materia_id = request.form.get('id')
        if not materia_id:
            return jsonify({'success': False, 'message': 'ID de materia no proporcionado.'})
        db_query("DELETE FROM materias WHERE id = %s", (materia_id,), commit=True)
        db_query("DELETE FROM calificaciones WHERE materia = %s", (materia_id,), commit=True)
        return jsonify({'success': True, 'message': 'Materia eliminada con éxito.'})
    except Exception as e:
        print("Error al eliminar materia:", e)
        return jsonify({'success': False, 'message': str(e)})

# --------------------------------------------------
# Mostrar calificaciones (panel) - para usuario autenticado
# --------------------------------------------------
@app.route('/calificaciones')
def mostrar_calificaciones():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    calificaciones = db_query('''
        SELECT c.calificacion, m.nombre AS materia_nombre, m.licenciatura, m.semestre,
               e.nombre AS estudiante_nombre, e.semestre AS estudiante_semestre
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE c.user_id = %s
    ''', (user_id,), many=True) or []
    # semestre_actual: tomar máximo de columna semestre (índice 'semestre')
    semestre_actual = max([row.get('semestre') if isinstance(row, dict) else row[3] for row in calificaciones]) if calificaciones else None
    return render_template('calificaciones.html', calificaciones=calificaciones, semestre_actual=semestre_actual)

# --------------------------------------------------
# Registrar calificación (vista para docentes/admin)
# --------------------------------------------------
@app.route('/registrar-calificacion', methods=['GET', 'POST'])
def registrar_calificacion():
    if request.method == 'POST':
        alumno_id = request.form.get('alumno_id')
        materia_id = request.form.get('materia_id')
        calificacion = request.form.get('calificacion')
        try:
            registro = db_query("SELECT id FROM calificaciones WHERE user_id = %s AND materia = %s",
                                (alumno_id, materia_id), one=True)
            if registro:
                registro_id = registro.get('id') if isinstance(registro, dict) else registro[0]
                db_query("UPDATE calificaciones SET calificacion = %s WHERE id = %s",
                         (calificacion, registro_id), commit=True)
                mensaje = '🔄 Calificación actualizada con éxito.'
            else:
                db_query("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
                         (alumno_id, materia_id, calificacion), commit=True)
                mensaje = '✅ Calificación registrada con éxito.'
        except Exception as e:
            mensaje = f'⚠️ Error al guardar la calificación: {str(e)}'
        return redirect(url_for('registrar_calificacion', mensaje=mensaje))

    mensaje = request.args.get('mensaje')
    alumnos_sql = db_query("SELECT * FROM estudiantes", many=True) or []
    materias_sql = db_query("SELECT * FROM materias", many=True) or []

    # convertir (ya devuelto como dicts por db_query)
    alumnos = alumnos_sql
    materias = materias_sql

    alumnos_agrupados = {}
    for alumno in alumnos:
        lic = alumno.get('licenciatura')
        sem = alumno.get('semestre')
        alumnos_agrupados.setdefault(lic, {}).setdefault(sem, []).append(alumno)

    for lic in alumnos_agrupados:
        for sem in alumnos_agrupados[lic]:
            alumnos_agrupados[lic][sem].sort(key=lambda x: x.get('nombre', ''))

    return render_template('registrar_calificacion.html',
                           alumnos=alumnos,
                           materias=materias,
                           mensaje=mensaje,
                           alumnos_agrupados=alumnos_agrupados)

# --------------------------------------------------
# Actualizar semestres alumnos (bulk)
# --------------------------------------------------
@app.route('/actualizar_semestre_alumnos', methods=['POST'])
def actualizar_semestre_alumnos():
    licenciatura = request.form.get('licenciatura')
    semestre_actual = request.form.get('semestre_actual')
    semestre_destino = request.form.get('semestre_destino')

    if not (licenciatura and semestre_actual and semestre_destino):
        return "Faltan datos", 400
    try:
        semestre_actual_int = int(semestre_actual)
        semestre_destino_int = int(semestre_destino)
    except ValueError:
        return "Semestres deben ser números", 400
    if semestre_destino_int < 1:
        return "El semestre destino no puede ser menor que 1", 400

    # Ejecutar actualización
    db_query("UPDATE estudiantes SET semestre = %s WHERE licenciatura = %s AND semestre = %s",
             (semestre_destino_int, licenciatura, semestre_actual_int), commit=True)

    return jsonify({'mensaje': 'Semestres actualizados correctamente'})

# --------------------------------------------------
# Historial académico
# --------------------------------------------------
@app.route('/historial')
def historial_academico():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    resultado = db_query('''
        SELECT m.licenciatura, m.semestre, m.nombre AS materia, c.calificacion
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        WHERE c.user_id = %s
        ORDER BY m.licenciatura, m.semestre, m.nombre
    ''', (user_id,), many=True) or []

    historial = {}
    promedios_por_semestre = {}
    for fila in resultado:
        lic = fila.get('licenciatura')
        sem = int(fila.get('semestre') or 0)
        historial.setdefault(lic, {}).setdefault(sem, []).append({
            'materia': fila.get('materia'),
            'calificacion': fila.get('calificacion')
        })
        promedios_por_semestre.setdefault(sem, []).append(fila.get('calificacion') or 0)

    promedios_por_semestre = {sem: round(sum(califs) / len(califs), 1) if califs else 0
                              for sem, califs in promedios_por_semestre.items()}

    return render_template('historial_academico.html',
                           historial=historial,
                           promedios_por_semestre=promedios_por_semestre)

@app.route('/ver_historial/<int:estudiante_id>')
def ver_historial_estudiante(estudiante_id):
    resultado = db_query('''
        SELECT e.nombre AS estudiante, m.licenciatura, m.semestre, m.nombre AS materia, c.calificacion
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE c.user_id = %s
        ORDER BY m.licenciatura, m.semestre, m.nombre
    ''', (estudiante_id,), many=True) or []

    if not resultado:
        flash('Este estudiante aún no tiene calificaciones registradas.', 'warning')
        return redirect(url_for('alumnos'))

    historial = {}
    promedios_por_semestre = {}
    for fila in resultado:
        lic = fila.get('licenciatura')
        sem = int(fila.get('semestre') or 0)
        historial.setdefault(lic, {}).setdefault(sem, []).append({
            'materia': fila.get('materia'),
            'calificacion': fila.get('calificacion')
        })
        promedios_por_semestre.setdefault(sem, []).append(fila.get('calificacion') or 0)

    promedios_por_semestre = {sem: round(sum(califs) / len(califs), 1) if califs else 0
                              for sem, califs in promedios_por_semestre.items()}

    nombre_estudiante = resultado[0].get('estudiante') if resultado else None
    return render_template('historial_academico.html',
                           estudiante=nombre_estudiante,
                           historial=historial,
                           promedios_por_semestre=promedios_por_semestre)

# --------------------------------------------------
# Update calificacion via form (buscar alumno por nombre/licenciatura/semestre)
# --------------------------------------------------
@app.route('/update_calificacion', methods=['POST'])
def update_calificacion():
    nombre_alumno = request.form.get('nombre_alumno')
    licenciatura = request.form.get('licenciatura')
    semestre = request.form.get('semestre')
    materia_id = request.form.get('materia_calificar')
    calificacion = request.form.get('calificacion')

    alumno = db_query('SELECT id FROM estudiantes WHERE nombre = %s AND licenciatura = %s AND semestre = %s',
                      (nombre_alumno, licenciatura, semestre), one=True)
    if not alumno:
        return "Alumno no encontrado", 404
    alumno_id = alumno.get('id') if isinstance(alumno, dict) else alumno[0]

    calificacion_existente = db_query('SELECT id FROM calificaciones WHERE user_id = %s AND materia = %s',
                                     (alumno_id, materia_id), one=True)
    if calificacion_existente:
        cal_id = calificacion_existente.get('id') if isinstance(calificacion_existente, dict) else calificacion_existente[0]
        db_query('UPDATE calificaciones SET calificacion = %s WHERE id = %s', (calificacion, cal_id), commit=True)
    else:
        db_query('INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)',
                 (alumno_id, materia_id, calificacion), commit=True)
    return redirect(url_for('ver_calificaciones'))

# --------------------------------------------------
# Alumnos - listados y CRUD
# --------------------------------------------------
@app.route('/alumnos')
def alumnos():
    alumnos = db_query("SELECT * FROM estudiantes", many=True) or []
    alumnos_por_licenciatura = {}
    for alumno in alumnos:
        lic = alumno.get('licenciatura')
        sem = alumno.get('semestre')
        alumnos_por_licenciatura.setdefault(lic, {}).setdefault(sem, []).append(alumno)
    return render_template('alumnos.html', alumnos=alumnos_por_licenciatura)

@app.route('/datos_alumnos', methods=['POST'])
def datos_alumnos():
    nombre = request.form.get('nombre')
    matricula = request.form.get('matricula')
    licenciatura = request.form.get('licenciatura')
    semestre = request.form.get('semestre')

    alumno_existente = db_query("SELECT * FROM estudiantes WHERE matricula = %s", (matricula,), one=True)
    if alumno_existente:
        db_query('UPDATE estudiantes SET nombre = %s, licenciatura = %s, semestre = %s WHERE matricula = %s',
                 (nombre, licenciatura, semestre, matricula), commit=True)
        mensaje = f'🔄 Alumno actualizado al {semestre}° semestre.'
    else:
        db_query('INSERT INTO estudiantes (nombre, matricula, licenciatura, semestre) VALUES (%s, %s, %s, %s)',
                 (nombre, matricula, licenciatura, semestre), commit=True)
        mensaje = f'✅ Alumno registrado correctamente.'
    return redirect(url_for('registrar_calificacion', mensaje=mensaje))

@app.route('/delete_alumno', methods=['POST'])
def delete_alumno():
    alumno_id = request.form.get('id')
    db_query("DELETE FROM estudiantes WHERE id = %s", (alumno_id,), commit=True)
    return redirect(url_for('alumnos'))

# --------------------------------------------------
# Materias - CRUD y vistas
# --------------------------------------------------
@app.route('/add_materia', methods=['POST'])
def add_materia():
    nombre = request.form.get('nombre')
    licenciatura = request.form.get('licenciatura')
    semestre = request.form.get('semestre')

    if not nombre or not licenciatura or not semestre:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return 'Faltan campos', 400
        flash('Por favor, completa todos los campos.', 'danger')
        return redirect(url_for('gestion_materias'))

    if verificar_materia_duplicada(nombre, licenciatura, semestre):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return 'Duplicado', 409
        flash('La materia ya existe para esa licenciatura y semestre.', 'warning')
        return redirect(url_for('gestion_materias'))

    try:
        db_query("INSERT INTO materias (nombre, licenciatura, semestre) VALUES (%s, %s, %s)",
                 (nombre, licenciatura, semestre), commit=True)
        # opcional: tabla licenciaturas_materias
        try:
            db_query("INSERT INTO licenciaturas_materias (materia_id, licenciatura, semestre) VALUES (%s, %s, %s)",
                     (None, licenciatura, semestre), commit=True)
        except Exception:
            pass

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return 'Materia añadida', 200
        flash('Materia añadida con éxito.', 'success')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return f'Error: {str(e)}', 500
        flash(f'Ocurrió un error al añadir la materia: {e}', 'danger')
    return redirect(url_for('gestion_materias'))

def verificar_materia_duplicada(nombre, licenciatura, semestre):
    resultado = db_query('SELECT 1 FROM materias WHERE nombre = %s AND licenciatura = %s AND semestre = %s',
                         (nombre, licenciatura, semestre), one=True)
    return resultado is not None

@app.route('/gestion_materias')
def gestion_materias():
    materias_duplicadas = db_query('''
        SELECT id, nombre, licenciatura, semestre
        FROM materias
        WHERE id NOT IN (
            SELECT MIN(id) FROM materias GROUP BY nombre, licenciatura, semestre
        )
    ''', many=True) or []
    return render_template('gestionar_materias.html', materias_duplicadas=materias_duplicadas)

@app.route('/ver_materias')
def ver_materias():
    materias = db_query("SELECT * FROM materias ORDER BY licenciatura, semestre, nombre", many=True) or []
    estructura = {}
    for m in materias:
        lic = m.get('licenciatura')
        sem = str(m.get('semestre'))
        estructura.setdefault(lic, {}).setdefault(sem, []).append(m)
    for lic in estructura:
        for s in range(1, 8):
            estructura[lic].setdefault(str(s), [])
    return render_template('ver_materias.html', materias=estructura)

@app.route('/eliminar_materia/<int:materia_id>', methods=['POST'])
def eliminar_materia(materia_id):
    db_query("DELETE FROM materias WHERE id = %s", (materia_id,), commit=True)
    flash('Materia eliminada exitosamente.', 'success')
    return redirect(url_for('ver_materias'))

@app.route('/obtener_materias', methods=['GET'])
def obtener_materias():
    licenciatura = request.args.get('licenciatura')
    semestre = request.args.get('semestre')
    materias = db_query('''
        SELECT m.id, m.nombre FROM materias m
        JOIN licenciaturas_materias lm ON m.id = lm.materia_id
        WHERE lm.licenciatura = %s AND lm.semestre = %s
    ''', (licenciatura, semestre), many=True) or []
    materias_list = [{'id': m.get('id'), 'nombre': m.get('nombre')} for m in materias]
    return jsonify({'materias': materias_list})

# --------------------------------------------------
# Materias calificadas por usuario/licenciatura/semestre
# --------------------------------------------------
@app.route('/materias_calificadas', methods=['GET'])
def materias_calificadas():
    user_id = request.args.get('user_id')
    licenciatura = request.args.get('licenciatura')
    semestre = request.args.get('semestre')
    materias = db_query('''
        SELECT c.calificacion, m.nombre AS materia_nombre, m.semestre, e.nombre AS estudiante_nombre, e.licenciatura
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE e.id = %s AND e.licenciatura = %s AND m.semestre = %s
        ORDER BY m.semestre
    ''', (user_id, licenciatura, semestre), many=True) or []
    return render_template('materias_calificadas.html', materias=materias, user_id=user_id)

# --------------------------------------------------
# Editar calificación
# --------------------------------------------------
@app.route('/editar_calificacion/<int:calificacion_id>', methods=['GET', 'POST'])
def editar_calificacion(calificacion_id):
    if request.method == 'POST':
        nueva_calificacion = request.form.get('calificacion')
        db_query("UPDATE calificaciones SET calificacion = %s WHERE id = %s", (nueva_calificacion, calificacion_id), commit=True)
        flash('Calificación actualizada correctamente.', 'success')
        user_id = request.form.get('user_id')
        return redirect(url_for('ver_calificaciones', user_id=user_id))
    calificacion = db_query("SELECT * FROM calificaciones WHERE id = %s", (calificacion_id,), one=True)
    return render_template('editar_calificacion.html', calificacion=calificacion)

# --------------------------------------------------
# Eliminar duplicados en calificaciones
# --------------------------------------------------
@app.route('/eliminar_duplicados', methods=['GET', 'POST'])
def eliminar_duplicados():
    if request.method == 'GET':
        ids_duplicados = db_query('''
            WITH cte AS (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id, materia ORDER BY id) AS rn
                FROM calificaciones
            )
            SELECT id FROM cte WHERE rn > 1;
        ''', many=True) or []
        duplicados_ids = [r.get('id') for r in ids_duplicados]
        calificaciones_duplicadas = []
        if duplicados_ids:
            # build placeholders automatically in db_query by passing tuple; db_query handles sqlite/psql placeholders
            placeholders = ','.join(['%s'] * len(duplicados_ids))
            calificaciones_duplicadas = db_query(f'''
                SELECT c.id, c.calificacion, m.nombre AS materia_nombre, e.nombre AS estudiante_nombre
                FROM calificaciones c
                JOIN materias m ON c.materia = m.id
                JOIN estudiantes e ON c.user_id = e.id
                WHERE c.id IN ({placeholders})
            ''', tuple(duplicados_ids), many=True) or []
        return render_template('eliminar_duplicados.html', calificaciones=calificaciones_duplicadas)

    # POST: eliminar seleccionados
    duplicados_ids = request.form.getlist('duplicados')
    if not duplicados_ids:
        flash('No se seleccionó ninguna calificación para eliminar.', 'danger')
        return redirect(url_for('eliminar_duplicados'))
    for id_ in duplicados_ids:
        db_query("DELETE FROM calificaciones WHERE id = %s", (id_,), commit=True)
    flash(f'Se eliminaron {len(duplicados_ids)} calificaciones duplicadas.', 'success')
    return redirect(url_for('eliminar_duplicados'))

# --------------------------------------------------
# Inicializar materias para alumno (helper)
# --------------------------------------------------
def inicializar_materias_para_alumno(alumno_id, licenciatura, semestre):
    materias = db_query("SELECT id FROM materias WHERE licenciatura = %s AND semestre = %s",
                       (licenciatura, semestre), many=True) or []
    for materia in materias:
        mid = materia.get('id')
        db_query("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
                 (alumno_id, mid, 0), commit=True)

# --------------------------------------------------
# Gestión y eliminación de materias duplicadas (vista)
# --------------------------------------------------
@app.route('/gestionar_materias', methods=['GET', 'POST'])
def gestionar_materias_view():
    if request.method == 'POST':
        ids_para_eliminar = request.form.getlist('materias_eliminar')
        for materia_id in ids_para_eliminar:
            db_query("DELETE FROM materias WHERE id = %s", (materia_id,), commit=True)
        flash('Las materias seleccionadas han sido eliminadas.', 'success')
        return redirect(url_for('gestionar_materias_view'))
    materias_duplicadas = db_query('''
        SELECT id, nombre, licenciatura, semestre
        FROM materias
        WHERE id NOT IN (
            SELECT MIN(id) FROM materias GROUP BY nombre, licenciatura, semestre
        )
    ''', many=True) or []
    return render_template('gestionar_materias.html', materias_duplicadas=materias_duplicadas)

# --------------------------------------------------
# test_db route simple
# --------------------------------------------------
@app.route('/test_db')
def test_db():
    try:
        # solo como prueba, distinto para sqlite/psql
        if _is_sqlite_conn(g.db_conn):
            return {"conexion": "sqlite"}
        else:
            cur = g.db_conn.cursor()
            cur.execute("SELECT current_database(), current_user;")
            res = cur.fetchall()
            cur.close()
            return {"conexion": res}
    except Exception as e:
        return {"error": str(e)}

# --------------------------------------------------
# Run app (solo si se ejecuta directamente)
# --------------------------------------------------
if __name__ == '__main__':
    # inicializa tablas si no existen
    inicializar_tablas_minimas()
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
