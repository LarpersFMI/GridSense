import pandas as pd

SEGMENTS = ("ev_owner", "heat_pump", "prosumer", "standard")


def generate_customers(n: int, seed: int) -> pd.DataFrame:
    raise NotImplementedError
