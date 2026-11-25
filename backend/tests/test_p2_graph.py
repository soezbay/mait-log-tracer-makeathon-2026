
import duckdb

from logtracer.analysis.graph import build_graph


def test_graph_generation():
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE error_groups (
            group_id INTEGER,
            host VARCHAR,
            component VARCHAR,
            level VARCHAR,
            count BIGINT,
            status VARCHAR
        )
    """)

    con.execute("""
        CREATE TABLE correlations (
            correlation_id INTEGER,
            group_a INTEGER,
            group_b INTEGER,
            kind VARCHAR,
            link_key VARCHAR,
            lag_s DOUBLE,
            confidence DOUBLE
        )
    """)

    con.execute("""
        INSERT INTO error_groups VALUES
        (101, 'cad', 'export', 'ERROR', 5, 'unknown'),
        (102, 'dispatcher', 'jobs', 'ERROR', 3, 'unknown'),
        (103, 'teamcenter', 'import', 'WARN', 2, 'unknown')
    """)

    con.execute("""
        INSERT INTO correlations VALUES
        (1, 101, 102, 'hard', 'job_id=JOB-2003', 12, 0.7),
        (2, 102, 103, 'hard', 'job_id=JOB-2003', 13, 0.7)
    """)

    graph = build_graph(con)

    assert len(graph["nodes"]) == 3
    assert len(graph["edges"]) == 2

    assert graph["edges"][0]["source"] == "101"
    assert graph["edges"][0]["target"] == "102"

    con.close()
