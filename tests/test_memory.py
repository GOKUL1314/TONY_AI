"""
Unit and Integration Tests for TONY AI Stage 4: Long-Term Memory & Context System.
Tests cover:
- SQLite persistence and schema initialization
- MemoryManager CRUD, superseding, deduplication, and categories
- MemoryExtractor intent classification, entity extraction, and secret blocking
- MemoryRetriever relevance scoring and context block generation
- Memory REST API endpoints (/api/memory, /api/memory/search, /api/memory/stats)
- End-to-end Chat memory injection and cross-restart persistence
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime

from pathlib import Path

from app import create_app
from config.settings import Config
from memory.database import MemoryDatabase
from memory.models import MemoryItem
from memory.manager import MemoryManager
from memory.extractor import MemoryExtractor
from memory.retriever import KeywordMemoryRetriever


class TestMemoryDatabase(unittest.TestCase):
    """Test lower-level SQLite database schema and connection operations."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")
        self.db = MemoryDatabase(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_initialization(self):
        """Verify SQLite tables and indexes are created properly."""
        self.assertTrue(os.path.exists(self.db_path))
        with self.db.get_cursor() as cur:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row["name"] for row in cur.fetchall()]
            self.assertIn("memories", tables)
            cur.execute("SELECT name FROM sqlite_master WHERE type='index';")
            indexes = [row["name"] for row in cur.fetchall()]
            self.assertIn("idx_memories_key", indexes)
            self.assertIn("idx_memories_category", indexes)

    def test_basic_crud_sql(self):
        """Test basic SQL insertions, updates, and soft deletes."""
        now = datetime.now().isoformat()
        with self.db.get_cursor() as cur:
            cur.execute(
                """INSERT INTO memories 
                   (memory_key, memory_value, category, importance, source, created_at, updated_at, last_accessed_at, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                ("user_name", "Gokul", "identity", 5, "user_explicit", now, now, now)
            )
            item_id = cur.lastrowid

        with self.db.get_cursor() as cur:
            cur.execute("SELECT * FROM memories WHERE id = ?", (item_id,))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["memory_key"], "user_name")
            self.assertEqual(row["memory_value"], "Gokul")
            self.assertEqual(row["importance"], 5)

        # Soft delete
        with self.db.get_cursor() as cur:
            cur.execute("UPDATE memories SET is_active = 0 WHERE id = ?", (item_id,))

        with self.db.get_cursor() as cur:
            cur.execute("SELECT * FROM memories WHERE id = ? AND is_active = 1", (item_id,))
            self.assertIsNone(cur.fetchone())


class TestMemoryManager(unittest.TestCase):
    """Test business logic in MemoryManager."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "manager_test.db")
        self.db = MemoryDatabase(db_path=self.db_path)
        self.manager = MemoryManager(database=self.db)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_and_retrieve_memory(self):
        """Test adding and retrieving a single memory item."""
        item = self.manager.remember(
            key="user_name",
            value="Gokul",
            category="identity",
            importance=5,
            source="user_explicit"
        )
        self.assertIsNotNone(item.id)
        self.assertEqual(item.key, "user_name")
        self.assertEqual(item.value, "Gokul")
        self.assertEqual(item.category, "identity")

        # Fetch by key
        fetched = self.manager.get_by_key("user_name")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.value, "Gokul")

    def test_duplicate_superseding(self):
        """Test that updating an existing preference supersedes the older value."""
        self.manager.remember("preferred_drink", "Coffee", "preference", importance=3)
        self.manager.remember("preferred_drink", "Tea", "preference", importance=4)

        all_memories = self.manager.get_all(include_inactive=False)
        self.assertEqual(len(all_memories), 1)
        self.assertEqual(all_memories[0].value, "Tea")
        self.assertEqual(all_memories[0].importance, 4)

    def test_soft_delete_and_forget(self):
        """Test forgetting a specific memory key."""
        self.manager.remember("user_skill", "Python", "skill")
        self.assertTrue(self.manager.forget_by_key("user_skill"))
        self.assertIsNone(self.manager.get_by_key("user_skill"))

        stats = self.manager.get_stats()
        self.assertEqual(stats["active_memories"], 0)
        self.assertEqual(stats["total_memories"], 1)

    def test_clear_all_memories(self):
        """Test clearing all memories soft deletes everything."""
        self.manager.remember("fact_1", "Value 1")
        self.manager.remember("fact_2", "Value 2")
        cleared_count = self.manager.clear_all(hard_delete=False)
        self.assertEqual(cleared_count, 2)
        self.assertEqual(len(self.manager.get_all(include_inactive=False)), 0)

    def test_search_memories(self):
        """Test wildcard search across key and value fields."""
        self.manager.remember("project_name", "TONY AI Assistant", "project")
        self.manager.remember("user_role", "Lead Architect", "identity")

        results = self.manager.search("Assistant")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].key, "project_name")

        results2 = self.manager.search("lead")
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0].key, "user_role")


class TestMemoryExtractor(unittest.TestCase):
    """Test intent classification, entity extraction, and secret rejection."""

    def setUp(self):
        self.extractor = MemoryExtractor()

    def test_intent_classification(self):
        """Verify intent detection for remember, forget, recall, clear, and normal."""
        self.assertEqual(self.extractor.classify_intent("Remember that my name is Gokul"), "REMEMBER")
        self.assertEqual(self.extractor.classify_intent("Forget my project name"), "FORGET")
        self.assertEqual(self.extractor.classify_intent("What do you remember about me?"), "RECALL")
        self.assertEqual(self.extractor.classify_intent("Forget everything you know about me"), "CLEAR")
        self.assertEqual(self.extractor.classify_intent("What is the speed of light?"), "NORMAL")

    def test_entity_extraction(self):
        """Test extraction of key-value fact pairs from user utterances."""
        facts = self.extractor.extract_facts("My name is Gokul")
        self.assertTrue(any(f["key"] == "user_name" and f["value"] == "Gokul" for f in facts))

        facts2 = self.extractor.extract_facts("I am building an AI called TONY")
        self.assertTrue(any("project" in f["key"] and "TONY" in f["value"] for f in facts2))

        facts3 = self.extractor.extract_facts("I prefer dark mode in my IDE")
        self.assertTrue(any("preference" in f["category"] for f in facts3))

    def test_sensitive_secret_rejection(self):
        """Verify security filter blocks passwords, API keys, and sensitive tokens."""
        self.assertTrue(self.extractor.is_sensitive_secret("My password is supersecret123!"))
        self.assertTrue(self.extractor.is_sensitive_secret("Here is my api_key: sk-1234567890abcdef"))
        self.assertTrue(self.extractor.is_sensitive_secret("My private ssh key starts with -----BEGIN RSA"))
        self.assertTrue(self.extractor.is_sensitive_secret("Remember my authorization bearer token eyJhbGci..."))

        # Non-secrets should pass safely
        self.assertFalse(self.extractor.is_sensitive_secret("My name is Gokul"))
        self.assertFalse(self.extractor.is_sensitive_secret("I like coding in Python"))


class TestMemoryRetriever(unittest.TestCase):
    """Test keyword retrieval and prompt context block building."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "retriever_test.db")
        self.db = MemoryDatabase(db_path=self.db_path)
        self.manager = MemoryManager(database=self.db)
        self.retriever = KeywordMemoryRetriever(self.manager)

        # Pre-populate memories
        self.manager.remember("user_name", "Gokul", "identity", importance=5)
        self.manager.remember("preferred_language", "Python", "preference", importance=4)
        self.manager.remember("current_project", "TONY AI Assistant", "project", importance=4)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_retrieve_relevant_name(self):
        """Querying 'What is my name?' retrieves the user_name memory."""
        results = self.retriever.retrieve_relevant("What is my name?", limit=3)
        self.assertTrue(len(results) > 0)
        top_match = results[0]
        self.assertEqual(top_match.key, "user_name")
        self.assertEqual(top_match.value, "Gokul")

    def test_retrieve_relevant_language(self):
        """Querying 'Which programming language do I prefer?' retrieves the language memory."""
        results = self.retriever.retrieve_relevant("Which programming language do I prefer?", limit=3)
        self.assertTrue(len(results) > 0)
        keys = [r.key for r in results]
        self.assertIn("preferred_language", keys)

    def test_build_memory_context(self):
        """Test formatting of the memory context block injected into AI prompt."""
        context_block = self.retriever.build_memory_context("What is my name and project?")
        self.assertIn("RELEVANT USER MEMORY:", context_block)
        self.assertIn("Gokul", context_block)
        self.assertIn("TONY AI Assistant", context_block)


class TestMemoryApiAndChatIntegration(unittest.TestCase):
    """Test REST API endpoints and end-to-end chat integration."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "api_integration.db")
        self.temp_path = Path(self.temp_dir)

        class TestConfig(Config):
            AI_PROVIDER = "mock"
            AI_MODEL = "tony-test"
            STT_PROVIDER = "mock"
            TTS_PROVIDER = "mock"
            BASE_DIR = self.temp_path
            DATA_DIR = self.temp_path / "data"
            CONVERSATIONS_DIR = self.temp_path / "data" / "conversations"
            AUDIO_DIR = self.temp_path / "data" / "audio"
            LOGS_DIR = self.temp_path / "logs"
            MEMORY_ENABLED = True
            MEMORY_DATABASE = self.db_path
            TESTING = True

        self.config_class = TestConfig
        self.app = create_app(config_class=TestConfig)
        self.client = self.app.test_client()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_memory_rest_api_crud(self):
        """Test full REST lifecycle via /api/memory."""
        # 1. Create memory
        res = self.client.post("/api/memory", json={
            "key": "framework",
            "value": "Flask",
            "category": "skill",
            "importance": 4
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        mem_id = data["memory"]["id"]

        # 2. Get single memory
        res_get = self.client.get(f"/api/memory/{mem_id}")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.get_json()["memory"]["value"], "Flask")

        # 3. Update memory
        res_put = self.client.put(f"/api/memory/{mem_id}", json={
            "value": "Flask and FastAPI",
            "importance": 5
        })
        self.assertEqual(res_put.status_code, 200)
        self.assertEqual(res_put.get_json()["memory"]["value"], "Flask and FastAPI")

        # 4. Search memory
        res_search = self.client.post("/api/memory/search", json={"query": "FastAPI"})
        self.assertEqual(res_search.status_code, 200)
        self.assertEqual(len(res_search.get_json()["results"]), 1)

        # 5. Delete memory
        res_del = self.client.delete(f"/api/memory/{mem_id}")
        self.assertEqual(res_del.status_code, 200)

        # 6. Verify deleted from active list
        res_list = self.client.get("/api/memory")
        self.assertEqual(len(res_list.get_json()["memories"]), 0)

    def test_memory_stats_endpoint(self):
        """Verify /api/memory/stats returns telemetry counts."""
        self.client.post("/api/memory", json={"key": "test_k", "value": "test_v"})
        res = self.client.get("/api/memory/stats")
        self.assertEqual(res.status_code, 200)
        stats = res.get_json()["stats"]
        self.assertGreaterEqual(stats["active_memories"], 1)

    def test_e2e_chat_remember_and_recall(self):
        """End-to-end: tell TONY a name, then ask for it, verifying memory retrieval."""
        # Step 1: Tell TONY user's name
        res1 = self.client.post("/api/chat", json={"message": "Remember that my name is Gokul."})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertIn("Gokul", data1["response"])

        # Verify it was stored in memory
        res_mem = self.client.get("/api/memory")
        memories = res_mem.get_json()["memories"]
        self.assertTrue(any(m["memory_value"] == "Gokul" for m in memories))

        # Step 2: Ask TONY for the name
        res2 = self.client.post("/api/chat", json={"message": "What is my name?"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertIn("Gokul", data2["response"])

    def test_e2e_secret_rejection(self):
        """Verify chat endpoint rejects storing sensitive passwords/keys."""
        res = self.client.post("/api/chat", json={
            "message": "Remember that my password is superSecretPassword123"
        })
        self.assertEqual(res.status_code, 200)
        reply = res.get_json()["response"]
        self.assertIn("cannot store sensitive credentials", reply.lower())

        # Verify nothing was added to SQLite database
        res_mem = self.client.get("/api/memory")
        memories = res_mem.get_json()["memories"]
        self.assertFalse(any("superSecretPassword123" in m["memory_value"] for m in memories))

    def test_persistence_across_app_restart(self):
        """Verify memories persist in SQLite when the application is re-created."""
        # 1. Store memory in first app instance
        self.client.post("/api/memory", json={
            "key": "user_city",
            "value": "San Francisco",
            "category": "identity"
        })

        # 2. Simulate application restart with a fresh create_app pointing to same DB
        new_app = create_app(config_class=self.config_class)
        new_client = new_app.test_client()

        # 3. Verify memory is preserved and queryable
        res = new_client.get("/api/memory")
        self.assertEqual(res.status_code, 200)
        memories = res.get_json()["memories"]
        self.assertTrue(any(m["memory_key"] == "user_city" and m["memory_value"] == "San Francisco" for m in memories))


if __name__ == "__main__":
    unittest.main()
