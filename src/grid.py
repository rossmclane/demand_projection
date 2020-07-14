# Regular Imports
import pandas as pd
from h3 import h3
from geojson.feature import *
from folium import Map, Marker, GeoJson
import branca.colormap as cm
import json


class HexGrid:
    """
    Hexagonal Grid based on H3 which can combine with charging event data and
    has functionality to display/write out the resulting graphics

    Attributes
    ----------
    resolution : str
        Resolution of the H3 Hexagonal Grid
    """

    def __init__(self, resolution):
        self.resolution = resolution
        self.charges = pd.DataFrame()
        self.hourly_charges = pd.DataFrame()

    def sjoin(self, charges):
        """
        Convert the ChargingEvents Object to a pandas dataframe of charging events

        Parameters
        ----------
        self: object
            Python Class Object
        charges: GeoPandas DataFrame
            GPD of hourly charging events
        """

        # Add Uber H3 Hex ID to each charging event
        charges["hex_id"] = charges.apply(
            lambda row: h3.geo_to_h3(row["longitude"], row["latitude"], resolution=self.resolution), axis=1)

        # Add the geometry associated with each HEX_ID
        charges["geometry"] = charges.hex_id.apply(lambda x:
                                                   {"type": "Polygon",
                                                    "coordinates":
                                                        [h3.h3_to_geo_boundary(h=x, geo_json=True)]
                                                    }
                                                   )

        self.charges = charges

    def hourly_sjoin(self, charges):

        # Add Uber H3 Hex ID to each charging event
        charges["hex_id"] = charges.apply(
            lambda row: h3.geo_to_h3(row["latitude"], row["longitude"], resolution=self.resolution), axis=1)

        # Add the geometry associated with each HEX_ID
        charges["geometry"] = charges.hex_id.apply(lambda x:
                                                   {"type": "Polygon",
                                                    "coordinates":
                                                        [h3.h3_to_geo_boundary(h=x, geo_json=True)]
                                                    }
                                                   )

        hourly_charges = charges.groupby(['hex_id', 'hour']).agg(
            {'delta_soc': 'mean', 'energy': 'mean', 'state_of_charge': 'mean', 'geometry': 'first'}).reset_index()

        self.hourly_charges = hourly_charges

        return hourly_charges

    def plot(self, hour=None, value='energy', border_color='black', fill_opacity=0.7, initial_map=None, with_legend=True,
             kind="linear"):

        if hour is not None:
            df = self.hourly_charges[self.hourly_charges.hour == hour]
        else:
            df = self.hourly_charges

        # colormap
        min_value = df[value].min()
        max_value = df[value].max()
        m = round((min_value + max_value) / 2, 0)

        res = h3.h3_get_resolution(df['hex_id'].iloc[0])

        if initial_map is None:
            initial_map = Map(location=[34.052235, -118.243683], zoom_start=11, tiles="cartodbpositron",
                              attr='© <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="http://cartodb.com/attributions#basemaps">CartoDB</a>'
                              )

        # the colormap
        if kind == "linear":
            custom_cm = cm.LinearColormap(['green', 'yellow', 'red'], vmin=min_value, vmax=max_value)
        elif kind == "outlier":
            # for outliers, values would be -11,0,1
            custom_cm = cm.LinearColormap(['blue', 'white', 'red'], vmin=min_value, vmax=max_value)
        elif kind == "filled_nulls":
            custom_cm = cm.LinearColormap(['sienna', 'green', 'yellow', 'red'],
                                          index=[0, min_value, m, max_value], vmin=min_value, vmax=max_value)

        # create geojson data from dataframe
        geojson_data = hexagons_dataframe_to_geojson(df, value)

        GeoJson(
            geojson_data,
            style_function=lambda feature: {
                'fillColor': custom_cm(feature['properties'][value]),
                'color': border_color,
                'weight': 1,
                'fillOpacity': fill_opacity
            }
        ).add_to(initial_map)

        # add legend (not recommended if multiple layers)
        if with_legend:
            custom_cm.add_to(initial_map)


        return initial_map


def hexagons_dataframe_to_geojson(df, value):
    list_features = []

    for i, row in df.iterrows():
        feature = Feature(geometry=row["geometry"], id=row["hex_id"], properties={value: row[value]})
        list_features.append(feature)

    feat_collection = FeatureCollection(list_features)

    geojson_result = json.dumps(feat_collection)

    return geojson_result