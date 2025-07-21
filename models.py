from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Estudiante(Base):
    __tablename__ = 'estudiantes'
    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    matricula = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)

class Calificacion(Base):
    __tablename__ = 'calificaciones'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('estudiantes.id'), nullable=False)
    materia = Column(String, nullable=False)
    calificacion = Column(Integer, nullable=False)

class Materia(Base):
    __tablename__ = 'materias'
    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    id_personalizado = Column(Integer)
