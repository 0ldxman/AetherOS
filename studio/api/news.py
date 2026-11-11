"""Новости команды игрокам. Логика в news.feed."""
import datetime as dt

from django.shortcuts import get_object_or_404
from ninja import Router, Schema

from news import feed
from news.models import Post

router = Router(tags=["news"])


class NwRow(Schema):
    id: int
    title: str
    status: str                 # draft | scheduled | published
    publish_at: dt.datetime | None
    pinned: bool
    important: bool
    reads: int
    author: str


class NwOut(NwRow):
    body: str
    updated_at: dt.datetime


class NwIn(Schema):
    title: str
    body: str = ""
    publish_at: dt.datetime | None = None
    pinned: bool = False
    important: bool = False


def _row(post):
    return dict(id=post.pk, title=post.title, status=post.status, publish_at=post.publish_at, pinned=post.pinned, important=post.important,
                reads=post.reads.count(), author=post.author.get_username() if post.author_id else "")


def _out(post):
    return NwOut(**_row(post), body=post.body, updated_at=post.updated_at)


@router.get("", response=list[NwRow])
def index(request):
    posts = Post.objects.select_related("author").order_by("-updated_at")
    return [NwRow(**_row(post)) for post in posts]


@router.post("", response=NwOut)
def create(request, body: NwIn):
    return _out(feed.save(Post(), author=request.user, **body.dict()))


@router.get("/{post_id}", response=NwOut)
def detail(request, post_id: int):
    return _out(get_object_or_404(Post, pk=post_id))


@router.put("/{post_id}", response=NwOut)
def update(request, post_id: int, body: NwIn):
    return _out(feed.save(get_object_or_404(Post, pk=post_id), author=request.user, **body.dict()))


@router.delete("/{post_id}", response={204: None})
def delete(request, post_id: int):
    get_object_or_404(Post, pk=post_id).delete()
    return 204, None
