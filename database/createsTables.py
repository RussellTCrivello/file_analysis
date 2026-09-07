import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def ensure_database_exists(dbname: str, user: str, password: str, host: str = "localhost", port: int = 5432):
    """
    Ensure database exists, create it if it doesn't.
    Uses template0 to avoid encoding conflicts (UTF8 vs WIN1252).
    """
    try:
        # Connect to postgres database (default database)
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
        
        if not exists:
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
        print(f"❌ Error ensuring database exists: {e}")
        raise


# Ensure database exists before connecting
ensure_database_exists("analysis", "postgres", "eggarf123", "localhost", 5432)

conn = psycopg2.connect(
    dbname="analysis",
    user="postgres",
    password="eggarf123",
    host="localhost",
    port=5432
)

cursor = conn.cursor()

# Enable pg_trgm extension for trigram matching (required for gin_trgm_ops)
cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")



# Create 'words' table
create_words_table = """
CREATE TABLE IF NOT EXISTS words (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    word TEXT UNIQUE NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_words_word ON words USING btree (word);
    CREATE INDEX IF NOT EXISTS idx_words_word_gin ON words USING gin (word gin_trgm_ops);
    CREATE INDEX IF NOT EXISTS idx_words_word_hash ON words USING hash (word);

"""
create_categorys_table = """
CREATE TABLE IF NOT EXISTS categorys (
        id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        word_id INTEGER UNIQUE NOT NULL,
        FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE ON UPDATE CASCADE
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_categorys_word_id ON categorys (word_id);
    CREATE INDEX IF NOT EXISTS idx_categorys_word_id ON categorys USING btree (word_id);
 
"""
create_word_categorys_table = """
CREATE TABLE IF NOT EXISTS words_categorys (
    word_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categorys(id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (word_id) REFERENCES words(id) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_wc_word_id ON words_categorys (word_id);
CREATE INDEX IF NOT EXISTS idx_wc_category_id ON words_categorys (category_id);

-- You can remove the CREATE UNIQUE INDEX and just add the constraint in the ALTER TABLE statement later
CREATE INDEX IF NOT EXISTS idx_words_categorys_word_id ON words_categorys USING btree (word_id);
CREATE INDEX IF NOT EXISTS idx_words_categorys_category_id ON words_categorys USING btree (category_id);
CREATE INDEX IF NOT EXISTS idx_words_categorys_word_cat ON words_categorys USING btree (word_id, category_id);

-- Add the unique constraint using ALTER TABLE (if it doesn't exist)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'unique_word_category'
    ) THEN
        ALTER TABLE words_categorys
        ADD CONSTRAINT unique_word_category UNIQUE (word_id, category_id);
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;
"""
create_words_paths_table = """
CREATE TABLE IF NOT EXISTS words_paths (
    path_id INTEGER NOT NULL,
    word_id INTEGER NOT NULL,
    FOREIGN KEY (path_id) REFERENCES paths(id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (word_id) REFERENCES words(id)  ON DELETE CASCADE ON UPDATE CASCADE,
    word_count INT,
    position_indexer BYTEA NOT NULL
);
"""
create_keywords_paths_table = """
CREATE TABLE IF NOT EXISTS keywords_paths (
    path_id INTEGER NOT NULL,
    keyword_id INTEGER NOT NULL,
    FOREIGN KEY (path_id) REFERENCES paths(id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (keyword_id) REFERENCES keywords(id) ON DELETE CASCADE ON UPDATE CASCADE,
    word_count INT
);
CREATE INDEX IF NOT EXISTS idx_keywords_paths_path_id ON keywords_paths (path_id);
CREATE INDEX IF NOT EXISTS idx_keywords_paths_keyword_id ON keywords_paths (keyword_id);
CREATE INDEX IF NOT EXISTS idx_keywords_paths_path_keyword ON keywords_paths (path_id, keyword_id);

-- Add the unique constraint using ALTER TABLE (if it doesn't exist)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'unique_keywords_paths_path_keyword'
    ) THEN
        ALTER TABLE keywords_paths
        ADD CONSTRAINT unique_keywords_paths_path_keyword UNIQUE (path_id, keyword_id);
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;
"""
create_keywords_table = """
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    keyword BYTEA UNIQUE NOT NULL,
    category_id INTEGER NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categorys(id) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_keywords_category_id ON keywords (category_id);
CREATE INDEX IF NOT EXISTS idx_keywords_category_id ON keywords USING btree (category_id);

"""
# Create 'big_text' table
create_contents_table = """
CREATE TABLE IF NOT EXISTS contents (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_data BYTEA,
    content_date Date NULL,
    path_id INTEGER NOT NULL,
    FOREIGN KEY (path_id) REFERENCES paths(id) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_contents_path_id ON contents (path_id);
CREATE INDEX IF NOT EXISTS idx_contents_content_date ON contents (content_date DESC);
CREATE INDEX IF NOT EXISTS idx_contents_path_date ON contents (path_id, content_date);
CREATE INDEX IF NOT EXISTS idx_contents_path_id ON contents USING btree (path_id);
CREATE INDEX IF NOT EXISTS idx_contents_date ON contents USING btree (content_date);
CREATE INDEX IF NOT EXISTS idx_contents_path_date ON contents USING btree (path_id, content_date);

"""

create_titles_content_table = """
CREATE TABLE IF NOT EXISTS titles_content (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title_data BYTEA,
    title_status VARCHAR(10) NOT NULL CHECK (title_status IN ('Main', 'Branch')) DEFAULT 'Main',
    title_content_id INTEGER NULL,
    path_id INTEGER NOT NULL,
    FOREIGN KEY (title_content_id) REFERENCES titles_content(id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (path_id) REFERENCES paths(id) ON DELETE CASCADE ON UPDATE CASCADE
);
"""

create_sides_table = """
CREATE TABLE IF NOT EXISTS sides(
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    importance DECIMAL(5,4) NOT NULL,
    date_creation Date NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sides_name ON sides (name);
CREATE INDEX IF NOT EXISTS idx_sides_importance ON sides (importance DESC);
CREATE INDEX IF NOT EXISTS idx_sides_date_creation ON sides (date_creation DESC);
CREATE INDEX IF NOT EXISTS idx_sides_name ON sides USING btree (name);
CREATE INDEX IF NOT EXISTS idx_sides_importance ON sides USING btree (importance DESC);
CREATE INDEX IF NOT EXISTS idx_sides_date_creation ON sides USING btree (date_creation);
    
"""
create_source_table = """
CREATE TABLE IF NOT EXISTS sources(
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    job VARCHAR(255) NOT NULL ,
    importance DECIMAL(5,4) NOT NULL,
    country VARCHAR(255) NOT NULL,
    city VARCHAR(255) NULL,
    description VARCHAR(255) NULL,
    accounts VARCHAR(255) NULL ,
    note VARCHAR(255) NULL,
    attachments VARCHAR(255) NULL,
    ownership VARCHAR(255) NULL,
    access_status VARCHAR(255) NULL,
    entry_date TIMESTAMP NULL,
    category_id INTEGER NULL,
    FOREIGN KEY (category_id) REFERENCES categorys(id) ON DELETE SET NULL ON UPDATE CASCADE,
    date_creation Date NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_name ON sources (name);
CREATE INDEX IF NOT EXISTS idx_sources_country ON sources (country);
CREATE INDEX IF NOT EXISTS idx_sources_job ON sources (job);
CREATE INDEX IF NOT EXISTS idx_sources_importance ON sources (importance DESC);
CREATE INDEX IF NOT EXISTS idx_sources_date_creation ON sources (date_creation DESC);
CREATE INDEX IF NOT EXISTS idx_sources_ownership ON sources (ownership);
CREATE INDEX IF NOT EXISTS idx_sources_access_status ON sources (access_status);
CREATE INDEX IF NOT EXISTS idx_sources_entry_date ON sources (entry_date DESC);
CREATE INDEX IF NOT EXISTS idx_sources_category_id ON sources (category_id);
CREATE INDEX IF NOT EXISTS idx_sources_name ON sources USING btree (name);
CREATE INDEX IF NOT EXISTS idx_sources_importance ON sources USING btree (importance DESC);
CREATE INDEX IF NOT EXISTS idx_sources_country ON sources USING btree (country);
CREATE INDEX IF NOT EXISTS idx_sources_city ON sources USING btree (city);
CREATE INDEX IF NOT EXISTS idx_sources_date_creation ON sources USING btree (date_creation);
CREATE INDEX IF NOT EXISTS idx_sources_ownership ON sources USING btree (ownership);
CREATE INDEX IF NOT EXISTS idx_sources_access_status ON sources USING btree (access_status);
CREATE INDEX IF NOT EXISTS idx_sources_entry_date ON sources USING btree (entry_date);
CREATE INDEX IF NOT EXISTS idx_sources_category_id ON sources USING btree (category_id);
"""

create_hashs_table = """
CREATE TABLE IF NOT EXISTS hashs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hash CHAR(64) NOT NULL,
    side_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    FOREIGN KEY (side_id) REFERENCES sides(id),
    FOREIGN KEY (source_id) REFERENCES sources(id),
    UNIQUE (hash, source_id, side_id)
);

CREATE INDEX IF NOT EXISTS idx_hashs_source_id ON hashs (source_id);
CREATE INDEX IF NOT EXISTS idx_hashs_side_id ON hashs (side_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hashs_hash_source_side ON hashs (hash, source_id, side_id);

-- Remove old UNIQUE constraint if it exists (hash, source_id only)
DO $$ 
BEGIN
    ALTER TABLE hashs DROP CONSTRAINT IF EXISTS hashs_hash_source_id_key;
    DROP INDEX IF EXISTS idx_hashs_hash_source;
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;
CREATE INDEX IF NOT EXISTS idx_hashs_hash ON hashs USING btree (hash);
CREATE INDEX IF NOT EXISTS idx_hashs_source_id ON hashs USING btree (source_id);
CREATE INDEX IF NOT EXISTS idx_hashs_side_id ON hashs USING btree (side_id);
CREATE INDEX IF NOT EXISTS idx_hashs_hash_source_side ON hashs USING btree (hash, source_id, side_id);

"""

create_paths_table = """
CREATE TABLE IF NOT EXISTS paths (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    file_type VARCHAR(100) NOT NULL,
    file_status VARCHAR(10) NOT NULL CHECK (file_status IN ('Read', 'Unread')) DEFAULT 'Unread',
    file_date DATE NOT NULL,
    date_creation DATE NOT NULL,
    hash_id INTEGER NOT NULL,
    coordinates TEXT NULL,
    FOREIGN KEY (hash_id) REFERENCES hashs(id)
);
"""
    # Punctuation table
create_punctuation_table = """
    CREATE TABLE IF NOT EXISTS punctuation (
        id SERIAL PRIMARY KEY,
        punctuation_text TEXT UNIQUE NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_punctuation_text ON punctuation USING btree (punctuation_text);
    CREATE INDEX IF NOT EXISTS idx_punctuation_text_hash ON punctuation USING hash (punctuation_text);
    """


   # Alerts table
create_alerts_table = """
    CREATE TABLE IF NOT EXISTS alerts (
        id SERIAL PRIMARY KEY,
        type VARCHAR(50) NOT NULL,
        priority VARCHAR(20) NOT NULL,
        title VARCHAR(500) NOT NULL,
        message TEXT NOT NULL,
        file_id INTEGER REFERENCES paths(id) ON DELETE CASCADE,
        file_name VARCHAR(500),
        file_path TEXT,
        event_date DATE,
        metadata JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        read BOOLEAN DEFAULT FALSE,
        dismissed BOOLEAN DEFAULT FALSE
    );
    CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(type);
    CREATE INDEX IF NOT EXISTS idx_alerts_priority ON alerts(priority);
    CREATE INDEX IF NOT EXISTS idx_alerts_event_date ON alerts(event_date);
    CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
    CREATE INDEX IF NOT EXISTS idx_alerts_dismissed ON alerts(dismissed);
    CREATE INDEX IF NOT EXISTS idx_alerts_read ON alerts(read);
    CREATE INDEX IF NOT EXISTS idx_alerts_file_id ON alerts(file_id);
    """

# # # Execute table creation
cursor.execute(create_words_table)

cursor.execute(create_categorys_table)
cursor.execute(create_word_categorys_table)
cursor.execute(create_sides_table)
cursor.execute(create_source_table)
cursor.execute(create_hashs_table)
cursor.execute(create_paths_table)
cursor.execute(create_titles_content_table)
cursor.execute(create_keywords_table)
cursor.execute(create_contents_table)
cursor.execute(create_words_paths_table)
cursor.execute(create_keywords_paths_table)

cursor.execute(create_alerts_table)
cursor.execute(create_punctuation_table)
# 
# cursor.execute("""DROP TABLE IF EXISTS words_categorys CASCADE""")
# # cursor.execute("DROP TABLE IF EXISTS words CASCADE")
# cursor.execute("DROP TABLE IF EXISTS sides CASCADE")
# cursor.execute("DROP TABLE IF EXISTS hashs CASCADE")
# cursor.execute("DROP TABLE IF EXISTS paths CASCADE")
# cursor.execute("DROP TABLE IF EXISTS sources CASCADE")
# cursor.execute("DROP TABLE IF EXISTS words_paths CASCADE")
# cursor.execute("DROP TABLE IF EXISTS titles_content CASCADE")
# cursor.execute("DROP TABLE IF EXISTS contents CASCADE")
# cursor.execute("DROP TABLE IF EXISTS keywords_paths CASCADE")
# cursor.execute("DROP TABLE IF EXISTS keywords CASCADE")

# cursor.execute("DROP TABLE IF EXISTS categorys CASCADE")
# cursor.execute("DROP TABLE IF EXISTS words CASCADE")
# cursor.execute("DROP TABLE IF EXISTS alerts CASCADE")
# cursor.execute("DROP TABLE IF EXISTS punctuation CASCADE")

# Commit and close
conn.commit()
cursor.close()
conn.close()

print("Tables created successfully.")
