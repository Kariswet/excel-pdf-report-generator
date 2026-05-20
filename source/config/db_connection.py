from psycopg2 import pool, OperationalError
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
from loguru import logger
import os
import pymongo
import threading

load_dotenv()
class DatabaseManager:
    """
    Unified Production-Ready Database Manager:
    ✅ PostgreSQL Pool
    ✅ MongoDB Client Pool
    ✅ Elasticsearch Client Pool
    ✅ Singleton Pattern
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
                    cls._instance._init_all()
        return cls._instance

    # =========================
    # INIT ALL CONNECTIONS
    # =========================
    def _init_all(self):
        self._init_postgres_pool()
        self._init_mongo_client()
        self._init_elasticsearch_client()

    # =========================
    # POSTGRESQL (POOL)
    # =========================
    def _init_postgres_pool(self):
        self.PG_URI = (
            f"postgresql://{os.getenv('POSTGRE_USER')}:{os.getenv('POSTGRE_PASS')}"
            f"@{os.getenv('POSTGRE_HOST')}:{os.getenv('POSTGRE_PORT')}"
            f"/{os.getenv('POSTGRE_DB')}"
        )

        try:
            self._pg_pool = pool.SimpleConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=self.PG_URI
            )
            logger.info("✅ PostgreSQL pool initialized")

        except OperationalError as e:
            logger.error(f"❌ PostgreSQL pool init failed: {e}")
            raise RuntimeError("PostgreSQL unavailable")

    def get_pg_conn(self):
        """
        ✅ Safe PG connection with auto-reconnect
        """
        try:
            conn = self._pg_pool.getconn()
            conn.autocommit = True
            return conn

        except Exception:
            logger.warning("♻️ PostgreSQL pool broken, reconnecting...")
            self._init_postgres_pool()
            conn = self._pg_pool.getconn()
            conn.autocommit = True
            return conn

    def release_pg_conn(self, conn):
        try:
            self._pg_pool.putconn(conn)
        except Exception:
            pass

    # =========================
    # MONGODB (CACHED CLIENT)
    # =========================
    def _init_mongo_client(self):
        try:
            self.MONGO_SRV = os.getenv("DB_MONGO_SRV")

            self._mongo_client = pymongo.MongoClient(
                self.MONGO_SRV,
                maxPoolSize=20,
                minPoolSize=2,
                serverSelectionTimeoutMS=5000
            )

            # ✅ Connectivity check
            self._mongo_client.admin.command("ping")

            logger.info("✅ MongoDB connected")

        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            raise RuntimeError("MongoDB unavailable")

    def get_mongo_collection(self, db, collection):
        return self._mongo_client[db][collection]

    # =========================
    # ELASTICSEARCH (CACHED + RETRY)
    # =========================
    def _init_elasticsearch_client(self):
        try:
            self.ES_URI = os.getenv("ES_VORTEX_URI")
            self.ES_USERNAME = os.getenv("ES_VORTEX_USER")
            self.ES_PASSWORD = os.getenv("ES_VORTEX_PASS")

            self._es_client = Elasticsearch(
                self.ES_URI,
                basic_auth=(self.ES_USERNAME, self.ES_PASSWORD),
                request_timeout=30,
                retry_on_timeout=True,
                max_retries=3
            )

            if not self._es_client.ping():
                raise ConnectionError("Elasticsearch not responding")

            logger.info("✅ Elasticsearch connected")

        except Exception as e:
            logger.error(f"❌ Elasticsearch connection failed: {e}")
            raise RuntimeError("Elasticsearch unavailable")

    def get_es(self):
        """
        ✅ Safe Elasticsearch getter with auto-reconnect
        """
        try:
            if self._es_client and self._es_client.ping():
                return self._es_client
        except Exception:
            logger.warning("♻️ Elasticsearch reconnecting...")
            self._init_elasticsearch_client()

        return self._es_client

    # =========================
    # GRACEFUL SHUTDOWN (OPTIONAL)
    # =========================
    def close_all(self):
        try:
            if self._mongo_client:
                self._mongo_client.close()

            if self._pg_pool:
                self._pg_pool.closeall()

            logger.info("✅ All DB connections closed safely")

        except Exception:
            pass