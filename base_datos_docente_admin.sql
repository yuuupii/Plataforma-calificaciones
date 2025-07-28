CREATE TABLE IF NOT EXISTS maestros (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT UNIQUE NOT NULL,
  contrasena TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS administrativos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT UNIQUE NOT NULL,
  contrasena TEXT NOT NULL
);

-- Datos de ejemplo
INSERT INTO maestros (usuario, contrasena) VALUES ('profe1', 'clave123');
INSERT INTO administrativos (usuario, contrasena) VALUES ('admin1', 'admin123');
