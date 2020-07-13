# Regular Imports
import pandas as pd
import geopandas as gpd
from fiona.crs import from_epsg
from datetime import timedelta
from h3 import h3
from geojson.feature import *
from folium import Map, Marker, GeoJson
import branca.colormap as cm
import json


class Vehicle:
    """
    A class to represent a vehicle in EV charging simulation

    Attributes
    ----------
    identifier : string
        Unique vehicle identifier
    trajectory : movingpandas object
        The movingpandas trajectory object describing the vehicles movement
    range : int
        Range in miles of vehicle on full battery
    state_of_charge : int
        Simulated battery state of charge of vehicle
    odometer_reading : float
        Reading of odometer at current vehicle state
    time : Datetime
        Current time of vehicle state
    gps : list
        List of GPS [Lat, Lon] for current vehicle state
    charge_events : list
        List of gps lists representing simulated charging events
    max_odo : float
        Maximum odometer reading in the trajectory
    battery_capacity : int
        55 kWh for Bolt EV
   """

    def __init__(self, trajectory):
        self.identifier = trajectory.df.hashed_vin.iloc[0]
        self.trajectory = trajectory
        self.range = 259
        self.state_of_charge = 100
        self.odometer_reading = trajectory.df.odo_read.min()
        self.time = pd.to_datetime(trajectory.df.element_time_local).min()
        self.gps = [trajectory.df.decr_lat[0], trajectory.df.decr_lng[0]]
        self.charge_events = []
        self.max_odo = trajectory.df.odo_read.max()
        self.battery_capacity = 55

    def __repr__(self):
        representation = (
            f"State of Charge: {self.state_of_charge} \n"
            f"Odometer Reading: {self.odometer_reading} \n"
            f"Time: {self.time} \n"
            f"GPS: {self.gps} \n"
        )
        return representation

    def drive(self, miles):
        """
        Moves the vehicle forward the input number of miles and alters vehicle state

        Parameters
        ----------
        self: object
            Python Class Object

        miles : float
            Number of miles to move the vehicle forward
        """

        # Increase odometer and decrease SOC accordingly
        self.odometer_reading += miles
        self.state_of_charge -= (100 * (miles / self.range))

        # Look for the closest odometer reading in the trajectory data
        self.trajectory.df['odo_diff'] = abs(self.trajectory.df['odo_read'] - self.odometer_reading)
        closest_ping = self.trajectory.df[self.trajectory.df['odo_diff'] == self.trajectory.df['odo_diff'].min()]

        # Set time and gps to that in the trajectory data
        self.time = pd.to_datetime(closest_ping.element_time_local.iloc[0])

        self.gps = [closest_ping.decr_lng[0], closest_ping.decr_lat[0]]

    def charge(self, energy):
        # derive delta_soc from energy
        delta_soc = (energy / self.battery_capacity) * 100

        # create a charging event
        charging_event = ChargingEvent(self.gps, self.time, delta_soc, self.state_of_charge, energy)

        # Increase the state_of_charge by delta_soc
        self.state_of_charge += delta_soc

        # Append the ChargingEvent to the charge_events list
        self.charge_events.append(charging_event)


class Simulation:
    """
    The simulation object could have a function call run
    In run, the model is trained and then passed to each vehicle object
    For that vehicle to use the prediction in its simulation

    Parameters
    ____________

    prediction_model : scikit-learn linear_model
        The trained delta_soc prediction model
    ev_charging_events : pandas dataframe
        The EV charging event data set used for random sampling and prediction
    vehicles : list
        List of vehicle objects for prediction of charging

    """

    def __init__(self, vehicles, charge_location_model, charge_amount_model):
        self.charge_location_model = charge_location_model
        self.charge_amount_model = charge_amount_model
        self.vehicles = vehicles

    def predict_charge_location(self, vehicle):
        miles_to_next_charge = self.charge_location_model.run(vehicle)
        return miles_to_next_charge

    def predict_charge_amount(self, vehicle):
        energy = self.charge_amount_model.run(vehicle)
        return energy

    def run(self):

        # For each vehicle in the simulation set
        for vehicle in self.vehicles:

            # Randomly sample start_soc and calculate miles to next charge
            miles_to_next_charge = self.predict_charge_location(vehicle)

            # While the vehicle is not at its maximum odometer reading
            while (vehicle.odometer_reading + miles_to_next_charge) <= vehicle.max_odo:
                # Drive to next charge
                vehicle.drive(miles_to_next_charge)

                # Predict the energy of charging
                energy = self.predict_charge_amount(vehicle)

                # Charge the vehicle
                vehicle.charge(energy)

                # Recalculate next charging event
                miles_to_next_charge = self.predict_charge_location(vehicle)


class ChargingEvent:
    """
    Class which defines a charging event

    Attributes
    ----------
    gps : list
        [Lat, Lon] in EPSG:4326
    time : Datetime
        Datetime Object
    delta_soc : int
        Change in SOC of charging event
    start_soc : int
        Starting state of charge
    energy : int
        Energy of charging event given battery size
    """

    def __init__(self, gps, time, delta_soc, start_soc, energy):
        self.gps = gps
        self.start_time = time
        self.delta_soc = delta_soc
        self.start_soc = start_soc
        self.energy = energy
        self.duration = timedelta(hours=(((delta_soc / 100) * 55) / 50))
        self.end_time = self.start_time + self.duration

    def __repr__(self):
        representation = (
            f"GPS: {self.gps} \n"
            f"Start Time: {self.start_time} \n"
            f"End Time: {self.end_time} \n"
            f"Delta SOC: {self.delta_soc} \n"
            f"Start SOC: {self.start_soc} \n"
            f"Energy: {self.energy} \n"
        )
        return representation


class ChargingEvents:
    """
    Class which defines all charging events and provides methods for visualization

    Attributes
    ----------
    event_list : list
        List of ChargingEvent Objects as defined above
    """

    def __init__(self, event_list):
        self.event_list = event_list

    def to_geopandas(self):
        """
        Convert the ChargingEvents Object to a pandas dataframe of charging events

        Parameters
        ----------
        self: object
            Python Class Object

        Returns
        ----------
        df : geo pandas dataframe
            GeoPandas dataframe of charging events
        """
        df = gpd.GeoDataFrame()
        for charging_events in self.event_list:

            # iterate through the list and add
            for event in charging_events:
                latitude, longitude = event.gps[0], event.gps[1]
                event_df = pd.DataFrame([[latitude, longitude, event.delta_soc, event.energy, event.start_soc,
                                          event.start_time, event.end_time]],
                                        columns=['latitude', 'longitude', 'delta_soc', 'energy', 'start_soc',
                                                 'start_time', 'end_time'])

                df = df.append(
                    gpd.GeoDataFrame(event_df, geometry=gpd.points_from_xy(event_df.latitude, event_df.longitude),
                                     crs=from_epsg(4326)))
        return df

    def to_hourly(self):

        # Create charges_gdf
        charge_events_gdf = self.to_geopandas()

        # Create unique identifier
        charge_events_gdf['ID'] = [i for i in range(0, charge_events_gdf.shape[0])]

        # Create dataframe by minutes in this datetime range
        start = charge_events_gdf['start_time'].min()
        end = charge_events_gdf['end_time'].max()
        index = pd.date_range(start=start, end=end, freq='1T')
        df2 = pd.DataFrame(index=index, columns= \
            ['minutes', 'ID', 'latitude', 'longitude', 'delta_soc', 'energy', 'start_soc'])

        # Spread the events across minutes
        for index, row in charge_events_gdf.iterrows():
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
        df5 = df4.drop(columns=['minutes', 'minutes_sum', 'hour']).sort_values(by='ID')

        return df5


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

    def plot(self, value='energy', border_color='black', fill_opacity=0.7, initial_map=None, with_legend=False,
             kind="linear"):

        df = self.charges.copy()
        df = df.groupby('hex_id').agg({value: 'mean', 'geometry': 'first'}).reset_index()

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
        # color names accepted https://github.com/python-visualization/branca/blob/master/branca/_cnames.json
        if kind == "linear":
            custom_cm = cm.LinearColormap(['green', 'yellow', 'red'], vmin=min_value, vmax=max_value)
        elif kind == "outlier":
            # for outliers, values would be -11,0,1
            custom_cm = cm.LinearColormap(['blue', 'white', 'red'], vmin=min_value, vmax=max_value)
        elif kind == "filled_nulls":
            custom_cm = cm.LinearColormap(['sienna', 'green', 'yellow', 'red'],
                                          index=[0, min_value, m, max_value], vmin=min_value, vmax=max_value)

        # create geojson data from dataframe
        geojson_data = self.hexagons_dataframe_to_geojson(df_hex=df, value=value)

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
        if with_legend == True:
            custom_cm.add_to(initial_map)

        return initial_map

    def hexagons_dataframe_to_geojson(df_hex, value, file_output=None):

        list_features = []

        for i, row in df_hex.iterrows():
            feature = Feature(geometry=row["geometry"], id=row["hex_id"], properties={value: row[value]})
            list_features.append(feature)

        feat_collection = FeatureCollection(list_features)

        geojson_result = json.dumps(feat_collection)

        # optionally write to file
        if file_output is not None:
            with open(file_output, "w") as f:
                json.dump(feat_collection, f)

        return geojson_result
