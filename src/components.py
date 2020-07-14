import pandas as pd
import geopandas as gpd
from fiona.crs import from_epsg
from datetime import timedelta
from geojson.feature import *


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
        df5 = df4.drop(columns=['minutes', 'minutes_sum']).sort_values(by='ID')

        return df5