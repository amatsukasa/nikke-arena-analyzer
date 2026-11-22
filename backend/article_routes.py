"""Article administration and anonymous publication endpoints."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from article_schemas import ArticleUpdate, ArticleWrite
from auth import get_current_user_optional, require_admin
from database import get_db
from services import article_image_cleanup
from services.season_summary import public_scope
from services.article_images import image_path, store_article_image
from services.player_icons import MAX_BYTES, IconTooLarge, InvalidIcon


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


def missing():
    return HTTPException(404, "Article or image not found", headers={"Cache-Control": "no-store"})


def get_article(db, article_id, *, lock=False):
    query = select(models.Article).where(models.Article.id == article_id)
    if lock:
        query = query.with_for_update()
    article = db.scalar(query)
    if article is None:
        raise missing()
    return article


def public_article(article, *, body=False):
    version = article.published
    result = {
        "id": article.id, "title": version["title"], "kind": article.published_kind,
        "championship_id": article.published_championship_id,
        "published_at": article.published_at, "updated_at": article.published_updated_at,
    }
    if body:
        result.update(body=version["body"], character_ids=version["character_ids"])
        if version.get("reference_scope"):
            result["reference_scope"] = version["reference_scope"]
    return result


def public_list(db, kind, championship_id=None):
    return db.scalars(select(models.Article).where(
        models.Article.published_kind == kind,
        models.Article.published_championship_id == championship_id,
    ).order_by(models.Article.published_at.desc(), models.Article.id.desc()))


def list_guides(db: Session = Depends(get_db)):
    return [public_article(article) for article in public_list(db, "guide")]


def season_articles(championship_id: int, db: Session = Depends(get_db)):
    articles = iter(public_list(db, "season", championship_id))
    newest = next(articles, None)
    return {
        "latest": public_article(newest, body=True) if newest else None,
        "earlier": [public_article(article) for article in articles],
    }


def article_image(
    image_id: UUID,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    if user is None or user.role != "admin":
        if db.scalar(select(models.ArticlePublicImage.image_id).where(
            models.ArticlePublicImage.image_id == image_id,
        ).limit(1)) is None:
            raise missing()
    path = image_path(image_id)
    if not path.is_file():
        raise missing()
    return FileResponse(path, media_type="image/webp", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


def read_article(article_id: UUID, db: Session = Depends(get_db)):
    article = get_article(db, article_id)
    if article.published_at is None:
        raise missing()
    return public_article(article, body=True)


def admin_article(article):
    return {
        "id": article.id, "revision": article.revision, "draft": article.draft,
        "published_at": article.published_at,
        "has_unpublished_changes": article.published != article.draft,
    }


def list_articles(db: Session = Depends(get_db)):
    articles = db.scalars(select(models.Article).order_by(models.Article.id))
    return [{
        "id": article.id, "title": article.draft["title"], "kind": article.draft["kind"],
        "published_at": article.published_at, "has_unpublished_changes": article.published != article.draft,
    } for article in articles]


def edit_article(article_id: UUID, db: Session = Depends(get_db)):
    return admin_article(get_article(db, article_id))


def upload_image(file: UploadFile = File(), db: Session = Depends(get_db)):
    data = file.file.read(MAX_BYTES + 1)
    try:
        with article_image_cleanup.image_transaction(db):
            image_id = store_article_image(data)
            article_image_cleanup.track(db, {image_id}, datetime.now(timezone.utc))
            db.commit()
    except IconTooLarge as exc:
        raise HTTPException(413, "Image is too large") from exc
    except InvalidIcon as exc:
        raise HTTPException(422, "Invalid image") from exc
    return {"image_id": image_id}


def save_article(db, article, payload):
    version = payload.draft
    if version.championship_id and not db.get(models.Championship, version.championship_id):
        raise HTTPException(422, "Unknown championship")
    if version.character_ids:
        known_characters = set(db.scalars(select(models.Character.id).where(
            models.Character.id.in_(version.character_ids),
        )))
        if known_characters != set(version.character_ids):
            raise HTTPException(422, "Unknown character")

    images = version.image_ids()
    if any(not image_path(image_id).is_file() for image_id in images):
        raise HTTPException(422, "Unknown article image")
    previous_images = article_image_cleanup.version_images(article.draft, article.published)
    saved_draft = article.draft or {}
    draft = version.model_dump(exclude_none=True, exclude={"reference_scope"})
    draft.setdefault("championship_id", None)
    if payload.reference_server and (version.kind != "season" or not version.championship_id):
        raise HTTPException(422, "A reference server requires a season article and championship")
    if version.kind == "season":
        if payload.reference_server:
            _, _, scope = public_scope(db, version.championship_id, payload.reference_server)
            draft["reference_scope"] = {key: scope[key] for key in ("play_server", "tournament_count")}
        elif (saved_draft.get("championship_id") == version.championship_id
              and saved_draft.get("reference_scope")):
            draft["reference_scope"] = saved_draft["reference_scope"]
    article.draft = draft
    if payload.publish and not version.can_publish():
        raise HTTPException(422, "Title, content and any required championship must be set")
    if payload.publish and article.published != article.draft:
        now = datetime.now(timezone.utc)
        article.published_at = article.published_at or now
        article.published_updated_at = now
        article.published = article.draft
        article.published_kind = version.kind
        article.published_championship_id = version.championship_id
        existing = {reference.image_id: reference for reference in article.public_images}
        for image_id, reference in existing.items():
            if image_id not in images:
                article.public_images.remove(reference)
        article.public_images.extend(models.ArticlePublicImage(image_id=image_id) for image_id in images - existing.keys())
    db.add(article)
    result = admin_article(article)
    try:
        article_image_cleanup.update_references(db, article, previous_images)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Article references changed. Reload and try again.") from exc
    return result


def create_article(payload: ArticleWrite, db: Session = Depends(get_db)):
    with article_image_cleanup.image_transaction(db):
        article = models.Article(id=uuid4(), revision=1)
        return save_article(db, article, payload)


def update_article(article_id: UUID, payload: ArticleUpdate, db: Session = Depends(get_db)):
    with article_image_cleanup.image_transaction(db):
        article = get_article(db, article_id, lock=True)
        if article.revision != payload.revision:
            raise HTTPException(409, "The article has changed. Reload before saving again.")
        article.revision += 1
        return save_article(db, article, payload)


def register_article_routes(app: FastAPI):
    public = "/api/articles"
    admin = "/api/admin/articles"
    no_cache = [Depends(no_store)]
    admin_only = [Depends(require_admin), Depends(no_store)]

    app.add_api_route(f"{public}/guides", list_guides, methods=["GET"], dependencies=no_cache)
    app.add_api_route(f"{public}/season/{{championship_id}}", season_articles, methods=["GET"], dependencies=no_cache)
    app.add_api_route(f"{public}/images/{{image_id}}", article_image, methods=["GET"])
    app.add_api_route(f"{public}/{{article_id}}", read_article, methods=["GET"], dependencies=no_cache)

    app.add_api_route(admin, list_articles, methods=["GET"], dependencies=admin_only)
    app.add_api_route(admin, create_article, methods=["POST"], dependencies=admin_only, status_code=201)
    app.add_api_route(f"{admin}/images", upload_image, methods=["POST"], dependencies=admin_only, status_code=201)
    app.add_api_route(f"{admin}/{{article_id}}", edit_article, methods=["GET"], dependencies=admin_only)
    app.add_api_route(f"{admin}/{{article_id}}", update_article, methods=["PUT"], dependencies=admin_only)
