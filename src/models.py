import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from geojson.feature import *


class Random_Sample_Charge_Location_Model:

    def __init__(self):
        self.ev_charging_events = pd.read_csv('../data/raw/charges_derived_joined_charger.csv')

    def run(self, vehicle):

        # Calculate start_soc probabilities
        self.ev_charging_events['start_soc_prob'] = self.ev_charging_events.start_soc / self.ev_charging_events.start_soc.sum()

        # Randomly sample from that distribution
        start_soc = np.random.choice(self.ev_charging_events.start_soc, 1,
                                     p=list(self.ev_charging_events['start_soc_prob']).reverse())[0]

        # The number of miles needed to get to the next charge
        miles_to_next_charge = ((100 - start_soc) / 100) * vehicle.range

        # The number of miles on the vehicle
        miles_on_vehicle = vehicle.range * (vehicle.state_of_charge / 100)

        while miles_to_next_charge > miles_on_vehicle:
            miles_to_next_charge = self.run(vehicle)

        return miles_to_next_charge


class Linear_Kwh_Model:

    def __init__(self):
        self.ev_charging_events = pd.read_csv('../data/raw/charges_derived_joined_charger.csv')
        self.model = None

    def train(self):
        x, y = np.array(self.ev_charging_events.start_soc).reshape((-1, 1)), np.array(
            self.ev_charging_events.delta_soc).reshape((-1, 1))

        # Split features to train/test on
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.33, random_state=42)

        # Create linear model
        model = LinearRegression()

        # Train the model using the training sets
        model.fit(x_train, y_train)

        self.model = model

    def run(self, vehicle):

        # Predict Delta_SOC

        delta_soc_predicted = self.model.predict(np.array(vehicle.state_of_charge).reshape(-1, 1))

        # If the Delta_SOC predicted is too much for the empty battery capacity, re-predict
        while delta_soc_predicted >= (100 - vehicle.state_of_charge):
            print('SOC capacity needed is lower than predicted delta SOC (EXPLORE MORE)')
            delta_soc_predicted = self.model.predict(np.array(vehicle.state_of_charge).reshape(-1, 1))

        # kwh prediction
        energy = (delta_soc_predicted[0][0] / 100) * vehicle.battery_capacity

        return energy