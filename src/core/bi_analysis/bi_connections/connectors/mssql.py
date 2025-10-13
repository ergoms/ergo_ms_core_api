from sqlalchemy import create_engine

def get_mssql_engine():
    return create_engine("mssql+pyodbc://user:password@host/dbname?driver=ODBC+Driver+17+for+SQL+Server")