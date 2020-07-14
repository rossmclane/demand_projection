# Regular Imports
from fiona.crs import from_epsg
from geojson.feature import *
import pandas as pd
from src.grid import HexGrid
import multiprocessing as mp
import geopandas as gpd


class VehicleSimulation:
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

    def __init__(self, charge_location_model, charge_amount_model):
        self.charge_location_model = charge_location_model
        self.charge_amount_model = charge_amount_model
        self.ev_charging_events = pd.DataFrame()

    def predict_charge_location(self, vehicle):
        miles_to_next_charge = self.charge_location_model.run(vehicle)
        return miles_to_next_charge

    def predict_charge_amount(self, vehicle):
        energy = self.charge_amount_model.run(vehicle)
        return energy

    def run(self, vehicle):
        # While the vehicle is not at its maximum odometer reading
        while vehicle.odometer_reading < vehicle.max_odo:
            # Run charge location model and move vehicle forwards
            miles_to_next_charge = self.predict_charge_location(vehicle)
            vehicle.drive(miles_to_next_charge)

            # Run charge amount model and move vehicle forwards
            energy = self.predict_charge_amount(vehicle)
            vehicle.charge(energy)

            self.ev_charging_events = self.ev_charging_events.append(
                gpd.GeoDataFrame(vehicle.charge_events, geometry=gpd.points_from_xy(vehicle.charge_events.latitude,
                                                                                    vehicle.charge_events.longitude),
                                 crs=from_epsg(4326)))


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
        self.charging_events = pd.DataFrame()
        self.hourly_charging_events = pd.DataFrame()
        self.hex_joined_hourly_charges = None

    def run_parallel(self):

        # Create a pool
        pool = mp.Pool(mp.cpu_count())

        def testsim(vehicle):
            vsim = VehicleSimulation(self.charge_location_model, self.charge_amount_model)
            vsim.run(vehicle)
            self.charging_events = self.charging_events.append(vsim.ev_charging_events)

        for vehicle in self.vehicles:
            pool.apply_async(testsim, args=(vehicle,))

        pool.close()
        pool.join()

    def run(self):

        # Run the simulation for each vehicle
        for vehicle in self.vehicles:
            # Run the simulation on the vehicles
            vsim = VehicleSimulation(self.charge_location_model, self.charge_amount_model)
            vsim.run(vehicle)
            self.charging_events = self.charging_events.append(vsim.ev_charging_events)

        # Generate hourly charges and save the result for the LP
        self.generate_hourly_charging_events()

        # Create a grid of resolution
        grid = HexGrid(resolution=8)

        # Join the data frame with the grid
        hex_joined_hourly_charges = grid.hourly_sjoin(self.hourly_charging_events)
        self.hex_joined_hourly_charges = hex_joined_hourly_charges

        self.save_result()

    def generate_hourly_charging_events(self):
        # Create unique identifier
        charge_events_gdf = self.charging_events.copy()

        charge_events_gdf['ID'] = [i for i in range(0, charge_events_gdf.shape[0])]

        # Create dataframe by minutes in this datetime range
        start = charge_events_gdf['start_time'].min()
        end = charge_events_gdf['end_time'].max()
        index = pd.date_range(start=start, end=end, freq='1T')
        df2 = pd.DataFrame(index=index, columns= \
            ['minutes', 'ID', 'latitude', 'longitude', 'delta_soc', 'energy', 'state_of_charge'])

        # Spread the events across minutes
        for index, row in charge_events_gdf.iterrows():
            df2['minutes'][row['start_time']:row['end_time']] = 1
            df2['ID'][row['start_time']:row['end_time']] = row['ID']
            df2['latitude'][row['start_time']:row['end_time']] = row['latitude']
            df2['longitude'][row['start_time']:row['end_time']] = row['longitude']
            df2['delta_soc'][row['start_time']:row['end_time']] = row['delta_soc']
            df2['energy'][row['start_time']:row['end_time']] = row['energy']
            df2['state_of_charge'][row['start_time']:row['end_time']] = row['state_of_charge']

        # Clean up dataframe
        df2 = df2[df2.ID.notna()]
        df2['time'] = df2.index
        df2['hour'] = df2['time'].apply(lambda x: x.hour)

        # GroupBy ID and hour
        df3 = df2.groupby(['ID', 'hour']).agg(
            {'minutes': 'count', 'time': 'first', 'latitude': 'first', 'longitude': 'first', 'delta_soc': 'first',
             'energy': 'first', 'state_of_charge': 'first'}).reset_index()

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

        self.hourly_charging_events = df5

    def map(self, resolution=8, value='energy', hour=12):
        # Create a grid of resolution
        grid = HexGrid(resolution)

        # Join the data frame with the grid
        grid.hourly_sjoin(self.hourly_charging_events)

        # Plot the energy values
        hexmap = grid.plot(value=value, hour=hour)

        # Save for the different hours!!
        return hexmap

    def save_result(self):
        lp_input = self.hex_joined_hourly_charges.groupby('hex_id').agg({'hour': 'first', 'energy': 'sum'}).reset_index()
        lp_input = lp_input.sort_values(by='hour')
        lp_input = lp_input.rename(columns={'hex_id': 'B', 'hour': 'T', 'energy': 'A'})
        lp_input.to_csv('../data/interim/lp_data/input_data/demand_model_output.csv', index=False)