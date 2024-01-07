import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import global_controller_test


if __name__ == "__main__":
    data = {'endpoint_1': [1, 2, 3, 4],
            'endpoint_2': [2, 3, 4, 5],
            'latency': [1, 2, 3, 4]}
    coef = global_controller_test.train_linear_regression(data, "latency")
    print(coef)
    # Access the coefficient for 'Feature1'
    # print(get_coef(coefficients_df, 'endpoint_1'))
    # print(get_coef(coefficients_df, 'endpoint_2'))
    # print(get_coef(coefficients_df, 'intercept'))
