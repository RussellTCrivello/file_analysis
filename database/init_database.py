"""
Database initialization script.
Creates the database if it doesn't exist, using template0 to avoid encoding conflicts.
"""
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sys


def create_database(dbname: str, user: str, password: str, host: str = "localhost", port: int = 5432):
    """
    Create a database if it doesn't exist.
    Uses template0 to avoid encoding conflicts.
    
    Args:
        dbname: Name of the database to create
        user: PostgreSQL username
        password: PostgreSQL password
        host: PostgreSQL host (default: localhost)
        port: PostgreSQL port (default: 5432)
    """
    # Connect to postgres database (default database)
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=user,
            password=password,
            host=host,
            port=port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (dbname,)
        )
        exists = cursor.fetchone()
        
        if exists:
            print(f"Database '{dbname}' already exists.")
            cursor.close()
            conn.close()
            return True
        
        # Create database using template0 with UTF8 encoding
        # template0 doesn't have locale/encoding restrictions
        print(f"Creating database '{dbname}' with UTF8 encoding using template0...")
        cursor.execute(
            sql.SQL("CREATE DATABASE {} WITH ENCODING 'UTF8' TEMPLATE template0").format(
                sql.Identifier(dbname)
            )
        )
        
        print(f"✅ Database '{dbname}' created successfully.")
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Error creating database: {e}")
        return False


if __name__ == "__main__":
    # Default values (can be overridden via command line or environment)
    import os
    
    dbname = os.getenv('DB_NAME', 'analysis')
    user = os.getenv('DB_USER', 'postgres')
    password = os.getenv('DB_PASSWORD', 'eggarf123')
    host = os.getenv('DB_HOST', 'localhost')
    port = int(os.getenv('DB_PORT', '5432'))
    
    # Allow command line arguments
    if len(sys.argv) > 1:
        dbname = sys.argv[1]
    if len(sys.argv) > 2:
        user = sys.argv[2]
    if len(sys.argv) > 3:
        password = sys.argv[3]
    
    success = create_database(dbname, user, password, host, port)
    sys.exit(0 if success else 1)
