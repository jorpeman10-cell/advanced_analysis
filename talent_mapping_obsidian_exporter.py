"""Export Gllue talent and mapping data into an Obsidian-style Markdown vault.

The exporter is intentionally one-way: it reads Gllue data and writes local
Markdown files. It does not modify the database.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

import db_config_manager
from gllue_db_client import GllueDBClient


DEFAULT_OUTPUT = Path(__file__).parent / "talent_mapping_vault"
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def _limit_filename_bytes(text: str, max_bytes: int = 180) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip(" .")


def slug(value: Any, fallback: str = "untitled") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r'[<>:"/\\|?*]+', "-", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return _limit_filename_bytes(text) or fallback


def meaningful_text(value: Any) -> bool:
    text = str(value or "").strip()
    if len(text) < 2:
        return False
    if text.lower() in {"topic", "subtopic", "children", "root", "untitled", "mindmap"}:
        return False
    return bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", text))


def link(name: Any, folder: str | None = None) -> str:
    text = str(name or "").strip()
    if not meaningful_text(text):
        return ""
    target = f"{folder}/{text}" if folder else text
    return f"[[{target}]]"


def write_note(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def md_list(items: Iterable[str]) -> str:
    values = [item for item in items if item]
    return "\n".join(f"- {item}" for item in values) if values else "- 待补充"


def safe_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def table_columns(db: GllueDBClient, table: str) -> set[str]:
    try:
        desc = db.describe_table(table)
    except Exception:
        return set()
    if desc.empty:
        return set()
    field_col = "Field" if "Field" in desc.columns else desc.columns[0]
    return {str(v) for v in desc[field_col].dropna().tolist()}


def optional_col(
    columns: set[str],
    candidates: list[str],
    alias: str,
    table_alias: str = "cd",
    default_sql: str = "NULL",
) -> str:
    for col in candidates:
        if col in columns:
            return f"{table_alias}.{col} AS {alias}"
    return f"{default_sql} AS {alias}"


def load_candidate_activity(db: GllueDBClient, limit: int) -> pd.DataFrame:
    candidate_cols = table_columns(db, "candidate")
    optional_fields = [
        optional_col(candidate_cols, ["gender", "sex"], "gender"),
        optional_col(candidate_cols, ["birthDate", "birthday", "dateOfBirth"], "birth_date"),
        optional_col(candidate_cols, ["currentCompany", "company", "employer"], "current_company"),
        optional_col(candidate_cols, ["currentTitle", "title", "position"], "current_title"),
        optional_col(candidate_cols, ["school", "educationSchool", "university"], "school"),
        optional_col(candidate_cols, ["major", "profession"], "major"),
        optional_col(candidate_cols, ["location", "city", "currentLocation"], "location"),
    ]
    sql = f"""
        SELECT
            cd.id AS candidate_id,
            TRIM(CONCAT(IFNULL(cd.englishName, ''), ' ', IFNULL(cd.chineseName, ''))) AS candidate_name,
            {", ".join(optional_fields)},
            js.id AS jobsubmission_id,
            js.dateAdded AS submission_date,
            js.onboardDate AS onboard_date,
            cs.dateAdded AS resume_sent_date,
            ci.first_interview_date,
            os.offer_date,
            os.offer_revenue,
            i.total_invoice,
            i.total_collection,
            jo.id AS joborder_id,
            jo.jobTitle AS position_name,
            jo.function_normal,
            jo.jobStatus AS job_status,
            c.name AS client_name,
            TRIM(CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, ''))) AS consultant,
            t.name AS team
        FROM candidate cd
        LEFT JOIN jobsubmission js ON js.candidate_id = cd.id AND js.active = 1
        LEFT JOIN joborder jo ON js.joborder_id = jo.id
        LEFT JOIN client c ON jo.client_id = c.id
        LEFT JOIN (
            SELECT jobsubmission_id, MIN(dateAdded) AS dateAdded, MIN(user_id) AS user_id
            FROM cvsent
            WHERE active = 1
            GROUP BY jobsubmission_id
        ) cs ON cs.jobsubmission_id = js.id
        LEFT JOIN user u ON cs.user_id = u.id
        LEFT JOIN team t ON u.team_id = t.id
        LEFT JOIN (
            SELECT jobsubmission_id, MIN(date) AS first_interview_date
            FROM clientinterview
            WHERE active = 1
            GROUP BY jobsubmission_id
        ) ci ON ci.jobsubmission_id = js.id
        LEFT JOIN (
            SELECT jobsubmission_id, MIN(signDate) AS offer_date, SUM(COALESCE(revenue, 0)) AS offer_revenue
            FROM offersign
            WHERE active = 1
            GROUP BY jobsubmission_id
        ) os ON os.jobsubmission_id = js.id
        LEFT JOIN (
            SELECT jobsubmission_id,
                   SUM(COALESCE(invoiceAmount, 0)) AS total_invoice,
                   SUM(COALESCE(paymentReceived, 0)) AS total_collection
            FROM invoice
            WHERE active = 1
            GROUP BY jobsubmission_id
        ) i ON i.jobsubmission_id = js.id
        WHERE cd.id IS NOT NULL
        ORDER BY COALESCE(js.dateAdded, cd.id) DESC
        LIMIT {int(limit)}
    """
    return db.query(sql)


def load_mapping_rows(db: GllueDBClient, limit: int) -> pd.DataFrame:
    sql = f"""
        SELECT m.content,
               co.id AS org_id,
               co.name AS org_name,
               co.client_name,
               co.dateAdded,
               co.lastUpdateDate,
               TRIM(CONCAT(IFNULL(u.englishName, ''), ' ', IFNULL(u.chineseName, ''))) AS creator_name
        FROM companyorganizationmapping m
        JOIN companyorganization co ON m.organization_id = co.id
        LEFT JOIN user u ON co.addedBy_id = u.id
        WHERE m.is_current = 1
          AND m.is_deleted = 0
          AND co.is_deleted = 0
        ORDER BY co.lastUpdateDate DESC
        LIMIT {int(limit)}
    """
    return db.query(sql)


def iter_mapping_nodes(content: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(content or "{}")
    except Exception:
        return []
    nodes: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], depth: int, parent: str = "") -> None:
        text = str(node.get("text") or "").strip()
        note = str(node.get("note") or "").strip()
        if text or note:
            nodes.append({"text": text, "note": note, "depth": depth, "parent": parent})
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, depth + 1, text or parent)

    for root in data.get("roots") or []:
        if isinstance(root, dict):
            walk(root, 0)
    return nodes


def stage_signal(row: pd.Series) -> list[str]:
    signals = []
    if str(row.get("resume_sent_date") or ""):
        signals.append(link("已推荐", "signals"))
    if str(row.get("first_interview_date") or ""):
        signals.append(link("进入面试", "signals"))
    if str(row.get("offer_date") or ""):
        signals.append(link("Offer 成功", "signals"))
    if float(row.get("total_collection") or 0) > 0:
        signals.append(link("产生回款", "signals"))
    return signals


def render_candidate(name: str, rows: pd.DataFrame) -> str:
    first = rows.iloc[0]
    basics = [
        f"Current Company: {link(first.get('current_company'), 'companies')}",
        f"Current Title: {link(first.get('current_title'), 'roles')}",
        f"School: {link(first.get('school'), 'schools')}",
        f"Major: {link(first.get('major'), 'majors')}",
        f"Location: {link(first.get('location'), 'regions')}",
    ]
    timeline = []
    for _, row in rows.iterrows():
        if not row.get("jobsubmission_id"):
            continue
        timeline.append(
            "\n".join(
                [
                    f"### {safe_date(row.get('submission_date')) or '日期待确认'} | {link(row.get('client_name'), 'companies')}",
                    "",
                    md_list(
                        [
                            f"Position: {link(row.get('position_name'), 'roles')}",
                            f"Function: {link(row.get('function_normal'), 'functions')}",
                            f"Consultant: {link(row.get('consultant'), 'consultants')}",
                            f"Team: {link(row.get('team'), 'teams')}",
                            f"Resume Sent: {safe_date(row.get('resume_sent_date'))}",
                            f"First Interview: {safe_date(row.get('first_interview_date'))}",
                            f"Offer Date: {safe_date(row.get('offer_date'))}",
                            f"Onboard Date: {safe_date(row.get('onboard_date'))}",
                            f"Offer Revenue: {row.get('offer_revenue') or 0}",
                            f"Collection: {row.get('total_collection') or 0}",
                        ]
                    ),
                ]
            )
        )
    signals = sorted({s for _, row in rows.iterrows() for s in stage_signal(row)})
    sources = sorted({f"Gllue candidate_id={v}" for v in rows["candidate_id"].dropna().unique()})
    return "\n\n".join(
        [
            f"# {name}",
            "## Basic Info",
            md_list(basics),
            "## Performance Signals",
            md_list(signals),
            "## Career / Search Timeline",
            "\n\n".join(timeline) if timeline else "- 待补充",
            "## Assessment Notes",
            "- 事实来自谷露数据库；能力判断需要结合访谈、业绩证明和客户反馈继续编译。",
            "## Sources",
            md_list(sources),
        ]
    )


def render_mapping(row: pd.Series, nodes: list[dict[str, Any]]) -> str:
    node_lines = []
    people_links = []
    for node in nodes:
        text = node["text"]
        if not text:
            continue
        indent = "  " * int(node["depth"])
        node_lines.append(f"{indent}- {link(text, 'mapping-nodes')}")
        if len(text) <= 40 and meaningful_text(text):
            people_links.append(link(text, "people"))
    return "\n\n".join(
        [
            f"# {row.get('org_name') or row.get('client_name') or 'Mapping'}",
            "## Company / Organization",
            md_list(
                [
                    f"Client: {link(row.get('client_name'), 'companies')}",
                    f"Creator: {link(row.get('creator_name'), 'consultants')}",
                    f"Created: {safe_date(row.get('dateAdded'))}",
                    f"Updated: {safe_date(row.get('lastUpdateDate'))}",
                ]
            ),
            "## Mapping Tree",
            "\n".join(node_lines) if node_lines else "- 待补充",
            "## Potential People Links",
            md_list(sorted(set(people_links))[:80]),
            "## Sources",
            f"- Gllue companyorganization id={row.get('org_id')}",
        ]
    )


def render_entity_page(title: str, backlinks: list[str], kind: str) -> str:
    return "\n\n".join(
        [
            f"# {title}",
            f"## Type\n- {kind}",
            "## Linked Records",
            md_list(sorted(set(backlinks))),
            "## Notes",
            "- 待结合访谈、简历、业绩数据继续编译。",
        ]
    )


def export_vault(output: Path, candidate_limit: int, mapping_limit: int) -> None:
    db = GllueDBClient(db_config_manager.get_gllue_db_config())
    entity_links: dict[tuple[str, str], list[str]] = defaultdict(list)
    try:
        candidates = load_candidate_activity(db, candidate_limit)
        mappings = load_mapping_rows(db, mapping_limit)
    finally:
        db.close()

    output.mkdir(parents=True, exist_ok=True)

    if not candidates.empty:
        candidates["candidate_name"] = candidates["candidate_name"].fillna("").replace("", "Unnamed Candidate")
        for name, group in candidates.groupby("candidate_name", dropna=False):
            page_name = slug(name, f"candidate-{group.iloc[0].get('candidate_id')}")
            rel = f"people/{page_name}"
            write_note(output / f"{rel}.md", render_candidate(page_name, group))
            for _, row in group.iterrows():
                for folder, col in [
                    ("companies", "client_name"),
                    ("companies", "current_company"),
                    ("schools", "school"),
                    ("majors", "major"),
                    ("regions", "location"),
                    ("roles", "position_name"),
                    ("roles", "current_title"),
                    ("functions", "function_normal"),
                    ("consultants", "consultant"),
                    ("teams", "team"),
                ]:
                    value = str(row.get(col) or "").strip()
                    if meaningful_text(value):
                        entity_links[(folder, value)].append(link(page_name, "people"))

    if not mappings.empty:
        for _, row in mappings.iterrows():
            nodes = iter_mapping_nodes(row.get("content"))
            page_name = slug(row.get("org_name") or row.get("client_name"), f"mapping-{row.get('org_id')}")
            write_note(output / f"mappings/{page_name}.md", render_mapping(row, nodes))
            if row.get("client_name"):
                client_name = str(row.get("client_name") or "").strip()
                if meaningful_text(client_name):
                    entity_links[("companies", client_name)].append(link(page_name, "mappings"))
            for node in nodes:
                text = str(node.get("text") or "").strip()
                if meaningful_text(text):
                    entity_links[("mapping-nodes", text)].append(link(page_name, "mappings"))

    for (folder, name), backlinks in entity_links.items():
        write_note(output / folder / f"{slug(name)}.md", render_entity_page(name, backlinks, folder))

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    index = "\n\n".join(
        [
            "# Talent Mapping Wiki",
            f"Generated: {now}",
            "## Main Areas",
            md_list(
                [
                    "[[people]]",
                    "[[companies]]",
                    "[[mappings]]",
                    "[[roles]]",
                    "[[signals]]",
                    "[[consultants]]",
                ]
            ),
            "## Workflow",
            "- 原始事实来自 Gllue；判断性内容应进入候选人页面的 Assessment Notes。",
            "- 用 Obsidian Backlinks 查看共同公司、共同岗位、共同 Mapping 节点和共同业绩信号。",
        ]
    )
    write_note(output / "index.md", index)
    write_note(output / "log.md", f"# Export Log\n\n## {now}\n\n- Exported {len(candidates)} candidate activity rows.\n- Exported {len(mappings)} organization mappings.")


def _note_id(path: Path, vault: Path) -> str:
    rel = path.relative_to(vault).with_suffix("")
    return rel.as_posix()


def _infer_group(node_id: str) -> str:
    return node_id.split("/", 1)[0] if "/" in node_id else "index"


def _resolve_link_target(raw_target: str, note_ids: set[str]) -> str:
    target = raw_target.strip().replace("\\", "/")
    if target in note_ids:
        return target
    if target.endswith(".md") and target[:-3] in note_ids:
        return target[:-3]
    basename_matches = [node_id for node_id in note_ids if node_id.rsplit("/", 1)[-1] == target]
    if basename_matches:
        return basename_matches[0]
    return target


def build_graph_data(vault: Path, max_nodes: int = 1200, max_edges: int = 4000) -> dict[str, Any]:
    """Parse Obsidian-style Markdown links into graph nodes and edges."""
    vault = Path(vault)
    files = sorted(vault.rglob("*.md"))
    note_ids = {_note_id(path, vault) for path in files}
    links_by_source: dict[str, set[str]] = defaultdict(set)
    inbound_count: dict[str, int] = defaultdict(int)
    outbound_count: dict[str, int] = defaultdict(int)

    for path in files:
        source = _note_id(path, vault)
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for match in WIKILINK_RE.finditer(content):
            target = _resolve_link_target(match.group(1), note_ids)
            if not meaningful_text(target):
                continue
            links_by_source[source].add(target)
            inbound_count[target] += 1
            outbound_count[source] += 1

    all_nodes = set(note_ids)
    for targets in links_by_source.values():
        all_nodes.update(targets)

    ranked_nodes = sorted(
        all_nodes,
        key=lambda node: (inbound_count.get(node, 0) + outbound_count.get(node, 0), node),
        reverse=True,
    )[: max(1, int(max_nodes))]
    kept = set(ranked_nodes)

    nodes = [
        {
            "id": node,
            "label": node.rsplit("/", 1)[-1],
            "group": _infer_group(node),
            "degree": inbound_count.get(node, 0) + outbound_count.get(node, 0),
        }
        for node in ranked_nodes
    ]

    edges = []
    for source, targets in links_by_source.items():
        if source not in kept:
            continue
        for target in sorted(targets):
            if target not in kept:
                continue
            edges.append({"from": source, "to": target})
            if len(edges) >= max_edges:
                break
        if len(edges) >= max_edges:
            break

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "vault": str(vault.resolve()),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source_file_count": len(files),
        },
    }


def export_graph_html(
    vault: Path,
    output_html: Path | None = None,
    max_nodes: int = 1200,
    max_edges: int = 4000,
) -> dict[str, Any]:
    """Create a self-contained Talent Mapping Graph View HTML file."""
    vault = Path(vault)
    output_html = output_html or (vault / "talent_mapping_graph.html")
    graph = build_graph_data(vault, max_nodes=max_nodes, max_edges=max_edges)
    graph_json = json.dumps(graph, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Talent Mapping Graph View</title>
  <script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/dist/vis-network.min.js"></script>
  <style>
    html, body {{ margin: 0; height: 100%; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f7f7f4; color: #222; }}
    #bar {{ height: 56px; display: flex; align-items: center; gap: 12px; padding: 0 16px; border-bottom: 1px solid #ddd; background: #fff; box-sizing: border-box; }}
    #graph {{ height: calc(100% - 56px); }}
    .title {{ font-weight: 700; }}
    .meta {{ color: #666; font-size: 13px; }}
    input {{ width: min(420px, 36vw); height: 32px; border: 1px solid #ccc; border-radius: 4px; padding: 0 10px; }}
    button {{ height: 32px; border: 1px solid #bbb; background: #fff; border-radius: 4px; cursor: pointer; }}
  </style>
</head>
<body>
  <div id="bar">
    <div class="title">Talent Mapping Graph View</div>
    <div class="meta" id="meta"></div>
    <input id="search" placeholder="搜索候选人、公司、岗位、区域..." />
    <button id="fit">Fit</button>
  </div>
  <div id="graph"></div>
  <script>
    const graph = {graph_json};
    const colors = {{
      "people": "#4C78A8", "companies": "#F58518", "roles": "#54A24B",
      "mapping-nodes": "#B279A2", "schools": "#72B7B2", "regions": "#E45756",
      "signals": "#FF9DA6", "consultants": "#9D755D", "teams": "#BAB0AC",
      "index": "#666666"
    }};
    const nodes = new vis.DataSet(graph.nodes.map(n => ({{
      id: n.id, label: n.label, group: n.group,
      value: Math.max(8, Math.min(40, 8 + n.degree * 2)),
      title: `${{n.id}}<br/>degree: ${{n.degree}}`,
      color: colors[n.group] || "#8C8C8C"
    }})));
    const edges = new vis.DataSet(graph.edges.map((e, i) => ({{ id: i, from: e.from, to: e.to, color: {{ color: "#c7c7c7" }} }})));
    const container = document.getElementById("graph");
    const network = new vis.Network(container, {{ nodes, edges }}, {{
      nodes: {{ shape: "dot", font: {{ size: 14, face: "Arial" }} }},
      edges: {{ width: 0.6, smooth: {{ type: "continuous" }} }},
      physics: {{
        solver: "forceAtlas2Based",
        forceAtlas2Based: {{ gravitationalConstant: -55, centralGravity: 0.015, springLength: 120, springConstant: 0.08 }},
        stabilization: {{ iterations: 180 }}
      }},
      interaction: {{ hover: true, tooltipDelay: 80, navigationButtons: true }}
    }});
    document.getElementById("meta").textContent = `${{graph.stats.node_count}} nodes / ${{graph.stats.edge_count}} edges`;
    document.getElementById("fit").onclick = () => network.fit({{ animation: true }});
    document.getElementById("search").addEventListener("keydown", event => {{
      if (event.key !== "Enter") return;
      const q = event.target.value.trim().toLowerCase();
      if (!q) return;
      const found = graph.nodes.find(n => n.id.toLowerCase().includes(q) || n.label.toLowerCase().includes(q));
      if (found) {{
        network.selectNodes([found.id]);
        network.focus(found.id, {{ scale: 1.2, animation: true }});
      }}
    }});
  </script>
</body>
</html>
"""
    write_note(output_html, html)
    return {
        "status": "success",
        "graph_html_path": str(output_html.resolve()),
        "stats": graph["stats"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Gllue talent mapping data to an Obsidian vault.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output vault directory.")
    parser.add_argument("--candidate-limit", type=int, default=300, help="Maximum candidate activity rows to export.")
    parser.add_argument("--mapping-limit", type=int, default=80, help="Maximum organization mappings to export.")
    parser.add_argument("--graph-html", action="store_true", help="Also export a graph view HTML file.")
    args = parser.parse_args()
    output = Path(args.output)
    export_vault(output, args.candidate_limit, args.mapping_limit)
    print(f"Exported Talent Mapping Wiki to: {output.resolve()}")
    if args.graph_html:
        print(export_graph_html(output))


if __name__ == "__main__":
    main()
