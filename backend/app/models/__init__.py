"""SQLAlchemy ORM models.

Importing this package registers every model on `Base.metadata`, which is what
`init_db()` relies on to create tables. Any new model must be imported here.
"""

from app.models.watchlist import WatchlistItem

__all__ = ["WatchlistItem"]
