import asyncio
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from os import path, urandom

from flask import Flask, abort, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_all_lexers, get_lexer_by_name
from sqlalchemy import Text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite+aiosqlite:///" + path.join(
    path.abspath(path.dirname(__file__)), "db.sqlite"
)
db = SQLAlchemy(app)


class Paste(db.Model):
    id: Mapped[str] = mapped_column(
        primary_key=True, default=lambda: urlsafe_b64encode(urandom(4)).decode()[:6]
    )
    body: Mapped[str] = mapped_column(Text)
    language: Mapped[str]
    timestamp: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), index=True
    )


with app.app_context():
    # Create database
    async def initdb():
        engine = create_async_engine(db.engine.url)
        db.Session = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as con:
            await con.run_sync(db.Model.metadata.create_all)

    asyncio.run(initdb())


languages = sorted([(lexer[1][0], lexer[0]) for lexer in get_all_lexers() if lexer[1]])


@app.route("/", methods=["GET", "POST"])
async def index():
    async with db.Session() as session:
        if request.method == "POST":
            paste = Paste(body=request.form["body"], language=request.form["language"])
            session.add(paste)
            await session.commit()
            return redirect(url_for("paste", id=paste.id))
        _pastes = await session.stream_scalars(
            db.select(Paste).order_by(Paste.timestamp.desc()).limit(10)
        )
        return render_template(
            "index.html",
            languages=languages,
            pastes=[p async for p in _pastes],
        )


@app.get("/<id>")
async def paste(id):
    async with db.Session() as session:
        paste = await session.get(Paste, id)
        if not paste:
            abort(404)
        lexer = get_lexer_by_name(paste.language, stripall=True)
        formatter = HtmlFormatter(lineos=True, cssclass="source")
        highlight_body = highlight(paste.body, lexer, formatter)
        highlight_css = formatter.get_style_defs(".source")
        return render_template(
            "paste.html", highlight_body=highlight_body, highlight_css=highlight_css
        )


@app.errorhandler(404)
async def not_found(e):
    return render_template("404.html"), 404
