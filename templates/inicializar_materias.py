import sqlite3

def init_db():
    conn = sqlite3.connect('materias.db')
    cursor = conn.cursor()

    # Crear la tabla de materias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            licenciatura TEXT NOT NULL,
            semestre INTEGER NOT NULL
        )
    ''')

    # Insertar algunas materias de ejemplo
    materias = [
        ('Matemáticas I', 'Matematicas', 1),
        ('Matemáticas II', 'Matematicas', 2),
        ('Literatura I', 'Español', 1),
        ('Literatura II', 'Español', 2),
        ('Ciencias Naturales I', 'Primaria', 1),
        ('Ciencias Naturales II', 'Primaria', 2),
    ]

    cursor.executemany('''
        INSERT INTO materias (nombre, licenciatura, semestre)
        VALUES (?, ?, ?)
    ''', materias)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
