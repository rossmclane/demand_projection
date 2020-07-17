# Regular Imports
from fiona.crs import from_epsg
from geojson.feature import *
import pandas as pd
from src.grid import HexGrid
import geopandas as gpd
from src.general_utils import generate_hourly_charges


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
        self.charging_events = pd.DataFrame()

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

            # Add charging event to charging events
            self.charging_events = self.charging_events.append(
                gpd.GeoDataFrame(vehicle.charging_events, geometry=gpd.points_from_xy(vehicle.charging_events.latitude,
                                                                                      vehicle.charging_events.longitude),
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
        self.grid = None

    def run(self):

        all_charging_events = pd.DataFrame()

        # Run the simulation for each vehicle
        for vehicle in self.vehicles:
            # Create a vehicle simulation and run it
            vehicle_sim = VehicleSimulation(self.charge_location_model, self.charge_amount_model)
            vehicle_sim.run(vehicle)

            # Append charging events to class attribute
            all_charging_events = all_charging_events.append(vehicle_sim.charging_events)

        # Generate hourly charges and save the result for the LP
        self.charging_events = generate_hourly_charges(all_charging_events)

        # Create a grid object, join results to the grid, and save the grid
        grid = HexGrid(resolution=8)
        grid.join(self.charging_events, groupby_items=['hex_id', 'hour'], agg_map={'energy': 'sum'}, resolution=8)
        self.grid = grid

        # Save the result
        self.save_result()

    def map(self, hour=None):

        # generate plot
        hexmap = self.grid.plot(value_to_map='energy', kind="linear", hour=hour)

        return hexmap

    def save_result(self):
        # Retrieve hexbinned results, sort by hour and drop geometry

        lp_input = self.grid.hex_data.sort_values(by='hour')

        # Rename output for linear program
        lp_input = lp_input.rename(columns={'hex_id': 'B', 'hour': 'T', 'energy': 'A'})

        # Write out the model output
        lp_input.to_csv('../data/interim/lp_data/input_data/Demand_Model_Output.csv', index=False)
