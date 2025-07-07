from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
#from databases import Database
from config import URL_DATABASE


engine=create_engine(URL_DATABASE)

@event.listens_for(engine, "connect")
def set_timezone(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET time_zone = '+00:00';")  # UTC offset
    cursor.close()

SessionLocal=sessionmaker(autocommit=False,autoflush=False,bind=engine)

Base=declarative_base()

#database_db = Database(URL_DATABASE)