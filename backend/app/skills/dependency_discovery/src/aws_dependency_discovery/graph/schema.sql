-- SQLite schema for AWS dependency discovery

CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    event_time      TEXT NOT NULL,
    event_source    TEXT NOT NULL,
    event_name      TEXT NOT NULL,
    source_account_id TEXT NOT NULL,
    source_principal  TEXT NOT NULL,
    target_resource   TEXT NOT NULL,
    target_service    TEXT NOT NULL,
    target_account_id TEXT NOT NULL,
    region            TEXT NOT NULL,
    raw_json          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_source ON events(event_source, event_name);
CREATE INDEX IF NOT EXISTS idx_events_source_account ON events(source_account_id);
CREATE INDEX IF NOT EXISTS idx_events_target_service ON events(target_service);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(event_time);

CREATE TABLE IF NOT EXISTS nodes (
    node_id     TEXT PRIMARY KEY,   -- "account_id:service" composite key
    account_id  TEXT NOT NULL,
    service     TEXT NOT NULL,
    node_type   TEXT NOT NULL DEFAULT 'service',  -- 'service', 'account', 'principal'
    first_seen  TEXT,
    last_seen   TEXT,
    event_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_nodes_account ON nodes(account_id);
CREATE INDEX IF NOT EXISTS idx_nodes_service ON nodes(service);

CREATE TABLE IF NOT EXISTS edges (
    edge_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id  TEXT NOT NULL REFERENCES nodes(node_id),
    target_node_id  TEXT NOT NULL REFERENCES nodes(node_id),
    edge_type       TEXT NOT NULL,       -- 'sync_call', 'async', 'data_read', 'data_write', 'trust'
    event_name      TEXT NOT NULL,
    frequency       INTEGER DEFAULT 1,   -- number of times this edge was observed
    first_seen      TEXT,
    last_seen       TEXT,
    sample_resource TEXT,                -- example target resource ARN
    UNIQUE(source_node_id, target_node_id, edge_type, event_name)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);

-- VPC Flow Logs: aggregated network dependencies
CREATE TABLE IF NOT EXISTS network_deps (
    dep_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src_addr        TEXT NOT NULL,
    dst_addr        TEXT NOT NULL,
    dst_port        INTEGER NOT NULL,
    protocol        INTEGER NOT NULL,       -- 6=TCP, 17=UDP
    service_guess   TEXT NOT NULL,           -- best-effort from port mapping
    total_bytes     INTEGER DEFAULT 0,
    total_packets   INTEGER DEFAULT 0,
    connection_count INTEGER DEFAULT 1,
    account_id      TEXT NOT NULL DEFAULT '',
    vpc_id          TEXT NOT NULL DEFAULT '',
    first_seen      TEXT,
    last_seen       TEXT,
    UNIQUE(src_addr, dst_addr, dst_port, protocol)
);

CREATE INDEX IF NOT EXISTS idx_netdeps_src ON network_deps(src_addr);
CREATE INDEX IF NOT EXISTS idx_netdeps_dst ON network_deps(dst_addr);
CREATE INDEX IF NOT EXISTS idx_netdeps_port ON network_deps(dst_port);
CREATE INDEX IF NOT EXISTS idx_netdeps_service ON network_deps(service_guess);
