# Regular Imports
from geojson.feature import *
from src.general_utils import *


class HexGrid:
    """
    Hexagonal Grid based on H3 with functionality to join a set of points to it and plot those values
    What I need to do is retool the class to do outer joins and then also to make it so that it is generalizable

    Attributes
    ----------
    resolution : str
        Resolution of the H3 Hexagonal Grid
    region : GeoPandas DF
        GeoPandas DataFrame representing the are across which you want to join features
    """

    def __init__(self, resolution):
        """
        Input the region and resolution of  the hexagonal grid
        """

        # initialize attributes
        self.hex_grid = generate_hexgrid(by_hour=True)
        self.resolution = resolution
        self.hex_data = None

    def join(self, df, groupby_items, agg_map, resolution):
        """
        Bin the input dataframe by h3 hexagons
        """

        # Bin the dataframe by hexagon with the specified params
        df_aggreg = bin_by_hexagon(df, groupby_items, agg_map, resolution)

        # Join with the polyfill grid with the df_aggreg
        df_outer = pd.merge(left=self.hex_grid[["hex_id", "hour", "geometry"]],
                            right=df_aggreg[["hex_id", "hour", "energy"]],
                            left_on=groupby_items, right_on=groupby_items, how="left")

        df_outer = df_outer.fillna(0)

        self.hex_data = df_outer

    def plot(self, value_to_map, kind, hour):

        # Use choropleth plotting function
        hmap = h3_choropleth_map(self.hex_data, value_to_map, kind, hour)

        return hmap
