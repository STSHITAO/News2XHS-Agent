from __future__ import annotations

from app.tools import ToolExecutor


def test_dispatch_calls_favorite_feed() -> None:
    executor = ToolExecutor()
    called: dict[str, bool] = {"favorite": False}

    def _favorite_feed(*, feed_id: str, xsec_token: str, unfavorite: bool = False):
        called["favorite"] = True
        assert feed_id == "abc"
        assert xsec_token == "token"
        assert unfavorite is False
        return {"success": True, "message": "favorited"}

    executor.xhs.favorite_feed = _favorite_feed  # type: ignore[method-assign]

    result = executor.call(
        "favorite_feed",
        {"feed_id": "abc", "xsec_token": "token"},
    )
    assert called["favorite"] is True
    assert result["isError"] is False


def test_dispatch_calls_like_feed_with_unlike() -> None:
    executor = ToolExecutor()
    called: dict[str, bool] = {"like": False}

    def _like_feed(*, feed_id: str, xsec_token: str, unlike: bool = False):
        called["like"] = True
        assert feed_id == "abc"
        assert xsec_token == "token"
        assert unlike is True
        return {"success": True, "message": "unliked"}

    executor.xhs.like_feed = _like_feed  # type: ignore[method-assign]

    result = executor.call(
        "like_feed",
        {"feed_id": "abc", "xsec_token": "token", "unlike": True},
    )
    assert called["like"] is True
    assert result["isError"] is False
