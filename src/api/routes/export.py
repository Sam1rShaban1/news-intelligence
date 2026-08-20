"""Export routes — dump articles / search results / story members as CSV or JSON.

Pi-safe: streaming generation with the stdlib `csv` module, no heavy deps.
Use `?format=csv` for a downloadable spreadsheet, or `?format=json` (default)
for the structured payload the rest of the API uses.
"""

import csv
import io
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from config.settings import settings
from src.api.deps import get_db
from src.api.search_query import apply_filters
from src.db.models.article import Article
from src.db.models.source import Source
from src.db.models.story import Story, story_articles

router = APIRouter(prefix="/export", tags=["export"])


def _rows_to_csv(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in columns})
    return buf.getvalue()


def _respond(rows: list[dict], columns: list[str], format: str, filename: str):
    if format == "csv":
        csv_text = _rows_to_csv(rows, columns)
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    return {"total": len(rows), "format": "json", "items": rows}


@router.get("/articles", response_model=None)
def export_articles(
    format: str = Query(default="json", description="csv | json"),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    source_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None, description="ISO date (discovered_at >=)"),
    db: Session = Depends(get_db),
) -> Response | dict:
    """Export the article list in CSV or JSON (same filters as GET /articles)."""
    query = (
        select(
            Article.id,
            Article.title,
            Article.url,
            Article.source_id,
            Source.name.label("source_name"),
            Article.language,
            Article.sentiment_label,
            Article.status,
            Article.published_date,
            Article.discovered_at,
            Article.summary,
        )
        .join(Source, Source.id == Article.source_id)
    )
    if source_id is not None:
        query = query.where(Article.source_id == source_id)
    if status is not None:
        query = query.where(Article.status == status)
    if since:
        query = query.where(Article.discovered_at >= since)
    query = query.order_by(desc(Article.discovered_at)).limit(limit).offset(offset)
    rows = db.execute(query).all()

    columns = [
        "id", "title", "url", "source_id", "source_name", "language",
        "sentiment_label", "status", "published_date", "discovered_at", "summary",
    ]
    items = [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "source_id": r.source_id,
            "source_name": r.source_name,
            "language": r.language,
            "sentiment_label": r.sentiment_label,
            "status": r.status,
            "published_date": r.published_date.isoformat() if r.published_date else None,
            "discovered_at": r.discovered_at.isoformat() if r.discovered_at else None,
            "summary": r.summary,
        }
        for r in rows
    ]
    return _respond(items, columns, format, "articles.csv")


@router.get("/search", response_model=None)
def export_search(
    format: str = Query(default="json", description="csv | json"),
    q: str | None = Query(default=None, min_length=2),
    language: str | None = Query(default=None),
    sentiment: str | None = Query(default=None),
    source_id: int | None = Query(default=None),
    entity: str | None = Query(default=None),
    predicate: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> Response | dict:
    """Export search / filtered-browse results in CSV or JSON."""
    sel = (
        select(
            Article.id,
            Article.title,
            Article.url,
            Article.source_id,
            Source.name.label("source_name"),
            Article.language,
            Article.sentiment_label,
            Article.published_date,
            Article.summary,
        )
        .join(Source, Source.id == Article.source_id)
    )
    sel = apply_filters(
        sel, q, language, sentiment, source_id, entity, predicate, date_from, date_to
    )
    sel = sel.order_by(desc(Article.discovered_at)).limit(limit)
    rows = db.execute(sel).all()

    columns = [
        "id", "title", "url", "source_id", "source_name", "language",
        "sentiment_label", "published_date", "summary",
    ]
    items = [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "source_id": r.source_id,
            "source_name": r.source_name,
            "language": r.language,
            "sentiment_label": r.sentiment_label,
            "published_date": r.published_date.isoformat() if r.published_date else None,
            "summary": r.summary,
        }
        for r in rows
    ]
    return _respond(items, columns, format, "search.csv")


@router.get("/stories/{story_id}", response_model=None)
def export_story(
    story_id: int,
    format: str = Query(default="json", description="csv | json"),
    db: Session = Depends(get_db),
) -> Response | dict:
    """Export all member articles of a story as CSV or JSON."""
    story = db.get(Story, story_id)
    if story is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Story not found")

    rows = db.execute(
        select(
            Article.id,
            Article.title,
            Article.url,
            Source.name.label("source_name"),
            Article.language,
            Article.sentiment_label,
            Article.published_date,
            Article.discovered_at,
            Article.summary,
        )
        .join(story_articles, story_articles.c.article_id == Article.id)
        .join(Source, Article.source_id == Source.id)
        .where(story_articles.c.story_id == story_id)
        .order_by(desc(Article.discovered_at))
    ).all()

    columns = [
        "id", "title", "url", "source_name", "language",
        "sentiment_label", "published_date", "discovered_at", "summary",
    ]
    items = [
        {
            "id": r.id,
            "title": r.title,
            "url": r.url,
            "source_name": r.source_name,
            "language": r.language,
            "sentiment_label": r.sentiment_label,
            "published_date": r.published_date.isoformat() if r.published_date else None,
            "discovered_at": r.discovered_at.isoformat() if r.discovered_at else None,
            "summary": r.summary,
        }
        for r in rows
    ]
    return _respond(items, columns, format, f"story_{story_id}.csv")


# ---- PDF export (vps tier; requires reportlab) -------------------------------

def _build_pdf(title: str, blocks: list[tuple[str, str]]) -> bytes:
    """Render a simple title + paragraph document to PDF bytes via reportlab."""
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

    def esc(s: str | None) -> str:
        if not s:
            return ""
        return (
            s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    styles = getSampleStyleSheet()
    h = ParagraphStyle("H", parent=styles["Title"], fontSize=18, leading=22, spaceAfter=6)
    meta = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, textColor="#555550",
                          spaceAfter=10)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=14,
                         alignment=TA_LEFT, spaceAfter=8)
    sub = ParagraphStyle("Sub", parent=styles["Heading2"], fontSize=12, spaceBefore=8,
                        spaceAfter=4)

    from io import BytesIO
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm, title=title,
    )
    flow = [Paragraph(esc(title), h)]
    for kind, text in blocks:
        if kind == "meta":
            flow.append(Paragraph(esc(text), meta))
        elif kind == "hr":
            flow.append(Spacer(1, 4))
            flow.append(HRFlowable(width="100%", thickness=0.5, color="#0a0a0a"))
            flow.append(Spacer(1, 4))
        elif kind == "sub":
            flow.append(Paragraph(esc(text), sub))
        else:
            flow.append(Paragraph(esc(text), body))
    doc.build(flow)
    return buf.getvalue()


@router.get("/articles/{article_id}/pdf", response_model=None)
def export_article_pdf(article_id: int, db: Session = Depends(get_db)) -> Response:
    """Server-rendered PDF of a single article (vps tier; FEATURE_PDF_EXPORT)."""
    if not settings.feature_pdf_export:
        raise HTTPException(
            status_code=503, detail="PDF export is disabled (FEATURE_PDF_EXPORT=false)"
        )

    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    source = db.get(Source, article.source_id)
    blocks = []
    if source:
        blocks.append(("meta", f"Source: {source.name}  ·  {article.language or ''}"))
    if article.published_date:
        blocks.append(("meta", f"Published: {article.published_date.isoformat()}"))
    if article.sentiment_label:
        blocks.append(("meta", f"Sentiment: {article.sentiment_label}"))
    blocks.append(("hr", ""))
    if article.summary:
        blocks.append(("sub", "Summary"))
        blocks.append(("body", article.summary))
    if article.content:
        blocks.append(("sub", "Body"))
        blocks.append(("body", article.content))
    if article.url:
        blocks.append(("meta", f"URL: {article.url}"))
    pdf = _build_pdf(article.title or "Article", blocks)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=article_{article_id}.pdf"},
    )


@router.get("/stories/{story_id}/pdf", response_model=None)
def export_story_pdf(story_id: int, db: Session = Depends(get_db)) -> Response:
    """Server-rendered PDF of a story: summary plus its member articles."""
    if not settings.feature_pdf_export:
        raise HTTPException(
            status_code=503, detail="PDF export is disabled (FEATURE_PDF_EXPORT=false)"
        )

    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")

    rows = db.execute(
        select(
            Article.id, Article.title, Article.url, Source.name.label("source_name"),
            Article.language, Article.sentiment_label, Article.summary,
        )
        .join(story_articles, story_articles.c.article_id == Article.id)
        .join(Source, Article.source_id == Source.id)
        .where(story_articles.c.story_id == story_id)
        .order_by(desc(Article.discovered_at))
    ).all()

    blocks = []
    if story.first_seen:
        blocks.append(("meta", f"First seen: {story.first_seen.isoformat()}"))
    if story.last_seen:
        blocks.append(("meta", f"Last seen: {story.last_seen.isoformat()}"))
    blocks.append(("meta", f"Articles: {len(rows)}"))
    blocks.append(("hr", ""))
    if story.summary:
        blocks.append(("sub", "Summary"))
        blocks.append(("body", story.summary))
    blocks.append(("sub", "Member articles"))
    for r in rows:
        line = f"• {r.title or '(untitled)'} — {r.source_name or ''} ({r.language or ''})"
        if r.sentiment_label:
            line += f" [{r.sentiment_label}]"
        blocks.append(("body", line))
        if r.summary:
            blocks.append(("body", r.summary))
    pdf = _build_pdf(story.title or "Story", blocks)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=story_{story_id}.pdf"},
    )
