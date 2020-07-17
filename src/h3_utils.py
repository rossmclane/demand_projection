from h3 import h3
import json
import pandas as pd
from geojson.feature import *
from folium import Map, Marker, GeoJson
from geojson.feature import *
import branca.colormap as cm
import geopandas as gpd
from shapely.geometry import Polygon


def bin_by_hexagon(df: pd.DataFrame, groupby_items: list, agg_map: dict, resolution: int):
    """
    Use h3.geo_to_h3 to join each point into the spatial index of the hex at the specified resolution.
    Use h3.h3_to_geo_boundary to obtain the geometries of these hexagons.
    adopted from: Uber https://github.com/uber/h3-py-notebooks/blob/master/notebooks/urban_analytics.ipynb

    parameters
    ---------
    df:pd.DataFrame - dataframe with points to be binned, including columns ['latitude'.'longitude']
    groupby_items:list - list of column names to group by. ex. ['hex_id','hour','weekday']
    agg_map:dict - dict where keys=columns to be included in groupby and values=aggrigate function
            ex. {'station_id':'count','energy':'sum'}
    resolution:int - H3 cell resolution size

    returns
    ---------
    df:pd.DataFrame - dataframe of resulting groupby function

    """

    # Assign hex_ids
    df["hex_id"] = df.apply(lambda row: h3.geo_to_h3(row["latitude"], row["longitude"], resolution), axis=1)

    # Groupby and aggregate
    df_aggreg = df.groupby(groupby_items).agg(agg_map)
    df_aggreg.reset_index(inplace=True)

    # Create geojson column
    df_aggreg["geojson"] = df_aggreg.hex_id.apply(lambda x:
                                                  {"type": "Polygon",
                                                   "coordinates":
                                                       [h3.h3_to_geo_boundary(h=x, geo_json=True)]
                                                   }
                                                  )

    return df_aggreg


def hexagons_dataframe_to_geojson(df_hex, file_output=None):
    """
    Produce the GeoJSON for a dataframe that has a geometry column in geojson format ,
    along with the other columns to include such as hex_id, station_ids, station_count, etc
    adopted from: Uber https://github.com/uber/h3-py-notebooks/blob/master/notebooks/urban_analytics.ipynb

    """

    list_features = []

    for i, row in df_hex.iterrows():
        feature = Feature(geometry=row["geometry"], id=row["hex_id"],
                          properties={
                              col: row[col] for col in df_hex.columns.drop('geometry', 'hex_id')
                          }
                          )

        list_features.append(feature)

    feat_collection = FeatureCollection(list_features)

    geojson_result = json.dumps(feat_collection)

    # optionally write to file
    if file_output is not None:
        with open(file_output, "w") as f:
            json.dump(feat_collection, f)

    return geojson_result


def h3_choropleth_map(df_aggreg: pd.DataFrame, value_to_map: str, kind: str, hour: int, border_color='black', fill_opacity=0.7,
                      initial_map=None, map_center=[34.0522, -118.2437], with_legend=True):
    """
    Builds a folium choropleth map from an df containing H3 hex cells and some cell value such as 'count'.
    parameters
    ----------
    df_aggreg:pd.DataFrame - df with H3 hex cells in col ['hex_id'] and at least one col ['value_to_map'] for cell color.
    value_to_map:str - column name in df to scale and color cells by
    returns
    ----------
    initial_map:folium.Map
    """
    # take resolution from the first row
    res = h3.h3_get_resolution(df_aggreg.loc[0, 'hex_id'])

    if hour is not None:
        df_aggreg = df_aggreg[df_aggreg.hour == hour]
    else:
        df_aggreg = df_aggreg.groupby(['hex_id']).agg({value_to_map: 'sum', 'geometry': 'first', 'hex_id': 'first'})

    # create geojson data from dataframe
    geojson_data = hexagons_dataframe_to_geojson(df_hex=df_aggreg)

    if initial_map is None:
        initial_map = Map(location=[34.0522, -118.2437], zoom_start=11, tiles="cartodbpositron",
                          attr='© <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="http://cartodb.com/attributions#basemaps">CartoDB</a>'
                          )

    if value_to_map:
        # colormap
        min_value = df_aggreg[value_to_map].min()
        max_value = df_aggreg[value_to_map].max()
        m = round((min_value + max_value) / 2, 0)

        # color names accepted https://github.com/python-visualization/branca/blob/master/branca/_cnames.json
        if kind == "linear":
            custom_cm = cm.LinearColormap(['green', 'yellow', 'red'], vmin=min_value, vmax=max_value)
        elif kind == "outlier":
            # for outliers, values would be -11,0,1
            custom_cm = cm.LinearColormap(['blue', 'white', 'red'], vmin=min_value, vmax=max_value)
        elif kind == "filled_nulls":
            custom_cm = cm.LinearColormap(['sienna', 'green', 'yellow', 'red'],
                                          index=[0, min_value, m, max_value], vmin=min_value, vmax=max_value)

        # plot on map
        name_layer = "Choropleth " + str(res)
        if kind != "linear":
            name_layer = name_layer + kind

        GeoJson(
            geojson_data,
            style_function=lambda feature: {
                'fillColor': custom_cm(feature['properties'][value_to_map]),
                'color': border_color,
                'weight': 1,
                'fillOpacity': fill_opacity
            },
            name=name_layer
        ).add_to(initial_map)

        # add legend (not recommended if multiple layers)
        if with_legend == True:
            custom_cm.add_to(initial_map)

    else:
        # plot on map
        name_layer = "Choropleth " + str(res)
        if kind != "linear":
            name_layer = name_layer + kind

        GeoJson(
            geojson_data,
            style_function=lambda feature: {
                'fillColor': 'blue',
                'color': 'border_color',
                'weight': 1,
                'fillOpacity': fill_opacity
            },
            name=name_layer
        ).add_to(initial_map)

    return initial_map


def reverse_lat_lon(hex_coords):
    geom_hex = []
    for lat_lon in hex_coords:
        geom_hex.append([lat_lon[1], lat_lon[0]])

    return geom_hex


def fill_shapefile_hexes(geojson: json, resolution: int):
    """
    Fill a shapefile with hexes of a particular h3 resolution.
    parameters
    ----------
    geojson:json - json with structure like:
    resolution:ind - h3 resolution
    returns
    ----------
    hex_df:gpd.GeoDataFrame() - geo dataframe with hex_id and geometry
    """

    # Generates hex_ids of filled polygon
    set_hexagons = h3.polyfill(geojson=geojson, res=resolution, geo_json_conformant=True)

    # Generate list of polygons
    list_hexagons = list(set_hexagons)

    # Reverse the latitude and longitude
    one_hex_of_fill = list_hexagons[0]
    one_hex_of_fill_coords_latlon = h3.h3_to_geo_boundary(h=one_hex_of_fill, geo_json=False)
    one_hex_of_fill_coords_lonlat = reverse_lat_lon(hex_coords=one_hex_of_fill_coords_latlon)

    # Create hex_id df, fill values with zero and assign the geometries
    df_fill_hex = pd.DataFrame({"hex_id": list_hexagons})
    df_fill_hex["value"] = 0
    df_fill_hex['geojson'] = df_fill_hex.hex_id.apply(lambda x:
                                                      {"type": "Polygon",
                                                       "coordinates":
                                                           [reverse_lat_lon(h3.h3_to_geo_boundary(h=x, geo_json=False))]
                                                       }
                                                      )

    # Fill the geometries and write out the final dataframe
    df_fill_hex['geometry'] = df_fill_hex['geojson'].apply(lambda x: Polygon(x['coordinates'][0]))
    df_fill_hex = gpd.GeoDataFrame(df_fill_hex, crs="EPSG:4326")
    return df_fill_hex