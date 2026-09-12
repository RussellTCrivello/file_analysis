"""Locks in the DatabaseHub call-site investigation as executable evidence.

These tests encode the conclusions of PHASE2_DBHUB_INVESTIGATION.md so that a
future change which makes the dead code reachable - or which deletes the
disabled block without noticing what it guarded - fails loudly instead of
silently changing behaviour.

They analyse the module with ``ast`` rather than reading it, because the whole
point is that some occurrences of ``db_hub.<x>_operations`` are text inside a
string literal or a comment, not code. A grep cannot tell the difference; this
can.
"""

import ast
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PIPELINE = PROJECT_ROOT / "pipeline" / "storage_pipeline.py"
DB_SERVICE = PROJECT_ROOT / "database" / "services" / "contents_db_service.py"

OPERATION_ATTRIBUTES = (
    "word_operations",
    "path_operations",
    "title_operations",
    "punctuation_operations",
    "content_operations",
    "hash_operations",
)


def parse(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def string_literal_lines(tree):
    """Every line occupied by a multi-line string constant (i.e. not code)."""
    lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "\n" in node.value:
                lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def is_comment(source_lines, lineno):
    return source_lines[lineno - 1].lstrip().startswith("#")


def operation_sites(path):
    """Yield (lineno, attribute, reachable_syntax) for each occurrence."""
    source = path.read_text(encoding="utf-8")
    tree = parse(path)
    in_string = string_literal_lines(tree)
    source_lines = source.splitlines()
    sites = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in OPERATION_ATTRIBUTES
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "db_hub"
        ):
            sites.append((node.lineno, node.attr, node.lineno not in in_string))
    # grep-style sweep to also catch occurrences inside strings and comments,
    # which the AST walk deliberately does not return.
    textual = {
        i
        for i, line in enumerate(source_lines, 1)
        if any(f"db_hub.{attr}" in line for attr in OPERATION_ATTRIBUTES)
    }
    ast_lines = {lineno for lineno, _, _ in sites}
    return sites, textual - ast_lines, in_string, source_lines


class TestOperationsAttributesDoNotExist:
    """The premise. Asserted rather than assumed."""

    @pytest.mark.parametrize("attribute", OPERATION_ATTRIBUTES)
    def test_database_hub_lacks(self, attribute):
        from database import DatabaseHub

        assert not hasattr(DatabaseHub, attribute), attribute

    def test_no_dynamic_attribute_access_to_hide_it(self):
        from database import DatabaseHub

        assert not hasattr(DatabaseHub, "__getattr__")


class TestDisabledBlock:
    def test_a_large_string_literal_disables_the_old_path(self):
        tree = parse(PIPELINE)
        blocks = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and len(node.value) > 5000
        ]
        assert blocks, "the disabled block is no longer a string literal"
        block = blocks[0]
        assert block.lineno < 1100 and (block.end_lineno or 0) > 1300

    def test_every_path_operations_site_is_inside_that_string(self):
        sites, _textual, in_string, _lines = operation_sites(PIPELINE)
        path_sites = [ln for ln, attr, _ in sites if attr == "path_operations"]
        # AST only yields code sites; path_operations has none.
        assert path_sites == [], (
            f"path_operations became live code at {path_sites}"
        )
        source = PIPELINE.read_text(encoding="utf-8").splitlines()
        textual = [
            i for i, line in enumerate(source, 1)
            if "db_hub.path_operations" in line and not line.lstrip().startswith("#")
        ]
        assert textual, "expected the historical occurrences to still be present"
        for lineno in textual:
            assert lineno in in_string, f"L{lineno} is now executable code"

    def test_execution_cannot_reach_the_disabled_block(self):
        """The guard that makes the block inert must still precede it."""
        source = PIPELINE.read_text(encoding="utf-8")
        guard = "return None"
        marker = "# OLD CODE BELOW IS DISABLED - DO NOT UNCOMMENT"
        assert marker in source
        assert source.index(guard) < source.index(marker), (
            "the return that prevents execution of the disabled block now "
            "comes after it"
        )


class TestStoreContentPipelineIsUnreachable:
    def test_method_exists_but_has_no_live_caller(self):
        tree = parse(PIPELINE)
        in_string = string_literal_lines(tree)
        source_lines = PIPELINE.read_text(encoding="utf-8").splitlines()

        definitions = [
            (n.lineno, n.end_lineno or n.lineno)
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_store_content_pipeline"
        ]
        assert definitions, "method was removed; update this test"
        body = set()
        for start, end in definitions:
            body.update(range(start, end + 1))

        callers = [
            i
            for i, line in enumerate(source_lines, 1)
            if "_store_content_pipeline" in line
            and i not in body  # the method's own log message names itself
            and not line.lstrip().startswith("#")
        ]
        live_callers = [i for i in callers if i not in in_string]
        assert live_callers == [], (
            f"_store_content_pipeline gained a live caller at {live_callers}; it "
            "contains calls to DatabaseHub attributes that do not exist and will "
            "raise AttributeError"
        )

    def test_all_remaining_live_sites_live_in_that_method(self):
        tree = parse(PIPELINE)
        sites, _textual, _in_string, _lines = operation_sites(PIPELINE)
        live = [(ln, attr) for ln, attr, ok in sites if ok]
        assert live, "expected the unreachable method's sites to still be present"

        funcs = [
            (n.lineno, n.end_lineno or 0, n.name)
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        for lineno, _attr in live:
            enclosing = [f for f in funcs if f[0] <= lineno <= f[1]]
            enclosing.sort(key=lambda f: f[0])
            assert enclosing, f"L{lineno} is at module level"
            assert enclosing[-1][2] == "_store_content_pipeline", (
                f"L{lineno} uses a missing DatabaseHub attribute inside "
                f"{enclosing[-1][2]}(), which was not part of the investigated "
                "unreachable method"
            )


class TestPunctuationGap:
    """The one genuine gap: formatting metadata is implemented but never wired."""

    def test_create_content_from_symbols_has_no_callers(self):
        source = DB_SERVICE.read_text(encoding="utf-8")
        occurrences = [
            i
            for i, line in enumerate(source.splitlines(), 1)
            if "create_content_from_symbols" in line
        ]
        # Only the definition. If this fails, the method was wired in - which
        # is the desired end state, and this test should then assert that the
        # punctuation table is populated.
        assert len(occurrences) == 1, (
            f"create_content_from_symbols is now referenced at {occurrences}; "
            "verify the punctuation table is populated and update this test"
        )

    def test_punctuation_table_is_empty_after_a_real_ingest(self, pg_db):
        """Runtime proof of the gap, not just a static one."""
        import datetime

        import psycopg2

        conn = psycopg2.connect(
            host=pg_db["host"], port=pg_db["port"], user=pg_db["user"],
            password=pg_db["password"], dbname=pg_db["database"],
        )
        today = datetime.date.today()
        tag = f"_punct_{today}"
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO sides (name, importance, date_creation)"
                    " VALUES (%s, 0.5, %s) ON CONFLICT (name)"
                    " DO UPDATE SET name = EXCLUDED.name",
                    (f"{tag}_side", today),
                )
                cur.execute(
                    "INSERT INTO sources (name, job, importance, country,"
                    " date_creation) VALUES (%s, 't', 0.5, 't', %s)"
                    " ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name",
                    (f"{tag}_src", today),
                )
            conn.commit()

            pymupdf = pytest.importorskip("pymupdf")
            import tempfile

            doc = pymupdf.open()
            doc.new_page().insert_text(
                (72, 72),
                "Quarterly reconciliation, dated 14 March; a variance of 4.7 "
                "percent was noted by the auditor.",
                fontsize=11,
            )
            tmp = Path(tempfile.mkdtemp())
            path = tmp / "punct.pdf"
            path.write_bytes(doc.tobytes())
            doc.close()

            from pipeline.integrated_reader import IntegratedFileReader

            IntegratedFileReader(
                max_workers=1, enable_storage=True,
                storage_source=f"{tag}_src", storage_side=f"{tag}_side",
            ).process_folder(str(tmp))

            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM words")
                assert cur.fetchone()[0] > 0, "sanity: words were stored"
                cur.execute("SELECT COUNT(*) FROM punctuation")
                assert cur.fetchone()[0] == 0, (
                    "punctuation is now populated - the gap is closed; update "
                    "this test to assert the correct behaviour"
                )
        finally:
            conn.close()
