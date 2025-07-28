import sqlite3

def update_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Crear la tabla nuevas_calificaciones si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nuevas_calificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            materia INTEGER NOT NULL,
            calificacion INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES estudiantes (id),
            FOREIGN KEY (materia) REFERENCES materias (id)
        )
    ''')

    # Insertar datos de ejemplo en nuevas_calificaciones
    cursor.execute('''
        INSERT INTO nuevas_calificaciones (user_id, materia, calificacion)
        SELECT user_id, materia, calificacion FROM calificaciones
    ''')

    conn.commit()
    conn.close()
    print("Base de datos actualizada correctamente.")

if __name__ == "__main__":
    update_db()
