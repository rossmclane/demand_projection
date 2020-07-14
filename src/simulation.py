# Regular Imports
from geojson.feature import *


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
        self.results = {}

    def predict_charge_location(self, vehicle):
        miles_to_next_charge = self.charge_location_model.run(vehicle)
        return miles_to_next_charge

    def predict_charge_amount(self, vehicle):
        energy = self.charge_amount_model.run(vehicle)
        return energy

    def compile_charging_events(self):
        events_list = []

        for v in self.vehicles:
            if v.charge_events:
                events_list.append(v.charge_events)

        charge_events = ChargingEvents(events_list)

        self.results['charging_events'] = charge_events.to_geopandas()
        self.results['hourly_charging_events'] = charge_events.to_hourly()

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

        self.compile_charging_events()

    def map(self, resolution=8, value='energy', hour=12):
        # Create a grid of resolution
        grid = HexGrid(resolution)

        # Join the data frame with the grid
        grid.hourly_sjoin(self.results['hourly_charging_events'])

        # Plot the energy values
        hexmap = grid.plot(value=value, hour=hour)

        # Save for the different hours!!
        return hexmap