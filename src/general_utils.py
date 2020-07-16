# Regular Imports
from geojson.feature import *
from src.h3_utils import *
import geopandas as gpd
import pandas as pd

def generate_hourly_charges(charges):
    # Create a unique identifier
    charges['ID'] = [i for i in range(0, charges.shape[0])]

    # Create dataframe by minutes in this datetime range
    start = charges['start_time'].min()
    end = charges['end_time'].max()
    index = pd.date_range(start=start, end=end, freq='1T')
    df2 = pd.DataFrame(index=index, columns= \
        ['minutes', 'ID', 'latitude', 'longitude', 'delta_soc', 'energy', 'start_soc'])

    # Spread the events across minutes
    for index, row in charges.iterrows():
        df2['minutes'][row['start_time']:row['end_time']] = 1
        df2['ID'][row['start_time']:row['end_time']] = row['ID']
        df2['latitude'][row['start_time']:row['end_time']] = row['latitude']
        df2['longitude'][row['start_time']:row['end_time']] = row['longitude']
        df2['delta_soc'][row['start_time']:row['end_time']] = row['delta_soc']
        df2['energy'][row['start_time']:row['end_time']] = row['energy']
        df2['start_soc'][row['start_time']:row['end_time']] = row['start_soc']

    # Clean up dataframe
    df2 = df2[df2.ID.notna()]
    df2['time'] = df2.index
    df2['hour'] = df2['time'].apply(lambda x: x.hour)

    # GroupBy ID and hour
    df3 = df2.groupby(['ID', 'hour']).agg(
        {'minutes': 'count', 'time': 'first', 'latitude': 'first', 'longitude': 'first', 'delta_soc': 'first',
         'energy': 'first', 'start_soc': 'first'}).reset_index()

    # Recreate time index
    df3['time'] = df3['time'].apply(lambda x: pd.datetime(year=x.year, month=x.month, day=x.day, hour=x.hour))
    df3.set_index('time', inplace=True)
    df3['time'] = df3.index

    # Spread energy and delta_soc
    sums = df3.groupby('ID').agg({'minutes': 'sum'}).rename(columns={'minutes': 'minutes_sum'})
    df4 = pd.merge(df3, sums, on='ID')
    df4.set_index('time', inplace=True)
    df4['delta_soc'] = df4['delta_soc'] * (df4['minutes'] / df4['minutes_sum'])
    df4['energy'] = df4['energy'] * (df4['minutes'] / df4['minutes_sum'])
    df5 = df4.drop(columns=['minutes', 'minutes_sum']).sort_values(by='ID')

    return df5


def generate_hexgrid(by_hour):

    # import la_shapefile
    la_shp = gpd.read_file('../data/raw/la_dissolved.shp')

    # remove extraneous multipolygon data structure
    la_shp['geometry'] = la_shp.geometry[0][1]

    # create geojson
    la_json = gpd.GeoSeries(la_shp['geometry']).__geo_interface__['features'][0]['geometry']

    # create hexes, put into df:
    la_hexes = fill_shapefile_hexes(geojson=la_json, resolution=8)

    # Add an hour component to the hexagonal grid

    if by_hour:
        la_hexes_with_hour = []
        for i in range(25):
            la_hexes_copy = la_hexes.copy()
            la_hexes_copy['hour'] = i
            la_hexes_with_hour.append(la_hexes_copy)

        la_hexes_with_hour = pd.concat(la_hexes_with_hour)
        return la_hexes_with_hour

    else:
        return la_hexes