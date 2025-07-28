CREATE DATABASE sistema_calificaciones;

USE sistema_calificaciones;

CREATE TABLE estudiantes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    matricula VARCHAR(20) NOT NULL UNIQUE,
    username VARCHAR(24) NOT NULL,
    password VARCHAR(12) NOT NULL
);

INSERT INTO estudiantes (matricula, username, password) VALUES ('20240001', 'juan', '123456');
INSERT INTO estudiantes (matricula, username, password) VALUES ('20240002', 'maria', 'abcdef');
