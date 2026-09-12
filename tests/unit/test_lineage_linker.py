"""Unit tests for StoragePipeline._link_extracted_children (task 2, PARENT-01).

Uses a stub repository so the recursion and the hierarchy string construction
are tested without a database.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.storage_pipeline import StoragePipeline  # noqa: E402


class StubRepo:
    def __init__(self, names=None, fail_ids=()):
        self.names = names or {}
        self.fail_ids = set(fail_ids)
        self.updates = []

    def get_lineage(self, path_id):
        return (self.names.get(path_id, f"file{path_id}"), self.names.get(path_id))

    def update_lineage(self, path_id, parent_path_id, hierarchy_path):
        if path_id in self.fail_ids:
            raise RuntimeError("db exploded")
        self.updates.append((path_id, parent_path_id, hierarchy_path))


def pipeline_with(repo):
    pipe = StoragePipeline.__new__(StoragePipeline)
    pipe.db_service = type("S", (), {"paths_repo": repo})() if repo is not None else None
    return pipe


class TestNoOpCases:
    @pytest.mark.parametrize("content", [None, {}, {"extracted_files": "nope"},
                                         {"extracted_files": []}])
    def test_no_children_writes_nothing(self, content):
        repo = StubRepo()
        assert pipeline_with(repo)._link_extracted_children(content, 1) == 0
        assert repo.updates == []

    def test_no_parent_id_writes_nothing(self):
        repo = StubRepo()
        content = {"extracted_files": [{"database_path_id": 5}]}
        assert pipeline_with(repo)._link_extracted_children(content, None) == 0
        assert repo.updates == []

    def test_no_db_service_does_not_raise(self):
        content = {"extracted_files": [{"database_path_id": 5}]}
        assert pipeline_with(None)._link_extracted_children(content, 1) == 0

    def test_child_without_a_path_id_is_skipped(self):
        repo = StubRepo()
        content = {"extracted_files": [{"Metadata": {"name": "orphan.pdf"}}]}
        assert pipeline_with(repo)._link_extracted_children(content, 1) == 0
        assert repo.updates == []


class TestLinking:
    def test_single_child_gets_parent_and_hierarchy(self):
        repo = StubRepo(names={1: "outer.zip"})
        content = {"extracted_files": [
            {"database_path_id": 2, "Metadata": {"name": "child.pdf"}},
        ]}
        pipe = pipeline_with(repo)
        assert pipe._link_extracted_children(content, 1) == 1
        assert repo.updates == [(2, 1, "outer.zip::child.pdf")]

    def test_hierarchy_falls_back_to_file_name(self):
        """A top-level container has no stored hierarchy yet."""
        repo = StubRepo(names={1: "outer.zip"})
        repo.names = {}  # get_lineage returns ("file1", None)
        content = {"extracted_files": [
            {"database_path_id": 2, "Metadata": {"name": "child.pdf"}},
        ]}
        pipeline_with(repo)._link_extracted_children(content, 1)
        assert repo.updates[0][2] == "file1::child.pdf"

    def test_name_is_derived_from_path_when_absent(self):
        repo = StubRepo(names={1: "a.zip"})
        content = {"extracted_files": [
            {"database_path_id": 2, "Metadata": {"path": "/tmp/x/deep.pdf"}},
        ]}
        pipeline_with(repo)._link_extracted_children(content, 1)
        assert repo.updates[0][2] == "a.zip::deep.pdf"

    def test_recursion_builds_the_full_chain(self):
        repo = StubRepo(names={1: "outer.zip"})
        content = {"extracted_files": [{
            "database_path_id": 2,
            "Metadata": {"name": "inner.zip"},
            "Content": {"extracted_files": [{
                "database_path_id": 3,
                "Metadata": {"name": "scan.png"},
            }]},
        }]}
        pipe = pipeline_with(repo)
        assert pipe._link_extracted_children(content, 1) == 2
        assert repo.updates == [
            (2, 1, "outer.zip::inner.zip"),
            (3, 2, "outer.zip::inner.zip::scan.png"),
        ]

    def test_separator_is_a_named_constant(self):
        assert StoragePipeline.HIERARCHY_SEPARATOR == "::"


class TestFailureHandling:
    def test_one_bad_child_does_not_abort_the_rest(self):
        """A failed link must not fail the ingest - the child is still indexed."""
        repo = StubRepo(names={1: "a.zip"}, fail_ids={2})
        content = {"extracted_files": [
            {"database_path_id": 2, "Metadata": {"name": "bad.pdf"}},
            {"database_path_id": 3, "Metadata": {"name": "good.pdf"}},
        ]}
        pipe = pipeline_with(repo)
        assert pipe._link_extracted_children(content, 1) == 1
        assert repo.updates == [(3, 1, "a.zip::good.pdf")]

    def test_get_lineage_failure_does_not_raise(self):
        class Broken(StubRepo):
            def get_lineage(self, path_id):
                raise RuntimeError("no connection")

        repo = Broken()
        content = {"extracted_files": [
            {"database_path_id": 2, "Metadata": {"name": "c.pdf"}},
        ]}
        pipeline_with(repo)._link_extracted_children(content, 1)
        assert repo.updates == [(2, 1, "c.pdf")]
