"""Dataset-only telecom GIS placement planning for Libya."""

__all__ = [
    "evaluate_candidate",
    "get_top_recommendations",
]


def __getattr__(name):
    """Keep package import light; load the public placement API on demand."""
    if name in __all__:
        from antenna_cell_placement import placement

        return getattr(placement, name)
    raise AttributeError(name)
