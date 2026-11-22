"""Validate the supported subset of the editor's JSON document format."""

from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.season_summary import PlayServer


class ReferenceScope(BaseModel):
    play_server: PlayServer
    tournament_count: int = Field(ge=0)


ArticleKind = Literal["season", "guide"]
MAX_CAPTION = 300
DocumentType = Literal["doc", "paragraph", "heading", "bulletList", "listItem", "text", "hardBreak", "articleImage"]


class ArticleMark(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["bold", "link"]
    attrs: dict | None = None

    @model_validator(mode="after")
    def normalize_mark(self):
        if self.type == "bold":
            self.attrs = None
            return self
        href = (self.attrs or {}).get("href")
        if not isinstance(href, str) or not 1 <= len(href) <= 2048:
            raise ValueError("Invalid article link")
        if "\\" in href or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in href):
            raise ValueError("Invalid article link")
        url = urlsplit(href)
        local = href.startswith("/") and not href.startswith("//") and not url.netloc
        external = url.scheme in {"http", "https"} and url.hostname and url.username is None and url.password is None
        if not (local or external):
            raise ValueError("Invalid article link")
        self.attrs = {"href": href}
        return self


INLINE = {"text", "hardBreak"}
BLOCKS = {"paragraph", "heading", "bulletList", "articleImage"}
CHILDREN = {
    "doc": BLOCKS, "paragraph": INLINE, "heading": INLINE,
    "bulletList": {"listItem"}, "listItem": BLOCKS,
}


class ArticleNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: DocumentType
    content: list["ArticleNode"] | None = Field(default=None, max_length=1000)
    text: str | None = Field(default=None, max_length=100_000)
    marks: list[ArticleMark] | None = Field(default=None, max_length=2)
    attrs: dict | None = None

    @model_validator(mode="after")
    def normalize_node(self):
        children = self.content or []
        if any(child.type not in CHILDREN.get(self.type, ()) for child in children):
            raise ValueError("Invalid article document structure")
        if self.type in {"doc", "listItem", "bulletList"} and not children:
            raise ValueError("Missing article blocks")
        if self.type == "listItem" and children[0].type != "paragraph":
            raise ValueError("List items must begin with a paragraph")
        if self.type == "text" and not self.text:
            raise ValueError("Missing article text")
        if self.type != "text":
            self.text = None
        if self.type not in INLINE:
            self.marks = None
        elif self.marks and len({mark.type for mark in self.marks}) != len(self.marks):
            raise ValueError("Duplicate article marks")
        if self.type == "heading":
            self.attrs = {"level": 2}
        elif self.type == "articleImage":
            attrs = self.attrs or {}
            try:
                image_id = str(UUID(attrs.get("imageId", "")))
            except (AttributeError, ValueError, TypeError) as exc:
                raise ValueError("Invalid article image") from exc
            caption = attrs.get("caption", "")
            if not isinstance(caption, str) or len(caption) > MAX_CAPTION:
                raise ValueError("Invalid image caption")
            self.attrs = {"imageId": image_id, "caption": caption}
        else:
            self.attrs = None
        return self

    def walk(self):
        nodes = [(self, 0)]
        while nodes:
            node, depth = nodes.pop()
            yield node, depth
            nodes.extend((child, depth + 1) for child in node.content or ())


class ArticleVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: ArticleKind
    championship_id: int | None = Field(default=None, gt=0)
    character_ids: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=300)
    title: str = Field(max_length=200)
    body: ArticleNode
    reference_scope: ReferenceScope | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value):
        return value.strip()

    @model_validator(mode="after")
    def validate_version(self):
        if self.kind == "guide" and self.championship_id is not None:
            raise ValueError("Guides are independent of championships")
        if self.kind == "season" and self.character_ids:
            raise ValueError("Related characters are for guides")
        self.character_ids = list(dict.fromkeys(self.character_ids))
        if self.body.type != "doc":
            raise ValueError("Invalid article document root")
        text_size = 0
        for count, (node, depth) in enumerate(self.body.walk(), 1):
            text_size += len(node.text or "")
            if count > 4000 or depth > 18 or text_size > 100_000:
                raise ValueError("Article document exceeds limits")
        return self

    def image_ids(self):
        return {UUID(node.attrs["imageId"]) for node, _ in self.body.walk() if node.type == "articleImage"}

    def can_publish(self):
        return (
            self.title
            and (self.kind == "guide" or self.championship_id)
            and any((node.text or "").strip() or node.type == "articleImage" for node, _ in self.body.walk())
        )


class ArticleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: ArticleVersion
    publish: bool = False
    reference_server: PlayServer | None = None


class ArticleUpdate(ArticleWrite):
    revision: int = Field(ge=1)
