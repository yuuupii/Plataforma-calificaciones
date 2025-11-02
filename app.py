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

# Conexión a la base de datos Supabase/Postgres
def get_db_connection():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL no está definida en las variables de entorno")
    
    # Render a veces usa el formato viejo postgres://, lo convertimos al nuevo:
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
    
    return psycopg2.connect(dsn)

#Opción de SQLite como respaldo
"""
def get_db_connection_sqlite():
    if 'db' not in g:
        g.db = sqlite3.connect('database.db')
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode = WAL')
    return g.db
"""
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
        
        # ✅ Crear la tabla si no existe
        conn.execute('''
            CREATE TABLE IF NOT EXISTS materias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                licenciatura TEXT NOT NULL,
                semestre INTEGER NOT NULL
            );
        ''')
        conn.commit()

        # ✅ Consultar datos después de asegurar existencia
        materias = conn.execute('SELECT * FROM materias').fetchall()
        conn.close()

def inicializar_base_datos():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maestros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS administrativos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL
        );
    ''')

    conn.commit()
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
    cursor = conn.cursor()

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
            existe = cursor.execute('SELECT * FROM maestros WHERE usuario = ?', (usuario,)).fetchone()
        elif tipo == 'administrativo':
            existe = cursor.execute('SELECT * FROM administrativos WHERE usuario = ?', (usuario,)).fetchone()
        else:
            flash('Tipo de usuario no válido')
            return redirect(url_for('registrar_usuario'))

        if existe:
            flash(f'El usuario "{usuario}" ya está registrado como {tipo}')
            return redirect(url_for('registrar_usuario'))

        # Insertar nuevo usuario
        # Encriptar contraseña antes de guardar
        contrasena_hash = generate_password_hash(contrasena)

        if tipo == 'docente':
            cursor.execute('INSERT INTO maestros (usuario, contrasena) VALUES (?, ?)', (usuario, contrasena_hash))
        elif tipo == 'administrativo':
            cursor.execute('INSERT INTO administrativos (usuario, contrasena) VALUES (?, ?)', (usuario, contrasena_hash))

        conn.commit()
        flash(f'Usuario "{usuario}" registrado exitosamente como {tipo}')
        return redirect(url_for('registrar_usuario'))

    # Mostrar tabla de usuarios existentes
    docentes = conn.execute('SELECT id, usuario, contrasena FROM maestros ORDER BY id').fetchall()
    administrativos = conn.execute('SELECT id, usuario, contrasena FROM administrativos ORDER BY id').fetchall()
    conn.close()

    return render_template('registrar_usuario.html',
                           docentes=docentes,
                           administrativos=administrativos)

@app.route('/registro_usuario_publico', methods=['GET', 'POST'])
def registrar_usuario_publico():
    conn = get_db_connection()
    cursor = conn.cursor()

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
        existe = cursor.execute(f'SELECT * FROM {tabla} WHERE usuario = ?', (usuario,)).fetchone()

        if existe:
            flash(f'El usuario "{usuario}" ya está registrado como {tipo}')
            return redirect(url_for('registrar_usuario_publico'))

        # Insertar nuevo usuario
        contrasena_hash = generate_password_hash(contrasena)
        cursor.execute(f'INSERT INTO {tabla} (usuario, contrasena) VALUES (?, ?)', (usuario, contrasena_hash))
        conn.commit()
        conn.close()

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

    conn = get_db_connection()

    docentes = conn.execute('SELECT id, usuario FROM maestros ORDER BY usuario').fetchall()
    admins = conn.execute('SELECT id, usuario FROM administrativos ORDER BY usuario').fetchall()

    # Si viene info para editar
    tipo = request.args.get('tipo')
    user_id = request.args.get('user_id')
    usuario_editar, tipo_edicion = None, None

    if tipo in ['docente', 'administrativo'] and user_id:
        tabla = 'maestros' if tipo == 'docente' else 'administrativos'
        usuario_editar = conn.execute(f'SELECT * FROM {tabla} WHERE id = ?', (user_id,)).fetchone()
        tipo_edicion = tipo

    conn.close()

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

    conn = get_db_connection()
    resultado = conn.execute(f'SELECT usuario FROM {tabla} WHERE id = ?', (user_id,)).fetchone()

    if resultado:
        conn.execute(f'DELETE FROM {tabla} WHERE id = ?', (user_id,))
        conn.commit()
        flash(f'Usuario "{resultado["usuario"]}" eliminado correctamente ✅')
    else:
        flash('Usuario no encontrado ❌')

    conn.close()
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
    conn = get_db_connection()

    if nueva_contrasena:
        conn.execute(f'''
            UPDATE {tabla} SET usuario = ?, contrasena = ? WHERE id = ?
        ''', (nuevo_usuario, nueva_contrasena, user_id))
    else:
        conn.execute(f'''
            UPDATE {tabla} SET usuario = ? WHERE id = ?
        ''', (nuevo_usuario, user_id))

    conn.commit()
    conn.close()

    flash('✅ Usuario actualizado correctamente')
    return redirect(url_for('ver_usuarios'))

@app.route('/cambiar-contrasena', methods=['GET', 'POST'])
def cambiar_contrasena():
    if 'user_id' not in session or session.get('usuario_tipo') not in ['docente', 'admin']:
        flash('Acceso restringido.')
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        actual = request.form['contrasena_actual'].strip()
        nueva = request.form['nueva_contrasena'].strip()
        confirmar = request.form['confirmar_contrasena'].strip()

        docente = conn.execute(
            'SELECT contrasena FROM maestros WHERE id = ?',
            (session['user_id'],)
        ).fetchone()

        if not docente or actual != docente['contrasena']:
            flash('❌ La contraseña actual no es correcta.')
        elif nueva != confirmar:
            flash('⚠️ Las nuevas contraseñas no coinciden.')
        elif not nueva:
            flash('🚫 La nueva contraseña no puede estar vacía.')
        else:
            conn.execute(
                'UPDATE maestros SET contrasena = ? WHERE id = ?',
                (nueva, session['user_id'])
            )
            conn.commit()
            flash('✅ Contraseña actualizada con éxito.')

        conn.close()
        return redirect(url_for('cambiar_contrasena'))

    conn.close()
    return render_template('cambiar_contrasena.html', tipo=session.get('usuario_tipo'))

@app.route('/logout')
def logout():
    session.clear()  # Borra toda la sesión
    flash('Sesión cerrada exitosamente')
    return redirect(url_for('seleccionar_rol'))  # Asegúrate de tener esta ruta definida

from werkzeug.security import check_password_hash

@app.route('/login/docente', methods=['GET', 'POST'])
def login_docente():
    if request.method == 'POST':
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()

        conn = get_db_connection()
        docente = conn.execute(
            'SELECT * FROM maestros WHERE usuario = ?',
            (usuario,)
        ).fetchone()
        conn.close()

        if docente and check_password_hash(docente['contrasena'], contrasena):
            session['user_id'] = docente['id']
            session['usuario_tipo'] = 'docente'
            session['usuario'] = docente['usuario']
            flash(f'Bienvenido, docente {docente["usuario"]} 👨‍🏫')
            return redirect(url_for('menu_docente'))
        else:
            flash('Credenciales incorrectas ❌')
            return redirect(url_for('login_docente'))

    return render_template('login_docente.html')

@app.route('/login/admin', methods=['GET', 'POST'])
def login_admin():
    if request.method == 'POST':
        usuario = request.form['usuario'].strip()
        contrasena = request.form['contrasena'].strip()

        conn = get_db_connection()
        admin = conn.execute('SELECT * FROM administrativos WHERE usuario = ?', (usuario,)).fetchone()
        conn.close()

        if admin and check_password_hash(admin['contrasena'], contrasena):
            session['user_id'] = admin['id']
            session['usuario_tipo'] = 'admin'
            session['usuario'] = admin['usuario']
            flash(f'Bienvenido, administrador {admin["usuario"]} 🧑‍💼')
            return redirect(url_for('menu_admin'))
        else:
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

    conn = get_db_connection()
    cursor = conn.cursor()

    if tipo not in ['docente', 'administrativo']:
        flash('Tipo de usuario inválido ❌')
        return redirect(url_for('registrar_usuario'))

    tabla = 'maestros' if tipo == 'docente' else 'administrativos'
    usuario = cursor.execute(f'SELECT * FROM {tabla} WHERE id = ?', (user_id,)).fetchone()

    if not usuario:
        flash('Usuario no encontrado ❌')
        conn.close()
        return redirect(url_for('registrar_usuario'))

    if request.method == 'POST':
        nueva = request.form['nueva_contrasena'].strip()
        if not nueva:
            flash('La nueva contraseña no puede estar vacía ❗')
        else:
            nueva_hash = generate_password_hash(nueva)
            cursor.execute(f'UPDATE {tabla} SET contrasena = ? WHERE id = ?', (nueva_hash, user_id))
            conn.commit()
            flash(f'Contraseña actualizada correctamente para "{usuario["usuario"]}" ✅')

        conn.close()
        return redirect(url_for('registrar_usuario'))

    conn.close()
    return render_template('actualizar_contrasena.html', usuario=usuario, tipo=tipo)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre = request.form['nombre']
        matricula = request.form['matricula']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM estudiantes WHERE nombre = ? AND matricula = ?', (nombre, matricula)).fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['usuario_tipo'] = 'estudiante'
            return redirect(url_for('ver_calificaciones'))
        else:
            flash('Nombre o matrícula incorrectos')
            return redirect(url_for('login'))  # Regresa al mismo formulario

    # Mostrar tu página visual personalizada
    return render_template('inicio_sesion.html')

@app.route('/login', methods=['GET'])
def mostrar_login_estudiante():
    return render_template('inicio_sesion.html')

@app.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    calificaciones = conn.execute('SELECT * FROM calificaciones').fetchall()
    conn.close()

    # Convertir los datos a un DataFrame
    df = pd.DataFrame([dict(row) for row in calificaciones])

    # Crear una gráfica de ejemplo
    fig = px.histogram(df, x='calificacion', nbins=10, title='Distribución de Calificaciones')
    graph_html = fig.to_html(full_html=False)

    return render_template('dashboard.html', graph_html=graph_html)

@app.route('/ver_calificaciones', methods=['GET'])
def ver_calificaciones():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('index'))  # Redirigir si el usuario no está autenticado

        conn = get_db_connection()

        # Primero obtenemos el semestre actual del estudiante
        estudiante = conn.execute(
            'SELECT nombre, semestre FROM estudiantes WHERE id = ?', (user_id,)
        ).fetchone()

        if not estudiante:
            conn.close()
            return render_template('calificaciones.html', calificaciones=None)

        semestre_actual = estudiante['semestre']

        # Luego obtenemos solo las calificaciones de ese semestre
        calificaciones = conn.execute('''
            SELECT c.calificacion, m.nombre AS materia_nombre, ? AS estudiante_nombre, ? AS estudiante_semestre
            FROM calificaciones c
            JOIN materias m ON c.materia = m.id
            WHERE c.user_id = ? AND m.semestre = ?
        ''', (estudiante['nombre'], semestre_actual, user_id, semestre_actual)).fetchall()

        conn.close()

        if not calificaciones:
            return render_template('calificaciones.html', calificaciones=None)

        calificaciones_dicts = [dict(row) for row in calificaciones]
        return render_template(
            'calificaciones.html',
            calificaciones=calificaciones_dicts,
            semestre_actual=semestre_actual
        )
    except Exception as e:
        return f"Ha ocurrido un error: {str(e)}", 500

@app.route('/add_calificacion', methods=['POST'])
def add_calificacion():
    try:
        materia = request.form['materia']
        calificacion = request.form['calificacion']
        user_id = session.get('user_id')

        conn = get_db_connection()
        conn.execute('INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (?, ?, ?)', (user_id, materia, calificacion))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_calificaciones'))
    except Exception as e:
        print(f"Error al añadir calificación: {e}")
        return str(e)

@app.route('/delete_materia', methods=['POST'])
def delete_materia():
    try:
        materia_id = request.form['id']

        if not materia_id:
            return jsonify({'success': False, 'message': 'ID de materia no proporcionado.'})

        conn = get_db_connection()

        # Eliminar la materia
        conn.execute('DELETE FROM materias WHERE id = ?', (materia_id,))
        conn.commit()

        # Eliminar calificaciones relacionadas
        conn.execute('DELETE FROM calificaciones WHERE materia = ?', (materia_id,))
        conn.commit()
        conn.close()

        # Devolver una respuesta JSON exitosa
        return jsonify({'success': True, 'message': 'Materia eliminada con éxito.'})

    except Exception as e:
        print(f"Error al eliminar materia: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/calificaciones')
def mostrar_calificaciones():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conn = get_db_connection()
    calificaciones = conn.execute('''
        SELECT c.calificacion,
               m.nombre AS materia_nombre,
               m.licenciatura,
               m.semestre,
               e.nombre AS estudiante_nombre,
               e.semestre AS estudiante_semestre
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE c.user_id = ?
    ''', (user_id,)).fetchall()
    conn.close()

    calificaciones = [dict(row) for row in calificaciones]

    # Calcula el semestre más alto entre todas las materias calificadas
    semestre_actual = max([row['semestre'] for row in calificaciones]) if calificaciones else None

    return render_template('calificaciones.html',
                           calificaciones=calificaciones,
                           semestre_actual=semestre_actual)

@app.route('/registrar-calificacion', methods=['GET', 'POST'])
def registrar_calificacion():
    conn = get_db_connection()

    # 📝 Procesar formulario (POST)
    if request.method == 'POST':
        alumno_id = request.form['alumno_id']
        materia_id = request.form['materia_id']
        calificacion = request.form['calificacion']

        try:
            registro = conn.execute(
                'SELECT id FROM calificaciones WHERE user_id = ? AND materia = ?',
                (alumno_id, materia_id)
            ).fetchone()

            if registro:
                conn.execute(
                    'UPDATE calificaciones SET calificacion = ? WHERE user_id = ? AND materia = ?',
                    (calificacion, alumno_id, materia_id)
                )
                mensaje = '🔄 Calificación actualizada con éxito.'
            else:
                conn.execute(
                    'INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (?, ?, ?)',
                    (alumno_id, materia_id, calificacion)
                )
                mensaje = '✅ Calificación registrada con éxito.'

            conn.commit()

        except Exception as e:
            mensaje = f'⚠️ Error al guardar la calificación: {str(e)}'

        finally:
            conn.close()

        return redirect(url_for('registrar_calificacion', mensaje=mensaje))

    # 📦 Renderizar vista (GET)
    mensaje = request.args.get('mensaje')

    alumnos_sql = conn.execute('SELECT * FROM estudiantes').fetchall()
    materias_sql = conn.execute('SELECT * FROM materias').fetchall()

    # Convertir cada Row a diccionario para compatibilidad con tojson
    alumnos = [dict(a) for a in alumnos_sql]
    materias = [dict(m) for m in materias_sql]

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

    conn.close()

    return render_template('registrar_calificacion.html',
                           alumnos=alumnos,
                           materias=materias,
                           mensaje=mensaje,
                           alumnos_agrupados=alumnos_agrupados)

@app.route('/guardar-calificacion', methods=['POST'])
def guardar_calificacion():
    conn = get_db_connection()

    alumno_id = request.form['alumno_id']
    materia_id = request.form['materia_id']
    calificacion = request.form['calificacion']

    try:
        registro = conn.execute(
            'SELECT id FROM calificaciones WHERE user_id = ? AND materia = ?',
            (alumno_id, materia_id)
        ).fetchone()

        if registro:
            conn.execute(
                'UPDATE calificaciones SET calificacion = ? WHERE user_id = ? AND materia = ?',
                (calificacion, alumno_id, materia_id)
            )
            mensaje = '🔄 Calificación actualizada con éxito.'
        else:
            conn.execute(
                'INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (?, ?, ?)',
                (alumno_id, materia_id, calificacion)
            )
            mensaje = '✅ Calificación registrada con éxito.'
        conn.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'exito': True, 'mensaje': mensaje})

    except Exception as e:
        mensaje = f'⚠️ Error al guardar la calificación: {str(e)}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'exito': False, 'mensaje': mensaje})
    finally:
        conn.close()

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

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE estudiantes SET semestre = ? WHERE licenciatura = ? AND semestre = ?',
        (semestre_destino_int, licenciatura, semestre_actual_int)
    )
    filas_actualizadas = cursor.rowcount
    conn.commit()
    conn.close()

    if filas_actualizadas == 0:
        return jsonify({'error': 'No se encontraron alumnos en ese semestre.'}), 404

    return jsonify({'mensaje': 'Semestres actualizados correctamente'})

@app.route('/historial')
def historial_academico():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conn = get_db_connection()

    resultado = conn.execute('''
        SELECT m.licenciatura,
               m.semestre,
               m.nombre AS materia,
               c.calificacion
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        WHERE c.user_id = ?
        ORDER BY m.licenciatura, m.semestre, m.nombre
    ''', (user_id,)).fetchall()

    conn.close()

    # Agrupar historial por licenciatura y semestre
    historial = {}
    promedios_por_semestre = {}

    for fila in resultado:
        lic = fila['licenciatura']
        sem = int(fila['semestre'])  # ✅ Asegura que sea numérico

        # Guardar materias y calificaciones
        historial.setdefault(lic, {}).setdefault(sem, []).append({
            'materia': fila['materia'],
            'calificacion': fila['calificacion']
        })

        # Para calcular promedio por semestre
        promedios_por_semestre.setdefault(sem, []).append(fila['calificacion'])

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
    conn = get_db_connection()

    resultado = conn.execute('''
        SELECT e.nombre AS estudiante,
               m.licenciatura,
               m.semestre,
               m.nombre AS materia,
               c.calificacion
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE c.user_id = ?
        ORDER BY m.licenciatura, m.semestre, m.nombre
    ''', (estudiante_id,)).fetchall()

    conn.close()

    if not resultado:
        flash('Este estudiante aún no tiene calificaciones registradas.', 'warning')
        return redirect(url_for('catalogo_alumnos'))  # Ajusta según tu flujo

    historial = {}
    promedios_por_semestre = {}

    for fila in resultado:
        lic = fila['licenciatura']
        sem = int(fila['semestre'])
        historial.setdefault(lic, {}).setdefault(sem, []).append({
            'materia': fila['materia'],
            'calificacion': fila['calificacion']
        })
        promedios_por_semestre.setdefault(sem, []).append(fila['calificacion'])

    promedios_por_semestre = {
        sem: round(sum(califs) / len(califs), 1)
        for sem, califs in promedios_por_semestre.items()
    }

    return render_template('historial_academico.html',
                           estudiante=resultado[0]['estudiante'],
                           historial=historial,
                           promedios_por_semestre=promedios_por_semestre)


@app.route('/update_calificacion', methods=['POST'])
def update_calificacion():
    nombre_alumno = request.form.get('nombre_alumno')
    licenciatura = request.form.get('licenciatura')
    semestre = request.form.get('semestre')
    materia_id = request.form.get('materia_calificar')
    calificacion = request.form.get('calificacion')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Buscar al alumno en la base de datos
    query = '''
        SELECT id FROM estudiantes
        WHERE nombre = ? AND licenciatura = ? AND semestre = ?
    '''
    cursor.execute(query, (nombre_alumno, licenciatura, semestre))
    alumno = cursor.fetchone()

    if not alumno:
        return "Alumno no encontrado", 404

    alumno_id = alumno['id']

    # Verificar si ya existe una calificación para este alumno y esta materia
    query = '''
        SELECT id FROM calificaciones
        WHERE user_id = ? AND materia = ?
    '''
    cursor.execute(query, (alumno_id, materia_id))
    calificacion_existente = cursor.fetchone()

    if calificacion_existente:
        # Si existe, actualizar la calificación
        cursor.execute('''
            UPDATE calificaciones
            SET calificacion = ?
            WHERE id = ?
        ''', (calificacion, calificacion_existente['id']))
    else:
        # Si no existe, insertar nueva calificación
        cursor.execute('''
            INSERT INTO calificaciones (user_id, materia, calificacion)
            VALUES (?, ?, ?)
        ''', (alumno_id, materia_id, calificacion))

    conn.commit()
    conn.close()

    # Redirigir al usuario después de actualizar/insertar
    return redirect(url_for('ver_calificaciones'))

@app.route('/alumnos')
def alumnos():
    conn = get_db_connection()
    alumnos = conn.execute('SELECT * FROM estudiantes').fetchall()
    conn.close()

    alumnos_por_licenciatura = {}
    for alumno in alumnos:
        licenciatura = alumno["licenciatura"]
        semestre = alumno["semestre"]
        if licenciatura not in alumnos_por_licenciatura:
            alumnos_por_licenciatura[licenciatura] = {}
        if semestre not in alumnos_por_licenciatura[licenciatura]:
            alumnos_por_licenciatura[licenciatura][semestre] = []
        alumnos_por_licenciatura[licenciatura][semestre].append(dict(alumno))

    return render_template('alumnos.html', alumnos=alumnos_por_licenciatura)

def inicializar_materias_para_alumno(alumno_id, licenciatura, semestre, conn):
    # Selecciona las materias correspondientes a la licenciatura y semestre del alumno
    materias = conn.execute('SELECT id FROM materias WHERE licenciatura = ? AND semestre = ?', (licenciatura, semestre)).fetchall()
    
    # Inicializa las calificaciones para cada materia con una calificación predeterminada de 0
    for materia in materias:
        conn.execute('INSERT INTO calificaciones (user_id, materia, calificacion) VALUES (?, ?, ?)', (alumno_id, materia['id'], 0))
    conn.commit()

@app.route('/gestion_alumnos', methods=['GET'])
def gestion_alumnos():
    conn = get_db_connection()
    alumnos = conn.execute('SELECT * FROM estudiantes').fetchall()
    conn.close()

    alumnos_por_licenciatura = {}
    for alumno in alumnos:
        licenciatura = alumno["licenciatura"]
        semestre = alumno["semestre"]
        if licenciatura not in alumnos_por_licenciatura:
            alumnos_por_licenciatura[licenciatura] = {}
        if semestre not in alumnos_por_licenciatura[licenciatura]:
            alumnos_por_licenciatura[licenciatura][semestre] = []
        alumnos_por_licenciatura[licenciatura][semestre].append(dict(alumno))

    for licenciatura in alumnos_por_licenciatura:
        for semestre in alumnos_por_licenciatura[licenciatura]:
            alumnos_por_licenciatura[licenciatura][semestre] = sorted(
                alumnos_por_licenciatura[licenciatura][semestre], key=lambda x: x['nombre']
            )

    return render_template('gestion_alumnos.html', alumnos=alumnos_por_licenciatura)

@app.route('/datos_alumnos', methods=['POST'])
def datos_alumnos():
    nombre = request.form['nombre']
    matricula = request.form['matricula']
    licenciatura = request.form['licenciatura']
    semestre = request.form['semestre']

    conn = get_db_connection()

    # Verificar si ya existe un alumno con esa matrícula
    alumno_existente = conn.execute(
        'SELECT * FROM estudiantes WHERE matricula = ?', (matricula,)
    ).fetchone()

    if alumno_existente:
        # Actualizamos datos si ya existe
        conn.execute('''
            UPDATE estudiantes
            SET nombre = ?, licenciatura = ?, semestre = ?
            WHERE matricula = ?
        ''', (nombre, licenciatura, semestre, matricula))
        mensaje = f'🔄 Alumno actualizado al {semestre}° semestre.'
    else:
        # Insertamos nuevo alumno
        conn.execute('''
            INSERT INTO estudiantes (nombre, matricula, licenciatura, semestre)
            VALUES (?, ?, ?, ?)
        ''', (nombre, matricula, licenciatura, semestre))
        mensaje = f'✅ Alumno registrado correctamente.'

    conn.commit()

    # ⚠️ Redirigir de nuevo a registrar_calificacion con mensaje
    conn.close()
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
        with get_db_connection() as conn:
            cur = conn.execute('''
                INSERT INTO materias (nombre, licenciatura, semestre)
                VALUES (?, ?, ?)
            ''', (nombre, licenciatura, semestre))
            materia_id = cur.lastrowid

            # Tabla auxiliar opcional
            try:
                conn.execute('''
                    INSERT INTO licenciaturas_materias (materia_id, licenciatura, semestre)
                    VALUES (?, ?, ?)
                ''', (materia_id, licenciatura, semestre))
            except Exception:
                pass

            conn.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return 'Materia añadida', 200

        flash('Materia añadida con éxito.', 'success')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return f'Error: {str(e)}', 500
        flash(f'Ocurrió un error al añadir la materia: {e}', 'danger')

    return redirect(url_for('gestion_materias'))

def verificar_materia_duplicada(nombre, licenciatura, semestre):
    with get_db_connection() as conn:
        resultado = conn.execute('''
            SELECT 1 FROM materias
            WHERE nombre = ? AND licenciatura = ? AND semestre = ?
        ''', (nombre, licenciatura, semestre)).fetchone()
    return resultado is not None

@app.route('/delete_alumno', methods=['POST'])
def delete_alumno():
    alumno_id = request.form['id']
    conn = get_db_connection()
    conn.execute('DELETE FROM estudiantes WHERE id = ?', (alumno_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('alumnos'))

@app.route('/error')
def error():
    return 'Nombre de usuario o contraseña incorrectos. Por favor, intenta nuevamente.'

@app.route('/materias')
def gestion_materias():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('index'))

    conn = get_db_connection()

    query = '''
        SELECT m.*, c.calificacion
        FROM materias m
        LEFT JOIN calificaciones c ON m.id = c.materia AND c.user_id = ?
        ORDER BY m.licenciatura, m.semestre, m.nombre
    '''
    materias = conn.execute(query, (user_id,)).fetchall()
    conn.close()

    # Agrupar materias por licenciatura y semestre
    materias_por_licenciatura = {}
    for materia in materias:
        licenciatura = materia["licenciatura"]
        semestre = materia["semestre"]

        if licenciatura not in materias_por_licenciatura:
            materias_por_licenciatura[licenciatura] = {}

        if semestre not in materias_por_licenciatura[licenciatura]:
            materias_por_licenciatura[licenciatura][semestre] = []

        materias_por_licenciatura[licenciatura][semestre].append(dict(materia))

    return render_template('materias.html', materias=materias_por_licenciatura)

@app.route('/ver_materias')
def ver_materias():
    conn = get_db_connection()
    materias = conn.execute('SELECT * FROM materias ORDER BY licenciatura, semestre, nombre').fetchall()
    conn.close()

    estructura = {}
    for m in materias:
        lic = m['licenciatura']
        sem = str(m['semestre'])
        estructura.setdefault(lic, {}).setdefault(sem, []).append(m)

    # Asegura que los 7 semestres estén presentes aunque estén vacíos
    for lic in estructura:
        for s in range(1, 8):
            estructura[lic].setdefault(str(s), [])

    return render_template('ver_materias.html', materias=estructura)

@app.route('/eliminar_materia/<int:materia_id>', methods=['POST'])
def eliminar_materia(materia_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM materias WHERE id = ?', (materia_id,))
    conn.commit()
    conn.close()
    flash('Materia eliminada exitosamente.', 'success')
    return redirect(url_for('ver_materias'))
 
@app.route('/obtener_materias', methods=['GET'])
def obtener_materias():
    licenciatura = request.args.get('licenciatura')
    semestre = request.args.get('semestre')

    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = '''
        SELECT m.id, m.nombre 
        FROM materias m
        JOIN licenciaturas_materias lm ON m.id = lm.materia_id
        WHERE lm.licenciatura = ? AND lm.semestre = ?
    '''
    cursor.execute(query, (licenciatura, semestre))
    materias = cursor.fetchall()
    conn.close()

    materias_list = [{'id': m['id'], 'nombre': m['nombre']} for m in materias]
    return jsonify({'materias': materias_list})

@app.route('/gestionar_materias', methods=['GET', 'POST'])
def gestionar_materias():
    conn = get_db_connection()
    
    # Consulta para obtener todas las materias duplicadas
    query = '''
        SELECT id, nombre, licenciatura, semestre
        FROM materias
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM materias
            GROUP BY nombre, licenciatura, semestre
        )
    '''
    materias_duplicadas = conn.execute(query).fetchall()
    conn.close()

    if request.method == 'POST':
        # Si se envía un formulario con IDs a eliminar
        ids_para_eliminar = request.form.getlist('materias_eliminar')
        conn = get_db_connection()
        for materia_id in ids_para_eliminar:
            conn.execute('DELETE FROM materias WHERE id = ?', (materia_id,))
        conn.commit()
        conn.close()
        flash('Las materias seleccionadas han sido eliminadas.', 'success')
        return redirect(url_for('gestionar_materias'))

    return render_template('gestionar_materias.html', materias_duplicadas=materias_duplicadas)

@app.route('/materias_calificadas', methods=['GET'])
def materias_calificadas():
    user_id = request.args.get('user_id')  # ID del alumno
    licenciatura = request.args.get('licenciatura')  # Licenciatura seleccionada
    semestre = request.args.get('semestre')  # Semestre seleccionado

    conn = get_db_connection()
    query = '''
        SELECT 
            c.calificacion, 
            m.nombre AS materia_nombre, 
            m.semestre, 
            e.nombre AS estudiante_nombre, 
            e.licenciatura
        FROM calificaciones c
        JOIN materias m ON c.materia = m.id
        JOIN estudiantes e ON c.user_id = e.id
        WHERE e.id = ? AND e.licenciatura = ? AND m.semestre = ?
        ORDER BY m.semestre;
    '''
    materias = conn.execute(query, (user_id, licenciatura, semestre)).fetchall()
    conn.close()

    return render_template('materias_calificadas.html', materias=materias, user_id=user_id)

@app.route('/editar_calificacion/<int:calificacion_id>', methods=['GET', 'POST'])
def editar_calificacion(calificacion_id):
    conn = get_db_connection()
    if request.method == 'POST':
        nueva_calificacion = request.form['calificacion']
        conn.execute('UPDATE calificaciones SET calificacion = ? WHERE id = ?', (nueva_calificacion, calificacion_id))
        conn.commit()
        conn.close()
        flash('Calificación actualizada correctamente.', 'success')
        return redirect(url_for('ver_calificaciones', user_id=request.form['user_id']))

    # Obtener la información de la calificación actual
    calificacion = conn.execute('SELECT * FROM calificaciones WHERE id = ?', (calificacion_id,)).fetchone()
    conn.close()

    return render_template('editar_calificacion.html', calificacion=calificacion)

@app.route('/eliminar_duplicados', methods=['GET', 'POST'])
def eliminar_duplicados():
    if request.method == 'GET':
        conn = get_db_connection()
        # Identifica IDs duplicados
        ids_duplicados = conn.execute('''
            WITH cte AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY user_id, materia ORDER BY id
                ) AS rn
                FROM calificaciones
            )
            SELECT id FROM cte WHERE rn > 1;
        ''').fetchall()

        duplicados_ids = [row['id'] for row in ids_duplicados]

        # Si hay duplicados, obtener sus detalles
        if duplicados_ids:
            placeholders = ','.join(['?'] * len(duplicados_ids))
            calificaciones_duplicadas = conn.execute(f'''
                SELECT c.id, c.calificacion,
                       m.nombre AS materia_nombre,
                       e.nombre AS estudiante_nombre
                FROM calificaciones c
                JOIN materias m ON c.materia = m.id
                JOIN estudiantes e ON c.user_id = e.id
                WHERE c.id IN ({placeholders});
            ''', duplicados_ids).fetchall()
        else:
            calificaciones_duplicadas = []

        conn.close()
        return render_template('eliminar_duplicados.html', calificaciones=calificaciones_duplicadas)

    elif request.method == 'POST':
        duplicados_ids = request.form.getlist('duplicados')
        if not duplicados_ids:
            flash('No se seleccionó ninguna calificación para eliminar.', 'danger')
            return redirect(url_for('eliminar_duplicados'))

        conn = get_db_connection()
        conn.executemany('DELETE FROM calificaciones WHERE id = ?', [(id,) for id in duplicados_ids])
        conn.commit()
        conn.close()

        flash(f'Se eliminaron {len(duplicados_ids)} calificaciones duplicadas.', 'success')
        return redirect(url_for('eliminar_duplicados'))

    # Fallback por si llega una solicitud inesperada
    return redirect(url_for('ver_calificaciones', user_id=session.get('user_id')))
    
if __name__ == '__main__':
    verificar_datos_materias()
    app.run(debug=True)
