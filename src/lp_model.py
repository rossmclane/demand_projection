from __future__ import division
from pyomo.environ import *
import numpy as np
import pandas as pd
from folium import Map, CircleMarker, FeatureGroup, LayerControl
import os.path


class linear_program:

    def construct_inputs(self):

        # Construct the files needed for input from the demand output file
        # Read in demand input
        # Load Sets
        # Create each file
            # Calculate Travel Times from google_api and Calculate Penalty Matrix
        #

    def load(self):

        # Create a model
        model = AbstractModel()

        # Import sets
        set_df = pd.read_csv('../data/interim/lp_data/input_data/Set_List.csv')
        node_list = list(set_df['B'])[:95]
        charger_list = list(set_df['K'])[:2]

        # 72 because three representative days
        time_list = list(set_df['T'])[:72]

        #
        line_list = list(set_df['L'])[:772]

        # Create pyomo sets
        model.B = Set(initialize=node_list)
        model.K = Set(initialize=charger_list)
        model.T = Set(initialize=time_list)
        model.L = Set(initialize=line_list)

        # Create Model Parameters
        model.F = Param(model.B, model.K)
        model.D = Param(model.B, model.K)
        model.p = Param(model.B, model.L)
        model.A = Param(model.B, model.T)
        model.G = Param(model.T)
        model.C = Param(model.B, model.K)
        model.N = Param(model.K)
        model.E = Param(model.B, model.K)
        model.S = Param(model.B)
        model.M = Param(initialize=100)
        model.VW = Param(model.B, model.K, model.T)
        model.P_H_U = Param(model.L, model.T)

        # Load data into model parameters
        data = DataPortal()
        data.load(filename='../data/interim/lp_data/input_data/Fixed_Cost.csv', param=model.F, index=(model.B, model.K))
        data.load(filename='../data/interim/lp_data/input_data/Demand_Charge.csv', param=model.D,
                  index=(model.B, model.K))
        data.load(filename='../data/interim/lp_data/input_data/Incidence_Matrix.tab', param=model.p, format='array')
        data.load(filename='../data/interim/lp_data/input_data/Demand.csv', param=model.A, index=(model.B, model.T))
        data.load(filename='../data/interim/lp_data/input_data/Charging_Efficiency.csv', param=model.G, index=(model.T))
        data.load(filename='../data/interim/lp_data/input_data/Plug_in_Limit.csv', param=model.C,
                  index=(model.B, model.K))
        data.load(filename='../data/interim/lp_data/input_data/Charger_Capacity.csv', param=model.N, index=(model.K))
        data.load(filename='../data/interim/lp_data/input_data/Existing_Capacity.csv', param=model.E,
                  index=(model.B, model.K))
        data.load(filename='../data/interim/lp_data/input_data/Site_Develop_Cost.csv', param=model.S, index=(model.B))
        data.load(filename='../data/interim/lp_data/input_data/V_Times_W.csv', param=model.VW,
                  index=(model.B, model.K, model.T))
        data.load(filename='../data/interim/lp_data/input_data/P_H_U.csv', param=model.P_H_U, index=(model.L, model.T))

        # Create Decision Variables
        model.x = Var(model.B, model.K, within=NonNegativeReals)
        model.n = Var(model.B, model.K, within=NonNegativeIntegers)
        model.y = Var(model.B, model.K, model.T, within=NonNegativeReals)
        model.f = Var(model.L, model.T, within=NonNegativeReals)
        model.v = Var(model.B, within=Binary)

        # Objective Function
        def obj_expression(model):
            return summation(model.S, model.v) + \
                   summation(model.F, model.x) + \
                   summation(model.D, model.x) + \
                   summation(model.VW, model.y) + \
                   summation(model.P_H_U, model.f)

        model.OBJ = Objective(rule=obj_expression, sense=minimize)

        # Constraint One
        def first_constraint_rule(model, b, t):
            return (sum(model.y[b, k, t] for k in model.K) + sum(model.p[b, l] * model.f[l, t] for l in model.L)) \
                   >= (model.A[b, t])

        model.FirstConstraint = Constraint(model.B, model.T, rule=first_constraint_rule)

        # Constraint Two
        def second_constraint_rule(model, b, k, t):
            return (model.y[b, k, t] <= (model.x[b, k] + model.E[b, k]) * model.G[t])

        model.SecondConstraint = Constraint(model.B, model.K, model.T, rule=second_constraint_rule)

        # Create model instance
        instance = model.create_instance(data)

        return instance

    def run(self):
        instance = self.load()

        # Create and solve the LP
        solver = pyomo.opt.SolverFactory('glpk')
        solver.solve(instance, tee=True, keepfiles=True)

        # Save the instance results
        self.save(instance)

    def save(self, instance):

        # Write out results
        ind_x = list(instance.x)
        val_x = list(instance.x[:, :].value)

        ind_v = list(instance.v)
        val_v = list(instance.v[:].value)

        ind_y = list(instance.y)
        val_y = list(instance.y[:, :, :].value)

        ind_f = list(instance.f)
        val_f = list(instance.f[:, :].value)

        result_x = [i + tuple([j]) for i, j in zip(ind_x, val_x)]
        result_v = [i for i in zip(ind_v, val_v)]
        result_y = [i + tuple([j]) for i, j in zip(ind_y, val_y)]
        result_f = [i + tuple([j]) for i, j in zip(ind_f, val_f)]

        pd.DataFrame(np.array(result_x)).to_csv('../data/processed/lp_data/output_data/x.csv', index=False)
        pd.DataFrame(np.array(result_v)).to_csv('../data/processed/lp_data/output_data/v.csv', index=False)
        pd.DataFrame(np.array(result_y)).to_csv('../data/processed/lp_data/output_data/y.csv', index=False)
        pd.DataFrame(np.array(result_f)).to_csv('../data/processed/lp_data/output_data/f.csv', index=False)

    def show(self):

       # Function should take the LP output, join with h3 hexagons to get geometries
       # And plot the proposed charging stations
       # Could add functionality for overlap with

        def map_multiple_outputs_points(directory: str, map_center=None, save_path=None):
            """
            Creates a folium map of single or multiple outputs from the LP model. Circle markers communicate both location of
            station and forecast demand (diameter).
            Good for outputs from LP model that outputs points - not hexes.
            """
            station_locations = open_station_locations()
            if not map_center:
                m_lat = station_locations[:1]['latitude']
                m_long = station_locations[:1]['longitude']

            else:
                m_lat = map_center[0]
                m_long = map_center[1]

            m = Map(
                location=[m_lat, m_long],
                tiles='cartodbpositron',
                zoom_start=9
            )

            colors = ['blue', 'crimson', 'violet', 'orange', 'yellow', 'black']
            cnt = 0

            for file in os.listdir(directory):
                open_path_1 = f'data/GIS/LP_outputs/{file}'
                print(file)
                name = file.rstrip('.csv')
                proposed_stations_1 = open_lp_proposed_stations(lp_proposed_stations_path=open_path_1)
                proposed_stations_1.set_index('id', inplace=True)
                proposed_stations_1 = join_dfs(station_locations, proposed_stations_1)

                feature_group = FeatureGroup(name=name)
                for i, row in proposed_stations_1.iterrows():
                    if row['demand'] == 0:
                        pass
                    else:
                        c = CircleMarker(
                            radius=row['demand'],
                            location=[row["latitude"], row["longitude"]],
                            tooltip=f"Station ID: {row.name} \n Demand: {row['demand']} kWh",
                            color=colors[cnt],
                            fill=True,
                            fill_color=colors[cnt]
                        )
                        c.add_to(feature_group)
                feature_group.add_to(m)
                cnt += 1

            LayerControl('bottomright', collapsed=False).add_to(m)
            if save_path:
                m.save(save_path)

            return m


def join_hex_ids()