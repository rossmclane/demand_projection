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
        self.latitude = trajectory.df.decr_lat[0]
        self.longitude = trajectory.df.decr_lng[0]
        self.charge_events = pd.DataFrame(columns=['latitude', 'longitude', 'start_time', 'end_time', 'delta_soc', 'state_of_charge', 'energy'])
        self.max_odo = trajectory.df.odo_read.max()
        self.battery_capacity = 55

    def __repr__(self):
        representation = (
            f"State of Charge: {self.state_of_charge} \n"
            f"Odometer Reading: {self.odometer_reading} \n"
            f"Time: {self.time} \n"
            f"GPS: {self.latitude, self.longitude} \n"
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

        # Set longitude and latitude
        self.latitude = closest_ping.decr_lat[0]
        self.longitude = closest_ping.decr_lng[0]

    def charge(self, energy):
        # derive delta_soc from energy
        delta_soc = (energy / self.battery_capacity) * 100
        duration = timedelta(hours=(((delta_soc / 100) * 55) / 50))
        start_time = self.time
        end_time = start_time + duration

        # Instead of creating a charging event class, just create a dataframe
        charge_event = pd.DataFrame([[self.latitude, self.longitude, start_time, end_time, delta_soc, self.state_of_charge, energy]],\
                                    columns=['latitude', 'longitude', 'start_time', 'end_time', 'delta_soc', 'state_of_charge', 'energy'])
        self.charge_events = self.charge_events.append(charge_event)

        # Increase the state_of_charge by delta_soc
        self.state_of_charge += delta_soc