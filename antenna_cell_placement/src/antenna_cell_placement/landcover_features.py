"""
ESA WorldCover 2021 land-cover features for the H3 pilot-city planning grid.
Computes the percentage of each land-cover class covering each hexagon.
"""

from typing import List

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterstats import zonal_stats

from antenna_cell_placement.config import ESA_WORLDCOVER_TILES

# Official ESA WorldCover v200 class codes.
WORLDCOVER_CLASSES = {
    10: "landcover_treecover_pct",
    20: "landcover_shrubland_pct",
    30: "landcover_grassland_pct",
    40: "landcover_cropland_pct",
    50: "landcover_builtup_pct",
    60: "landcover_bare_pct",
    70: "landcover_snowice_pct",
    80: "landcover_water_pct",
    90: "landcover_wetland_pct",
    95: "landcover_mangroves_pct",
    100: "landcover_mosslichen_pct",
}


def load_worldcover_mosaic(tile_paths: List = ESA_WORLDCOVER_TILES):
    """Merge the ESA WorldCover tiles covering a pilot city into one in-memory array."""
    sources = [rasterio.open(str(p)) for p in tile_paths]
    mosaic, transform = merge(sources)
    for src in sources:
        src.close()
    return mosaic[0], transform


def compute_landcover_pct_per_hex(hex_gdf: gpd.GeoDataFrame, tile_paths: List = ESA_WORLDCOVER_TILES) -> pd.DataFrame:
    """Compute the % of each land-cover class within each hex polygon via zonal stats."""
    print("Merging ESA WorldCover tiles...")
    array, transform = load_worldcover_mosaic(tile_paths)

    print(f"Computing land-cover zonal stats for {len(hex_gdf)} hexes...")
    stats = zonal_stats(
        hex_gdf.geometry,
        array,
        affine=transform,
        categorical=True,
        nodata=0,
    )

    rows = []
    for hex_stats in stats:
        total = sum(hex_stats.values()) or 1
        row = {col: 0.0 for col in WORLDCOVER_CLASSES.values()}
        for class_code, count in hex_stats.items():
            col = WORLDCOVER_CLASSES.get(int(class_code))
            if col is not None:
                row[col] = round(100.0 * count / total, 2)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["h3_index"] = hex_gdf["h3_index"].values
    return df


if __name__ == "__main__":
    import geopandas as gpd
    from antenna_cell_placement.config import H3_GRID_GEOJSON_TEMPLATE, DEFAULT_PILOT_CITY

    grid = gpd.read_file(H3_GRID_GEOJSON_TEMPLATE.format(city=DEFAULT_PILOT_CITY))
    result = compute_landcover_pct_per_hex(grid)
    print(result.head())
