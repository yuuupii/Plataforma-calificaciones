import sqlite3

def check_tables():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Agregar mensaje de depuración para verificar la conexión
    print("Conexión a la base de datos establecida.")

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    # Agregar mensaje de depuración para verificar la consulta
    print("Consulta ejecutada, recuperando tablas...")

    print("Tablas en la base de datos:")
    for table in tables:
        print(table[0])
    
    conn.close()
    print("Conexión a la base de datos cerrada.")

if __name__ == "__main__":
    check_tables()
