import sqlite3

def verify_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Verificar las tablas existentes
    cursor.execute("PRAGMA table_info(materias)")
    columns = cursor.fetchall()
    print("Estructura de la tabla 'materias':")
    for column in columns:
        print(column)

    # Verificar datos
    cursor.execute("SELECT * FROM materias")
    rows = cursor.fetchall()
    print("\nDatos de la tabla 'materias':")
    for row in rows:
        print(row)

    conn.close()

if __name__ == "__main__":
    verify_db()
