"""Command-line interface: `cvm <command>`.

A thin wrapper over the same entry points tasks.ps1 and the Makefile call, so
there is one implementation and three ways to reach it rather than three
implementations that drift.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="AI CVM Suite", no_args_is_help=True)


@app.command()
def ingest() -> None:
    """Validate, deduplicate, hash and land every source."""
    from cvm.ingest.run import main

    main()


@app.command()
def synthesise() -> None:
    """Fit the GAN, sample the population, run the quality gate."""
    from cvm.synthesis.run import main

    main()


@app.command()
def features() -> None:
    """Build the feature store and the sequence tensors."""
    from cvm.features.run import main

    main()


@app.command()
def pipeline() -> None:
    """ingest -> synthesise -> features."""
    ingest()
    synthesise()
    features()


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:
    """Run the API."""
    import uvicorn

    uvicorn.run("cvm.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
