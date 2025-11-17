from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from markupsafe import Markup
import os
import sqlite3
import psycopg2
import json
import plotly.express as px
import pandas as pd
from dotenv import load_dotenv
from materias_util import verificar_materia_duplicada, eliminar_materias_duplicadas
from models import Estudiante

# Cargar variables de entorno desde .env
load_dotenv()

# Verificación temporal (puedes quitarlo después de confirmar que funciona)
print("DATABASE_URL:", os.getenv("DATABASE_URL"))

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Conexión a la base de datos (PostgreSQL en Railway o SQLite local)
def get_db_connection():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        # Si no hay DATABASE_URL, usar SQLite como respaldo
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn

    # Render a veces usa formato postgres:// viejo
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)

    try:
        conn = psycopg2.connect(dsn)
        print("✅ Conexión exitosa a PostgreSQL")
        return conn
    except Exception as e:
        print("❌ Error conectando a PostgreSQL, usando SQLite:", e)
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn

# Función auxiliar para ejecutar consultas
def query(sql, params=None, fetchone=False, fetchall=False, commit=False):
    cur = g.db_conn.cursor()

    # Ajustar placeholder si es SQLite
    if isinstance(g.db_conn, sqlite3.Connection):
        sql = sql.replace("%s", "?")

    cur.execute(sql, params or ())

    result = None
    if fetchone:
        result = cur.fetchone()
    elif fetchall:
        result = cur.fetchall()

    if commit:
        g.db_conn.commit()

    cur.close()
    return result

@app.before_request
def before_request():
    try:
        g.db_conn = get_db_connection()
    except Exception as e:
        print("❌ Error conectando a la base de datos:", e)
        return "Error conectando a la base de datos", 500

@app.teardown_request
def teardown_request(exception):
    db_conn = getattr(g, 'db_conn', None)
    if db_conn is not None:
        db_conn.close()

def verificar_datos_materias():
    with app.app_context():
        conn = get_db_connection()
        cur = conn.cursor()

        # ✅ Crear la tabla si no existe
        if isinstance(conn, sqlite3.Connection):
            cur.execute('''
                CREATE TABLE IF NOT EXISTS materias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT NOT NULL,
                    licenciatura TEXT NOT NULL,
                    semestre INTEGER NOT NULL
                );
            ''')
        else:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS materias (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    licenciatura TEXT NOT NULL,
                    semestre INTEGER NOT NULL
                );
            ''')

        conn.commit()
        cur.execute("SELECT * FROM materias;")
        materias = cur.fetchall()
        cur.close()
        conn.close()
        return materias

def inicializar_base_datos():
    conn = get_db_connection()
    cur = conn.cursor()

    if isinstance(conn, sqlite3.Connection):
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
    else:
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

    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    # Si ya hay sesión activa, redirige al panel correcto
    if 'user_id' in session:
        rol = session.get('rol')
        if rol == 'alumno':
            return redirect('/panel-alumno')
        elif rol == 'docente':
            return redirect('/panel-docente')
        elif rol == 'admin':
            return redirect('/panel-admin')
    
    # Si no hay sesión, mostrar selección de rol
    return render_template('seleccionar_rol.html')

@app.route("/test_db")
def test_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT current_database(), current_user;")
        result = cur.fetchall()
        cur.close()
        conn.close()
        return {"conexion": result}
    except Exception as e:
        return {"error": str(e)}

@app.route('/menu/docente')
def menu_docente():
    return render_template('menu_docente.html')

@app.route('/registrar_usuario', methods=['GET', 'POST'])
def registrar_usuario():
    # Seguridad: solo admins pueden acceder
    if session.get('usuario_tipo') != 'admin':
        return redirect(url_for('seleccionar_rol'))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        tipo = request.form['tipo'].strip()
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()

        # Validación de campos vacíos
        if not tipo or not usuario or not contrasena:
            flash('Todos los campos son obligatorios')
            return redirect(url_for('registrar_usuario'))

        # Validación de duplicados
        if tipo == 'docente':
            existe = query("SELECT * FROM maestros WHERE usuario = %s", (usuario,), fetchone=True)
        elif tipo == 'administrativo':
            existe = query("SELECT * FROM administrativos WHERE usuario = %s", (usuario,), fetchone=True)
        else:
            flash('Tipo de usuario no válido')
            return redirect(url_for('registrar_usuario'))

        if existe:
            flash(f'El usuario "{usuario}" ya está registrado como {tipo}')
            return redirect(url_for('registrar_usuario'))

        # Encriptar contraseña antes de guardar
        contrasena_hash = generate_password_hash(contrasena)

        if tipo == 'docente':
            query("INSERT INTO maestros (usuario, contrasena) VALUES (%s, %s)", (usuario, contrasena_hash), commit=True)
        elif tipo == 'administrativo':
            query("INSERT INTO administrativos (usuario, contrasena) VALUES (%s, %s)", (usuario, contrasena_hash), commit=True)

        flash(f'Usuario "{usuario}" registrado exitosamente como {tipo}')
        return redirect(url_for('registrar_usuario'))

    # Mostrar tabla de usuarios existentes
    docentes = query("SELECT id, usuario, contrasena FROM maestros ORDER BY id", fetchall=True)
    administrativos = query("SELECT id, usuario, contrasena FROM administrativos ORDER BY id", fetchall=True)

    return render_template('registrar_usuario.html',
                           docentes=docentes,
                           administrativos=administrativos)

@app.route('/registro_usuario_publico', methods=['GET', 'POST'])
def registrar_usuario_publico():
    if request.method == 'POST':
        tipo = request.form['tipo'].strip()
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()

        # Validar campos vacíos
        if not tipo or not usuario or not contrasena:
            flash('Todos los campos son obligatorios')
            return redirect(url_for('registrar_usuario_publico'))

        # Determinar tabla según tipo
        if tipo == 'docente':
            tabla = 'maestros'
        elif tipo == 'administrativo':
            tabla = 'administrativos'
        else:
            flash('Tipo de usuario no válido')
            return redirect(url_for('registrar_usuario_publico'))

        # Verificar si el usuario ya existe
        existe = query(f"SELECT * FROM {tabla} WHERE usuario = %s", (usuario,), fetchone=True)

        if existe:
            flash(f'El usuario "{usuario}" ya está registrado como {tipo}')
            return redirect(url_for('registrar_usuario_publico'))

        # Insertar nuevo usuario
        contrasena_hash = generate_password_hash(contrasena)
        query(f"INSERT INTO {tabla} (usuario, contrasena) VALUES (%s, %s)", (usuario, contrasena_hash), commit=True)

        flash('¡Registro exitoso! Ahora puedes iniciar sesión.')

        # Redirigir al login correspondiente
        if tipo == 'docente':
            return redirect(url_for('login_docente'))
        elif tipo == 'administrativo':
            return redirect(url_for('login_admin'))

    return render_template('registrar_usuario_publico.html')

@app.route('/ver_usuarios')
def ver_usuarios():
    if 'user_id' not in session or session.get('usuario_tipo') != 'admin':
        flash('Acceso restringido')
        return redirect(url_for('login_admin'))

    docentes = query("SELECT id, usuario FROM maestros ORDER BY usuario", fetchall=True)
    admins = query("SELECT id, usuario FROM administrativos ORDER BY usuario", fetchall=True)

    # Si viene info para editar
    tipo = request.args.get('tipo')
    user_id = request.args.get('user_id')
    usuario_editar, tipo_edicion = None, None

    if tipo in ['docente', 'administrativo'] and user_id:
        tabla = 'maestros' if tipo == 'docente' else 'administrativos'
        usuario_editar = query(f"SELECT * FROM {tabla} WHERE id = %s", (user_id,), fetchone=True)
        tipo_edicion = tipo

    return render_template('ver_usuarios.html',
                           docentes=docentes,
                           admins=admins,
                           usuario_editar=usuario_editar,
                           tipo_edicion=tipo_edicion)

@app.route('/eliminar_usuario')
def eliminar_usuario():
    if 'user_id' not in session or session.get('usuario_tipo') != 'admin':
        flash('Acceso restringido. Solo administradores pueden eliminar usuarios.')
        return redirect(url_for('login_admin'))

    tipo = request.args.get('tipo')
    user_id = request.args.get('user_id')

    # Validación básica
    if tipo not in ['docente', 'administrativo'] or not user_id or not user_id.isdigit():
        flash('Datos inválidos para eliminar usuario ❌')
        return redirect(url_for('registrar_usuario'))

    tabla = 'maestros' if tipo == 'docente' else 'administrativos'

    resultado = query(f"SELECT usuario FROM {tabla} WHERE id = %s", (user_id,), fetchone=True)

    if resultado:
        query(f"DELETE FROM {tabla} WHERE id = %s", (user_id,), commit=True)
        flash(f'Usuario "{resultado[0]}" eliminado correctamente ✅')
    else:
        flash('Usuario no encontrado ❌')

    return redirect(url_for('registrar_usuario'))

@app.route('/actualizar_usuario', methods=['POST'])
def actualizar_usuario():
    tipo = request.form.get('tipo')
    user_id = request.form.get('user_id')
    nuevo_usuario = request.form.get('usuario').strip()
    nueva_contrasena = request.form.get('contrasena').strip()

    if tipo not in ['docente', 'administrativo'] or not user_id or not nuevo_usuario:
        flash('Datos inválidos')
        return redirect(url_for('ver_usuarios'))

    tabla = 'maestros' if tipo == 'docente' else 'administrativos'

    if nueva_contrasena:
        query(f"UPDATE {tabla} SET usuario = %s, contrasena = %s WHERE id = %s",
              (nuevo_usuario, nueva_contrasena, user_id), commit=True)
    else:
        query(f"UPDATE {tabla} SET usuario = %s WHERE id = %s",
              (nuevo_usuario, user_id), commit=True)

    flash('✅ Usuario actualizado correctamente')
    return redirect(url_for('ver_usuarios'))


@app.route('/cambiar-contrasena', methods=['GET', 'POST'])
def cambiar_contrasena():
    if 'user_id' not in session or session.get('usuario_tipo') not in ['docente', 'admin']:
        flash('Acceso restringido.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        actual = request.form['contrasena_actual'].strip()
        nueva = request.form['nueva_contrasena'].strip()
        confirmar = request.form['confirmar_contrasena'].strip()

        docente = query("SELECT contrasena FROM maestros WHERE id = %s",
                        (session['user_id'],), fetchone=True)

        if not docente or not check_password_hash(docente[0], actual):
            flash('❌ La contraseña actual no es correcta.')
        elif nueva != confirmar:
            flash('⚠️ Las nuevas contraseñas no coinciden.')
        elif not nueva:
            flash('🚫 La nueva contraseña no puede estar vacía.')
        else:
            nueva_hash = generate_password_hash(nueva)
            query("UPDATE maestros SET contrasena = %s WHERE id = %s",
                  (nueva_hash, session['user_id']), commit=True)
            flash('✅ Contraseña actualizada con éxito.')

        return redirect(url_for('cambiar_contrasena'))

    return render_template('cambiar_contrasena.html', tipo=session.get('usuario_tipo'))


@app.route('/logout')
def logout():
    session.clear()  # Borra toda la sesión
    flash('Sesión cerrada exitosamente')
    return redirect(url_for('seleccionar_rol'))


@app.route('/login/docente', methods=['GET', 'POST'])
def login_docente():
    if request.method == 'POST':
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()

        docente = query("SELECT id, usuario, contrasena FROM maestros WHERE usuario = %s",
                        (usuario,), fetchone=True)

        if docente:
            docente_id, docente_usuario, docente_pass = docente

            if check_password_hash(docente_pass, contrasena):
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
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()

        admin = query("SELECT id, usuario, contrasena FROM administrativos WHERE usuario = %s",
                      (usuario,), fetchone=True)

        if admin:
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

@app.route('/actualizar_contrasena/<tipo>/<int:user_id>', methods=['GET', 'POST'])
def actualizar_contrasena(tipo, user_id):
    if session.get('usuario_tipo') != 'admin':
        return redirect(url_for('seleccionar_rol'))

    if tipo not in ['docente', 'administrativo']:
        flash('Tipo de usuario inválido ❌')
        return redirect(url_for('registrar_usuario'))

    tabla = 'maestros' if tipo == 'docente' else 'administrativos'
    usuario = query(f"SELECT id, usuario FROM {tabla} WHERE id = %s", (user_id,), fetchone=True)

    if not usuario:
        flash('Usuario no encontrado ❌')
        return redirect(url_for('registrar_usuario'))

    if request.method == 'POST':
        nueva = request.form['nueva_contrasena'].strip()
        if not nueva:
            flash('La nueva contraseña no puede estar vacía ❗')
        else:
            nueva_hash = generate_password_hash(nueva)
            query(f"UPDATE {tabla} SET contrasena = %s WHERE id = %s",
                  (nueva_hash, user_id), commit=True)
            flash(f'Contraseña actualizada correctamente para "{usuario[1]}" ✅')

        return redirect(url_for('registrar_usuario'))

    return render_template('actualizar_contrasena.html', usuario=usuario, tipo=tipo)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        matricula = request.form['matricula'].strip()

        user = query("SELECT id, nombre, matricula FROM estudiantes WHERE nombre = %s AND matricula = %s",
                     (nombre, matricula), fetchone=True)

        if user:
            session['user_id'] = user[0]
            session['usuario_tipo'] = 'estudiante'
            return redirect(url_for('ver_calificaciones'))
        else:
            flash('Nombre o matrícula incorrectos ❌')
            return redirect(url_for('login'))

    return render_template('inicio_sesion.html')


@app.route('/dashboard')
def dashboard():
    calificaciones = query("SELECT * FROM calificaciones", fetchall=True)

    if not calificaciones:
        return render_template('dashboard.html', graph_html=None)

    # Convertir los datos a un DataFrame
    df = pd.DataFrame([dict(zip([desc[0] for desc in g.db_conn.cursor().description], row))
                       for row in calificaciones])

    # Crear una gráfica de ejemplo
    fig = px.histogram(df, x='calificacion', nbins=10, title='Distribución de Calificaciones')
    graph_html = fig.to_html(full_html=False)

    return render_template('dashboard.html', graph_html=graph_html)


@app.route('/ver_calificaciones', methods=['GET'])
def ver_calificaciones():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('index'))

        estudiante = query("SELECT nombre, semestre FROM estudiantes WHERE id = %s",
                           (user_id,), fetchone=True)

        if not estudiante:
            return render_template('calificaciones.html', calificaciones=None)

        nombre_estudiante, semestre_actual = estudiante

        calificaciones = query('''
            SELECT c.calificacion,
                   m.nombre AS materia_nombre,
                   %s AS estudiante_nombre,
                   %s AS estudiante_semestre
            FROM calificaciones c
            JOIN materias m ON c.materia = m.id
            WHERE c.user_id = %s AND m.semestre = %s
        ''', (nombre_estudiante, semestre_actual, user_id, semestre_actual), fetchall=True)

        return render_template('calificaciones.html',
                               calificaciones=calificaciones,
                               semestre_actual=semestre_actual)

    except Exception as e:
        return f"Ha ocurrido un error: {str(e)}", 500


@app.route('/add_calificacion', methods=['POST'])
def add_calificacion():
    try:
        materia = request.form['materia']
        calificacion = request.form['calificacion']
        user_id = session.get('user_id')

        query("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
              (user_id, materia, calificacion), commit=True)

        return redirect(url_for('ver_calificaciones'))

    except Exception as e:
        print(f"Error al añadir calificación: {e}")
        return str(e), 500


@app.route('/delete_materia', methods=['POST'])
def delete_materia():
    try:
        materia_id = request.form['id']

        if not materia_id:
            return jsonify({'success': False, 'message': 'ID de materia no proporcionado.'})

        query("DELETE FROM materias WHERE id = %s", (materia_id,), commit=True)
        query("DELETE FROM calificaciones WHERE materia = %s", (materia_id,), commit=True)

        return jsonify({'success': True, 'message': 'Materia eliminada con éxito.'})

    except Exception as e:
        print(f"Error al eliminar materia: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/calificaciones')
def mostrar_calificaciones():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    calificaciones = query('''
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
    ''', (user_id,), fetchall=True)

    semestre_actual = max([row[3] for row in calificaciones]) if calificaciones else None

    return render_template('calificaciones.html',
                           calificaciones=calificaciones,
                           semestre_actual=semestre_actual)

@app.route('/registrar-calificacion', methods=['GET', 'POST'])
def registrar_calificacion():
    # 📝 Procesar formulario (POST)
    if request.method == 'POST':
        alumno_id = request.form['alumno_id']
        materia_id = request.form['materia_id']
        calificacion = request.form['calificacion']

        try:
            registro = query(
                "SELECT id FROM calificaciones WHERE user_id = %s AND materia = %s",
                (alumno_id, materia_id),
                fetchone=True
            )

            if registro:
                query(
                    "UPDATE calificaciones SET calificacion = %s WHERE user_id = %s AND materia = %s",
                    (calificacion, alumno_id, materia_id),
                    commit=True
                )
                mensaje = '🔄 Calificación actualizada con éxito.'
            else:
                query(
                    "INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
                    (alumno_id, materia_id, calificacion),
                    commit=True
                )
                mensaje = '✅ Calificación registrada con éxito.'

        except Exception as e:
            mensaje = f'⚠️ Error al guardar la calificación: {str(e)}'

        return redirect(url_for('registrar_calificacion', mensaje=mensaje))

    # 📦 Renderizar vista (GET)
    mensaje = request.args.get('mensaje')

    alumnos_sql = query("SELECT * FROM estudiantes", fetchall=True)
    materias_sql = query("SELECT * FROM materias", fetchall=True)

    # Convertir cada Row a diccionario para compatibilidad con tojson
    alumnos = [dict(zip([desc[0] for desc in g.db_conn.cursor().description], row)) for row in alumnos_sql]
    materias = [dict(zip([desc[0] for desc in g.db_conn.cursor().description], row)) for row in materias_sql]

    # 📚 Agrupar alumnos por licenciatura y semestre
    alumnos_agrupados = {}
    for alumno in alumnos:
        lic = alumno['licenciatura']
        sem = alumno['semestre']
        alumnos_agrupados.setdefault(lic, {}).setdefault(sem, []).append(alumno)

    # 🔠 Ordenar alumnos por nombre
    for lic in alumnos_agrupados:
        for sem in alumnos_agrupados[lic]:
            alumnos_agrupados[lic][sem].sort(key=lambda x: x['nombre'])

    return render_template('registrar_calificacion.html',
                           alumnos=alumnos,
                           materias=materias,
                           mensaje=mensaje,
                           alumnos_agrupados=alumnos_agrupados)


@app.route('/guardar-calificacion', methods=['POST'])
def guardar_calificacion():
    alumno_id = request.form['alumno_id']
    materia_id = request.form['materia_id']
    calificacion = request.form['calificacion']

    try:
        registro = query(
            "SELECT id FROM calificaciones WHERE user_id = %s AND materia = %s",
            (alumno_id, materia_id),
            fetchone=True
        )

        if registro:
            query(
                "UPDATE calificaciones SET calificacion = %s WHERE user_id = %s AND materia = %s",
                (calificacion, alumno_id, materia_id),
                commit=True
            )
            mensaje = '🔄 Calificación actualizada con éxito.'
        else:
            query(
                "INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
                (alumno_id, materia_id, calificacion),
                commit=True
            )
            mensaje = '✅ Calificación registrada con éxito.'

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'exito': True, 'mensaje': mensaje})

    except Exception as e:
        mensaje = f'⚠️ Error al guardar la calificación: {str(e)}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'exito': False, 'mensaje': mensaje})

    # Si no es AJAX, redirige (por si quieres usarlo desde un formulario normal)
    return redirect(url_for('registrar_calificacion', mensaje=mensaje))


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

    filas_actualizadas = query(
        "UPDATE estudiantes SET semestre = %s WHERE licenciatura = %s AND semestre = %s",
        (semestre_destino_int, licenciatura, semestre_actual_int),
        commit=True
    )

    if not filas_actualizadas:
        return jsonify({'error': 'No se encontraron alumnos en ese semestre.'}), 404

    return jsonify({'mensaje': 'Semestres actualizados correctamente'})


@app.route('/historial')
def historial_academico():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    resultado = query('''
        SELECT m.licenciatura,
               m.semestre,
               m.nombre AS materia,
               c.calificacion
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        WHERE c.user_id = %s
        ORDER BY m.licenciatura, m.semestre, m.nombre
    ''', (user_id,), fetchall=True)

    # Agrupar historial por licenciatura y semestre
    historial = {}
    promedios_por_semestre = {}

    for fila in resultado:
        lic = fila[0]
        sem = int(fila[1])  # ✅ Asegura que sea numérico

        # Guardar materias y calificaciones
        historial.setdefault(lic, {}).setdefault(sem, []).append({
            'materia': fila[2],
            'calificacion': fila[3]
        })

        # Para calcular promedio por semestre
        promedios_por_semestre.setdefault(sem, []).append(fila[3])

    # Calcular promedios finales por semestre
    promedios_por_semestre = {
        sem: round(sum(califs) / len(califs), 1)
        for sem, califs in promedios_por_semestre.items()
    }

    return render_template('historial_academico.html',
                           historial=historial,
                           promedios_por_semestre=promedios_por_semestre)

@app.route('/ver_historial/<int:estudiante_id>')
def ver_historial_estudiante(estudiante_id):
    resultado = query('''
        SELECT e.nombre AS estudiante,
               m.licenciatura,
               m.semestre,
               m.nombre AS materia,
               c.calificacion
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE c.user_id = %s
        ORDER BY m.licenciatura, m.semestre, m.nombre
    ''', (estudiante_id,), fetchall=True)

    if not resultado:
        flash('Este estudiante aún no tiene calificaciones registradas.', 'warning')
        return redirect(url_for('catalogo_alumnos'))  # Ajusta según tu flujo

    historial = {}
    promedios_por_semestre = {}

    for fila in resultado:
        lic = fila[1]  # licenciatura
        sem = int(fila[2])  # semestre
        historial.setdefault(lic, {}).setdefault(sem, []).append({
            'materia': fila[3],
            'calificacion': fila[4]
        })
        promedios_por_semestre.setdefault(sem, []).append(fila[4])

    promedios_por_semestre = {
        sem: round(sum(califs) / len(califs), 1)
        for sem, califs in promedios_por_semestre.items()
    }

    return render_template('historial_academico.html',
                           estudiante=resultado[0][0],
                           historial=historial,
                           promedios_por_semestre=promedios_por_semestre)


@app.route('/update_calificacion', methods=['POST'])
def update_calificacion():
    nombre_alumno = request.form.get('nombre_alumno')
    licenciatura = request.form.get('licenciatura')
    semestre = request.form.get('semestre')
    materia_id = request.form.get('materia_calificar')
    calificacion = request.form.get('calificacion')

    alumno = query('''
        SELECT id FROM estudiantes
        WHERE nombre = %s AND licenciatura = %s AND semestre = %s
    ''', (nombre_alumno, licenciatura, semestre), fetchone=True)

    if not alumno:
        return "Alumno no encontrado", 404

    alumno_id = alumno[0]

    calificacion_existente = query('''
        SELECT id FROM calificaciones
        WHERE user_id = %s AND materia = %s
    ''', (alumno_id, materia_id), fetchone=True)

    if calificacion_existente:
        query('''
            UPDATE calificaciones
            SET calificacion = %s
            WHERE id = %s
        ''', (calificacion, calificacion_existente[0]), commit=True)
    else:
        query('''
            INSERT INTO calificaciones (user_id, materia, calificacion)
            VALUES (%s, %s, %s)
        ''', (alumno_id, materia_id, calificacion), commit=True)

    return redirect(url_for('ver_calificaciones'))


@app.route('/alumnos')
def alumnos():
    alumnos = query("SELECT * FROM estudiantes", fetchall=True)

    alumnos_por_licenciatura = {}
    for alumno in alumnos:
        lic = alumno[2]  # licenciatura
        sem = alumno[3]  # semestre
        alumnos_por_licenciatura.setdefault(lic, {}).setdefault(sem, []).append(dict(zip(
            [desc[0] for desc in g.db_conn.cursor().description], alumno
        )))

    return render_template('alumnos.html', alumnos=alumnos_por_licenciatura)


def inicializar_materias_para_alumno(alumno_id, licenciatura, semestre):
    materias = query("SELECT id FROM materias WHERE licenciatura = %s AND semestre = %s",
                     (licenciatura, semestre), fetchall=True)

    for materia in materias:
        query("INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (%s, %s, %s)",
              (alumno_id, materia[0], 0), commit=True)


@app.route('/gestion_alumnos', methods=['GET'])
def gestion_alumnos():
    alumnos = query("SELECT * FROM estudiantes", fetchall=True)

    alumnos_por_licenciatura = {}
    for alumno in alumnos:
        lic = alumno[2]
        sem = alumno[3]
        alumnos_por_licenciatura.setdefault(lic, {}).setdefault(sem, []).append(dict(zip(
            [desc[0] for desc in g.db_conn.cursor().description], alumno
        )))

    for lic in alumnos_por_licenciatura:
        for sem in alumnos_por_licenciatura[lic]:
            alumnos_por_licenciatura[lic][sem] = sorted(
                alumnos_por_licenciatura[lic][sem], key=lambda x: x['nombre']
            )

    return render_template('gestion_alumnos.html', alumnos=alumnos_por_licenciatura)


@app.route('/datos_alumnos', methods=['POST'])
def datos_alumnos():
    nombre = request.form['nombre']
    matricula = request.form['matricula']
    licenciatura = request.form['licenciatura']
    semestre = request.form['semestre']

    alumno_existente = query(
        "SELECT * FROM estudiantes WHERE matricula = %s", (matricula,), fetchone=True
    )

    if alumno_existente:
        query('''
            UPDATE estudiantes
            SET nombre = %s, licenciatura = %s, semestre = %s
            WHERE matricula = %s
        ''', (nombre, licenciatura, semestre, matricula), commit=True)
        mensaje = f'🔄 Alumno actualizado al {semestre}° semestre.'
    else:
        query('''
            INSERT INTO estudiantes (nombre, matricula, licenciatura, semestre)
            VALUES (%s, %s, %s, %s)
        ''', (nombre, matricula, licenciatura, semestre), commit=True)
        mensaje = f'✅ Alumno registrado correctamente.'

    return redirect(url_for('registrar_calificacion', mensaje=mensaje))


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
        query('''
            INSERT INTO materias (nombre, licenciatura, semestre)
            VALUES (%s, %s, %s)
        ''', (nombre, licenciatura, semestre), commit=True)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return 'Materia añadida', 200

        flash('Materia añadida con éxito.', 'success')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return f'Error: {str(e)}', 500
        flash(f'Ocurrió un error al añadir la materia: {e}', 'danger')

    return redirect(url_for('gestion_materias'))


def verificar_materia_duplicada(nombre, licenciatura, semestre):
    resultado = query('''
        SELECT 1 FROM materias
        WHERE nombre = %s AND licenciatura = %s AND semestre = %s
    ''', (nombre, licenciatura, semestre), fetchone=True)
    return resultado is not None

@app.route('/delete_alumno', methods=['POST'])
def delete_alumno():
    alumno_id = request.form['id']
    query("DELETE FROM estudiantes WHERE id = %s", (alumno_id,), commit=True)
    return redirect(url_for('alumnos'))


@app.route('/error')
def error():
    return 'Nombre de usuario o contraseña incorrectos. Por favor, intenta nuevamente.'


@app.route('/materias')
def gestion_materias():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))

    materias = query('''
        SELECT m.*, c.calificacion
        FROM materias m
        LEFT JOIN calificaciones c ON m.id = c.materia AND c.user_id = %s
        ORDER BY m.licenciatura, m.semestre, m.nombre
    ''', (user_id,), fetchall=True)

    materias_por_licenciatura = {}
    for materia in materias:
        lic = materia[2]  # licenciatura
        sem = materia[3]  # semestre
        materias_por_licenciatura.setdefault(lic, {}).setdefault(sem, []).append(dict(zip(
            [desc[0] for desc in g.db_conn.cursor().description], materia
        )))

    return render_template('materias.html', materias=materias_por_licenciatura)


@app.route('/ver_materias')
def ver_materias():
    materias = query("SELECT * FROM materias ORDER BY licenciatura, semestre, nombre", fetchall=True)

    estructura = {}
    for m in materias:
        lic = m[2]
        sem = str(m[3])
        estructura.setdefault(lic, {}).setdefault(sem, []).append(dict(zip(
            [desc[0] for desc in g.db_conn.cursor().description], m
        )))

    for lic in estructura:
        for s in range(1, 8):
            estructura[lic].setdefault(str(s), [])

    return render_template('ver_materias.html', materias=estructura)


@app.route('/eliminar_materia/<int:materia_id>', methods=['POST'])
def eliminar_materia(materia_id):
    query("DELETE FROM materias WHERE id = %s", (materia_id,), commit=True)
    flash('Materia eliminada exitosamente.', 'success')
    return redirect(url_for('ver_materias'))


@app.route('/obtener_materias', methods=['GET'])
def obtener_materias():
    licenciatura = request.args.get('licenciatura')
    semestre = request.args.get('semestre')

    materias = query('''
        SELECT m.id, m.nombre 
        FROM materias m
        JOIN licenciaturas_materias lm ON m.id = lm.materia_id
        WHERE lm.licenciatura = %s AND lm.semestre = %s
    ''', (licenciatura, semestre), fetchall=True)

    materias_list = [{'id': m[0], 'nombre': m[1]} for m in materias]
    return jsonify({'materias': materias_list})


@app.route('/gestionar_materias', methods=['GET', 'POST'])
def gestionar_materias():
    materias_duplicadas = query('''
        SELECT id, nombre, licenciatura, semestre
        FROM materias
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM materias
            GROUP BY nombre, licenciatura, semestre
        )
    ''', fetchall=True)

    if request.method == 'POST':
        ids_para_eliminar = request.form.getlist('materias_eliminar')
        for materia_id in ids_para_eliminar:
            query("DELETE FROM materias WHERE id = %s", (materia_id,), commit=True)
        flash('Las materias seleccionadas han sido eliminadas.', 'success')
        return redirect(url_for('gestionar_materias'))

    return render_template('gestionar_materias.html', materias_duplicadas=materias_duplicadas)


@app.route('/materias_calificadas', methods=['GET'])
def materias_calificadas():
    user_id = request.args.get('user_id')
    licenciatura = request.args.get('licenciatura')
    semestre = request.args.get('semestre')

    materias = query('''
        SELECT 
            c.calificacion, 
            m.nombre AS materia_nombre, 
            m.semestre, 
            e.nombre AS estudiante_nombre, 
            e.licenciatura
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE e.id = %s AND e.licenciatura = %s AND m.semestre = %s
        ORDER BY m.semestre;
    ''', (user_id, licenciatura, semestre), fetchall=True)

    return render_template('materias_calificadas.html', materias=materias, user_id=user_id)


@app.route('/editar_calificacion/<int:calificacion_id>', methods=['GET', 'POST'])
def editar_calificacion(calificacion_id):
    if request.method == 'POST':
        nueva_calificacion = request.form['calificacion']
        query("UPDATE calificaciones SET calificacion = %s WHERE id = %s",
              (nueva_calificacion, calificacion_id), commit=True)
        flash('Calificación actualizada correctamente.', 'success')
        return redirect(url_for('ver_calificaciones', user_id=request.form['user_id']))

    calificacion = query("SELECT * FROM calificaciones WHERE id = %s",
                         (calificacion_id,), fetchone=True)

    return render_template('editar_calificacion.html', calificacion=calificacion)


@app.route('/eliminar_duplicados', methods=['GET', 'POST'])
def eliminar_duplicados():
    if request.method == 'GET':
        ids_duplicados = query('''
            WITH cte AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY user_id, materia ORDER BY id
                ) AS rn
                FROM calificaciones
            )
            SELECT id FROM cte WHERE rn > 1;
        ''', fetchall=True)

        duplicados_ids = [row[0] for row in ids_duplicados]

        if duplicados_ids:
            placeholders = ','.join(['%s'] * len(duplicados_ids))
            calificaciones_duplicadas = query(f'''
                SELECT c.id, c.calificacion,
                       m.nombre AS materia_nombre,
                       e.nombre AS estudiante_nombre
                FROM calificaciones c
                JOIN materias m ON c.materia = m.id
                JOIN estudiantes e ON c.user_id = e.id
                WHERE c.id IN ({placeholders});
            ''', tuple(duplicados_ids), fetchall=True)
        else:
            calificaciones_duplicadas = []

        return render_template('eliminar_duplicados.html', calificaciones=calificaciones_duplicadas)

    elif request.method == 'POST':
        duplicados_ids = request.form.getlist('duplicados')
        if not duplicados_ids:
            flash('No se seleccionó ninguna calificación para eliminar.', 'danger')
            return redirect(url_for('eliminar_duplicados'))

        for id in duplicados_ids:
            query("DELETE FROM calificaciones WHERE id = %s", (id,), commit=True)

        flash(f'Se eliminaron {len(duplicados_ids)} calificaciones duplicadas.', 'success')
        return redirect(url_for('eliminar_duplicados'))

    return redirect(url_for('ver_calificaciones', user_id=session.get('user_id')))


if __name__ == '__main__':
    verificar_datos_materias()
    app.run(debug=True)
