"""Streamlit dashboard — live view of the news intelligence pipeline."""

import os

import streamlit as st
from sqlalchemy import create_engine, text
from streamlit_agraph import Config, Edge, Node, agraph

DATABASE_URL = os.getenv(
    "NEWS_DATABASE_URL", "postgresql://news:news@localhost:5432/news_intelligence"
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

st.set_page_config(page_title="News Intelligence", layout="wide")
st.title("News Intelligence — North Macedonia")

# ── Summary cards ──────────────────────────────────────────
with engine.connect() as conn:
    total = conn.scalar(text("SELECT count(*) FROM articles")) or 0
    sources = conn.scalar(text("SELECT count(*) FROM sources WHERE enabled")) or 0
    extracted = conn.scalar(text("SELECT count(*) FROM articles WHERE status='extracted'")) or 0
    analyzed = conn.scalar(text("SELECT count(*) FROM articles WHERE status='analyzed'")) or 0
    failed = conn.scalar(text("SELECT count(*) FROM articles WHERE status='failed'")) or 0
    entities = conn.scalar(text("SELECT count(*) FROM entities")) or 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Articles", total)
c2.metric("Sources", sources)
c3.metric("Extracted", extracted)
c4.metric("Analyzed", analyzed)
c5.metric("Failed", failed)
c6.metric("Entities", entities)

# ── Tabs ───────────────────────────────────────────────────
tab_pipeline, tab_sentiment, tab_entities, tab_graph = st.tabs(
    ["Pipeline", "Sentiment", "Entities", "Knowledge Graph"]
)

with tab_pipeline:
    st.subheader("Pipeline Status")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT status, count(*) as cnt FROM articles GROUP BY status ORDER BY cnt DESC")
        ).all()
    if rows:
        st.bar_chart({r.status: r.cnt for r in rows})

    st.subheader("Languages (extracted+)")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT language, count(*) as cnt FROM articles WHERE status IN ('extracted','analyzed') GROUP BY language ORDER BY cnt DESC")
        ).all()
    if rows:
        st.bar_chart({r.language: r.cnt for r in rows})

    st.subheader("Recent Articles")
    limit = st.slider("Show", 5, 50, 10, key="pipeline_limit")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT a.title, a.url, a.language, a.status, a.sentiment_label, a.discovered_at, s.name as source "
                "FROM articles a JOIN sources s ON a.source_id = s.id "
                "ORDER BY a.discovered_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).all()
    if rows:
        for r in rows:
            sentiment_badge = f" [{r.sentiment_label}]" if r.sentiment_label else ""
            st.markdown(f"**[{r.title or r.url}]({r.url})**{sentiment_badge}")
            st.caption(f"{r.source} · {r.language} · {r.status} · {r.discovered_at}")

with tab_sentiment:
    st.subheader("Sentiment Distribution")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT sentiment_label, count(*) as cnt, avg(sentiment_score) as avg_score "
                "FROM articles WHERE sentiment_label IS NOT NULL "
                "GROUP BY sentiment_label ORDER BY cnt DESC"
            )
        ).all()
    if rows:
        st.bar_chart({r.sentiment_label: r.cnt for r in rows})
        for r in rows:
            st.caption(f"{r.sentiment_label}: {r.count} articles, avg score {r.avg_score:.3f}")
    else:
        st.info("No analyzed articles yet.")

    st.subheader("Recent Sentiment")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT title, sentiment_score, sentiment_label, language "
                "FROM articles WHERE sentiment_label IS NOT NULL "
                "ORDER BY analyzed_at DESC LIMIT 20"
            )
        ).all()
    if rows:
        for r in rows:
            score = r.sentiment_score or 0
            emoji = "+" if score > 0.05 else ("-" if score < -0.05 else "~")
            st.markdown(f"**{r.title or 'untitled'}** — {r.sentiment_label} ({score:+.3f})")
            st.caption(f"{r.language}")

with tab_entities:
    st.subheader("Top Entities")
    label_filter = st.selectbox("Filter by label", ["All", "PER", "ORG", "LOC", "MISC"], key="ent_label")
    with engine.connect() as conn:
        if label_filter == "All":
            rows = conn.execute(
                text(
                    "SELECT text, label, count(*) as cnt FROM entities "
                    "GROUP BY text, label ORDER BY cnt DESC LIMIT 30"
                )
            ).all()
        else:
            rows = conn.execute(
                text(
                    "SELECT text, label, count(*) as cnt FROM entities "
                    "WHERE label = :lbl GROUP BY text, label ORDER BY cnt DESC LIMIT 30"
                ),
                {"lbl": label_filter},
            ).all()
    if rows:
        st.dataframe(
            [{"Text": r.text, "Label": r.label, "Mentions": r.cnt} for r in rows],
            use_container_width=True,
        )
    else:
        st.info("No entities extracted yet.")

    st.subheader("Entity Type Distribution")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT label, count(*) as cnt FROM entities GROUP BY label ORDER BY cnt DESC")
        ).all()
    if rows:
        st.bar_chart({r.label: r.cnt for r in rows})

with tab_graph:
    st.subheader("Knowledge Graph — Entity Co-occurrence")

    # Graph stats
    with engine.connect() as conn:
        stats = conn.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM entity_nodes) AS nodes, "
                "(SELECT count(*) FROM entity_edges) AS edges"
            )
        ).one()
        by_label = conn.execute(
            text(
                "SELECT label, coalesce(sum(mention_count),0) AS mentions "
                "FROM entity_nodes GROUP BY label ORDER BY mentions DESC"
            )
        ).all()

    c1, c2 = st.columns(2)
    c1.metric("Entity Nodes", stats.nodes)
    c2.metric("Co-occurrence Edges", stats.edges)
    if by_label:
        st.caption("Mentions by type: " + ", ".join(f"{r.label}={int(r.mentions)}" for r in by_label))

    label_filter = st.selectbox(
        "Entity type", ["All", "PER", "ORG", "LOC", "MISC", "EVENT"], key="graph_label"
    )
    top_n = st.slider("Top nodes", 20, 150, 60, key="graph_topn")

    def fetch_graph(label: str, top_n: int):
        with engine.connect() as conn:
            nodes = conn.execute(
                text(
                    "SELECT id, canonical_text, label, mention_count "
                    "FROM entity_nodes "
                    + ("WHERE label = :lbl " if label != "All" else "")
                    + "ORDER BY mention_count DESC LIMIT :lim"
                ),
                {"lbl": label, "lim": top_n} if label != "All" else {"lim": top_n},
            ).all()
            node_ids = [r.id for r in nodes]
            edges = conn.execute(
                text(
                    "SELECT e.node_a_id, e.node_b_id, e.weight, "
                    "a.canonical_text AS a_text, b.canonical_text AS b_text "
                    "FROM entity_edges e "
                    "JOIN entity_nodes a ON e.node_a_id = a.id "
                    "JOIN entity_nodes b ON e.node_b_id = b.id "
                    "WHERE e.node_a_id = ANY(:ids) AND e.node_b_id = ANY(:ids) "
                    "ORDER BY e.weight DESC LIMIT 500"
                ),
                {"ids": node_ids},
            ).all()
        return nodes, edges

    nodes, edges = fetch_graph(label_filter, top_n)

    if not nodes:
        st.info("No entities yet — the NER service is still building the graph.")
    else:
        LABEL_COLORS = {
            "PER": "#4C78A8",
            "ORG": "#F58518",
            "LOC": "#54A24B",
            "MISC": "#E45756",
            "EVENT": "#72B7B2",
            "DATE": "#EECA3B",
        }

        node_ids_in_edges = {e.node_a_id for e in edges} | {e.node_b_id for e in edges}
        g_nodes = [
            Node(
                id=str(r.id),
                label=r.canonical_text[:24],
                size=min(40, 8 + int(r.mention_count)),
                color=LABEL_COLORS.get(r.label, "#B0B0B0"),
                title=f"{r.canonical_text} ({r.label}) — {r.mention_count} mentions",
            )
            for r in nodes
            if r.id in node_ids_in_edges or not edges
        ]
        g_edges = [
            Edge(
                source=str(e.node_a_id),
                target=str(e.node_b_id),
                width=min(8.0, 0.5 + e.weight / 2.0),
                type="CURVE_SMOOTH",
                title=f"weight {e.weight}",
            )
            for e in edges
        ]

        config = Config(
            width="100%",
            height=600,
            directed=False,
            physics=True,
            hierarchical=False,
            collapsible=True,
            node={"labelProperty": "label"},
            link={"labelProperty": "title"},
            maxZoom=4,
            minZoom=0.2,
        )
        st.write(f"Showing {len(g_nodes)} nodes, {len(g_edges)} edges")
        agraph(nodes=g_nodes, edges=g_edges, config=config)

        # ── Entity detail: click to inspect ──
        st.divider()
        st.subheader("Inspect an entity")
        search = st.text_input("Search entity", key="graph_search")
        if search:
            with engine.connect() as conn:
                matches = conn.execute(
                    text(
                        "SELECT id, canonical_text, label, mention_count "
                        "FROM entity_nodes WHERE canonical_text ILIKE :q "
                        "ORDER BY mention_count DESC LIMIT 25"
                    ),
                    {"q": f"%{search}%"},
                ).all()
            if matches:
                label_map = {
                    m.id: f"{m.canonical_text} ({m.label}, {m.mention_count})" for m in matches
                }
                choice = st.selectbox(
                    "Select",
                    options=[m.id for m in matches],
                    format_func=lambda mid: label_map.get(mid, str(mid)),
                )
                if choice:
                    with engine.connect() as conn:
                        arts = conn.execute(
                            text(
                                "SELECT a.title, a.url, a.sentiment_label, a.language "
                                "FROM articles a JOIN entities e ON e.article_id = a.id "
                                "WHERE e.node_id = :nid ORDER BY a.discovered_at DESC LIMIT 25"
                            ),
                            {"nid": choice},
                        ).all()
                        neigh = conn.execute(
                            text(
                                "SELECT e.node_a_id, e.node_b_id, e.weight, "
                                "n.canonical_text, n.label "
                                "FROM entity_edges e JOIN entity_nodes n ON n.id = "
                                "CASE WHEN e.node_a_id = :nid THEN e.node_b_id "
                                "ELSE e.node_a_id END "
                                "WHERE e.node_a_id = :nid OR e.node_b_id = :nid "
                                "ORDER BY e.weight DESC LIMIT 30"
                            ),
                            {"nid": choice},
                        ).all()
                    st.markdown(f"**{len(arts)} articles** mention this entity:")
                    for r in arts:
                        badge = f" [{r.sentiment_label}]" if r.sentiment_label else ""
                        st.markdown(f"**[{r.title or 'untitled'}]({r.url})**{badge}  ·  {r.language}")
                    st.markdown("**Connected entities:**")
                    for r in neigh:
                        st.caption(f"{r.canonical_text} ({r.label}) — co-occurred {r.weight}×")
            else:
                st.info("No matching entity.")

# ── Source health (collapsed) ──────────────────────────────
with st.expander("Source Health"):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT s.name, s.enabled, s.article_count, s.last_scanned_at, s.last_error "
                "FROM sources s ORDER BY s.name"
            )
        ).all()
    if rows:
        st.dataframe(
            [{"Name": r.name, "Enabled": r.enabled, "Articles": r.article_count,
              "Last Scan": r.last_scanned_at, "Error": r.last_error} for r in rows],
            use_container_width=True,
        )
