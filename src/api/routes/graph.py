"""Graph route — entity co-occurrence edges for knowledge-graph visualization."""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, aliased

from src.api.deps import get_db
from src.db.models.entity_edge import EntityEdge
from src.db.models.entity_node import EntityNode
from src.db.models.relationship import Relationship

router = APIRouter(tags=["graph"])

NodeA = aliased(EntityNode)
NodeB = aliased(EntityNode)
Subj = aliased(EntityNode)
Obj = aliased(EntityNode)


@router.get("/graph/cooccurrence")
def graph_cooccurrence(
    node_limit: int = Query(
        default=0, ge=0, le=10000,
        description="Restrict to the top-N entities by mention count (0 = all nodes)",
    ),
    min_weight: int = Query(default=1, ge=1),
    limit: int = Query(
        default=200000, ge=1, le=200000,
        description="Safety cap on number of returned edges",
    ),
    label: str | None = Query(default=None, description="Restrict to edges touching this label"),
    db: Session = Depends(get_db),
) -> dict:
    """Co-occurrence edges among the chosen entity set — ready for network viz.

    `node_limit` picks the top-N entities (by mention count) and returns ALL edges
    connecting them; `node_limit=0` returns the full graph. `min_weight` and `label`
    further filter edges. This makes "how many nodes to show" a direct control.
    """
    query = (
        select(
            EntityEdge.id,
            EntityEdge.weight,
            EntityEdge.node_a_id,
            EntityEdge.node_b_id,
            NodeA.canonical_text.label("a_text"),
            NodeA.label.label("a_label"),
            NodeB.canonical_text.label("b_text"),
            NodeB.label.label("b_label"),
        )
        .join(NodeA, EntityEdge.node_a_id == NodeA.id)
        .join(NodeB, EntityEdge.node_b_id == NodeB.id)
        .where(EntityEdge.weight >= min_weight)
    )

    if label:
        lbl = label.upper()
        query = query.where(or_(NodeA.label == lbl, NodeB.label == lbl))

    if node_limit and node_limit > 0:
        nids = db.execute(
            select(EntityNode.id).order_by(desc(EntityNode.mention_count)).limit(node_limit)
        ).scalars().all()
        if nids:
            node_set = set(int(x) for x in nids)
            query = query.where(
                EntityEdge.node_a_id.in_(node_set),
                EntityEdge.node_b_id.in_(node_set),
            )

    query = query.limit(limit)
    rows = db.execute(query).all()

    return {
        "edges": [
            {
                "source": r.node_a_id,
                "target": r.node_b_id,
                "weight": r.weight,
                "source_text": r.a_text,
                "source_label": r.a_label,
                "target_text": r.b_text,
                "target_label": r.b_label,
            }
            for r in rows
        ],
    }


@router.get("/graph/stats")
def graph_stats(db: Session = Depends(get_db)) -> dict:
    """High-level knowledge-graph stats."""
    nodes = db.scalar(select(func.count(EntityNode.id))) or 0
    edges = db.scalar(select(func.count(EntityEdge.id))) or 0
    triples = db.scalar(select(func.count(Relationship.id))) or 0
    by_label = db.execute(
        select(EntityNode.label, func.sum(EntityNode.mention_count).label("mentions"))
        .group_by(EntityNode.label)
        .order_by(desc("mentions"))
    ).all()
    by_pred = db.execute(
        select(Relationship.predicate, func.count(Relationship.id).label("cnt"))
        .group_by(Relationship.predicate)
        .order_by(desc("cnt"))
    ).all()

    return {
        "nodes": nodes,
        "edges": edges,
        "triples": triples,
        "mentions_by_label": {r.label: int(r.mentions or 0) for r in by_label},
        "triples_by_predicate": {r.predicate: int(r.cnt) for r in by_pred},
    }


@router.get("/graph/relationships")
def graph_relationships(
    predicate: str | None = Query(default=None, description="Filter by predicate (e.g. appointed)"),
    label: str | None = Query(
        default=None, description="Restrict to triples touching this entity label",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """Typed relationship triples (subject → predicate → object)."""
    query = (
        select(
            Relationship.id,
            Relationship.predicate,
            Relationship.article_id,
            Relationship.confidence,
            Subj.canonical_text.label("subject_text"),
            Subj.label.label("subject_label"),
            Obj.canonical_text.label("object_text"),
            Obj.label.label("object_label"),
        )
        .join(Subj, Relationship.subject_node_id == Subj.id)
        .join(Obj, Relationship.object_node_id == Obj.id)
    )
    if predicate:
        query = query.where(Relationship.predicate == predicate)
    if label:
        lbl = label.upper()
        query = query.where(or_(Subj.label == lbl, Obj.label == lbl))

    query = query.order_by(desc(Relationship.confidence)).limit(limit)
    rows = db.execute(query).all()

    return {
        "relationships": [
            {
                "subject": r.subject_text,
                "subject_label": r.subject_label,
                "predicate": r.predicate,
                "object": r.object_text,
                "object_label": r.object_label,
                "article_id": r.article_id,
                "confidence": r.confidence,
            }
            for r in rows
        ],
    }


@router.get("/entities/{node_id}/relationships")
def node_relationships(
    node_id: int = Path(..., description="EntityNode id"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """Typed relationships where the given entity is subject or object."""
    query = (
        select(
            Relationship.predicate,
            Relationship.article_id,
            Relationship.confidence,
            Subj.canonical_text.label("subject_text"),
            Subj.label.label("subject_label"),
            Obj.canonical_text.label("object_text"),
            Obj.label.label("object_label"),
        )
        .join(Subj, Relationship.subject_node_id == Subj.id)
        .join(Obj, Relationship.object_node_id == Obj.id)
        .where((Relationship.subject_node_id == node_id) | (Relationship.object_node_id == node_id))
        .order_by(desc(Relationship.confidence))
        .limit(limit)
    )
    rows = db.execute(query).all()

    return {
        "node_id": node_id,
        "relationships": [
            {
                "subject": r.subject_text,
                "subject_label": r.subject_label,
                "predicate": r.predicate,
                "object": r.object_text,
                "object_label": r.object_label,
                "article_id": r.article_id,
                "confidence": r.confidence,
            }
            for r in rows
        ],
    }
