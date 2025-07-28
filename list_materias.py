import sqlite3

def list_materias():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM materias;")
    materias = cursor.fetchall()
    
    print("Contenido de la tabla 'materias':")
    for materia in materias:
        print(materia)
    
    conn.close()

if __name__ == "__main__":
    list_materias()
