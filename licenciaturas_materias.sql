# Después de insertar en la tabla "materias"
cur = conn.execute('INSERT INTO materias (nombre, licenciatura, semestre) VALUES (?, ?, ?)',
                   (nombre, licenciatura, semestre))
materia_id = cur.lastrowid

# Insertar también en licenciaturas_materias
conn.execute('INSERT INTO licenciaturas_materias (materia_id, licenciatura, semestre) VALUES (?, ?, ?)',
             (materia_id, licenciatura, semestre))
conn.commit()





PRAGMA foreign_keys = ON;

-- Tabla de materias
CREATE TABLE IF NOT EXISTS materias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    licenciatura TEXT NOT NULL,
    semestre INTEGER NOT NULL
);

-- Tabla puente entre licenciaturas y materias
CREATE TABLE IF NOT EXISTS licenciaturas_materias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    materia_id INTEGER NOT NULL,
    licenciatura TEXT NOT NULL,
    semestre INTEGER NOT NULL,
    UNIQUE(materia_id, licenciatura, semestre),
    FOREIGN KEY(materia_id) REFERENCES materias(id) ON DELETE CASCADE
);

-- Tabla de estudiantes
CREATE TABLE IF NOT EXISTS estudiantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    matricula TEXT NOT NULL UNIQUE,
    licenciatura TEXT NOT NULL,
    semestre INTEGER NOT NULL
);

-- Tabla de calificaciones
CREATE TABLE IF NOT EXISTS calificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    materia INTEGER NOT NULL,
    calificacion INTEGER NOT NULL,
    UNIQUE(user_id, materia), -- Evitar duplicados
    FOREIGN KEY(user_id) REFERENCES estudiantes(id) ON DELETE CASCADE,
    FOREIGN KEY(materia) REFERENCES materias(id) ON DELETE CASCADE
);
