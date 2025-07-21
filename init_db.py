import sqlite3

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Crear la tabla de estudiantes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estudiantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            matricula TEXT NOT NULL,
            licenciatura TEXT NOT NULL,
            semestre INTEGER NOT NULL
        )
    ''')

    # Crear la tabla de materias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            licenciatura TEXT NOT NULL,
            semestre INTEGER NOT NULL
        )
    ''')

    # Crear la tabla de calificaciones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            materia INTEGER NOT NULL,
            calificacion INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES estudiantes (id),
            FOREIGN KEY (materia) REFERENCES materias (id)
        )
    ''')

    # Crear la tabla de relaciones licenciaturas-materias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licenciaturas_materias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            licenciatura TEXT NOT NULL,
            semestre INTEGER NOT NULL,
            materia_id INTEGER NOT NULL,
            FOREIGN KEY (materia_id) REFERENCES materias (id)
        )
    ''')

    # Insertar materias de prueba
    cursor.execute("INSERT INTO materias (nombre, licenciatura, semestre) VALUES ('Matemáticas I', 'Ingeniería Civil', 1)")
    cursor.execute("INSERT INTO materias (nombre, licenciatura, semestre) VALUES ('Física I', 'Ingeniería Civil', 1)")
    cursor.execute("INSERT INTO materias (nombre, licenciatura, semestre) VALUES ('Programación I', 'Ingeniería Informática', 1)")

    # Insertar relaciones de prueba
    cursor.execute("INSERT INTO licenciaturas_materias (licenciatura, semestre, materia_id) VALUES ('Ingeniería Civil', 1, 1)")
    cursor.execute("INSERT INTO licenciaturas_materias (licenciatura, semestre, materia_id) VALUES ('Ingeniería Civil', 1, 2)")
    cursor.execute("INSERT INTO licenciaturas_materias (licenciatura, semestre, materia_id) VALUES ('Ingeniería Informática', 1, 3)")

    conn.commit()
    conn.close()
    print("Base de datos inicializada correctamente con datos de prueba.")

if __name__ == "__main__":
    init_db()
