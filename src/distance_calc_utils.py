from __future__ import division
from pyomo.environ import *
import pandas as pd
from haversine import haversine, Unit


def haversine_distance_matrix(df):
    # Create line list
    all_lines = []
    for id1 in list(df.B):
        for id2 in list(df.B):
            all_lines.append(f"{id1}_{id2}")

    # Create node and point dictionary
    point_list = list(zip(df['latitude'], df['longitude']))
    node_points = dict(list(zip(df.B, point_list)))

    # Create distance dataframe to fill
    distances = pd.DataFrame(columns=['dist'], index=all_lines)

    # Fill distances
    for index, row in distances.iterrows():
        n1, n2 = index.split("_")
        row['dist'] = haversine(node_points[n1], node_points[n2], unit=Unit.MILES)

    return distances