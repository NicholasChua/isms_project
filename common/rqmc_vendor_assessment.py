import csv
import itertools
import json
import numpy as np
from SALib.sample import sobol as sobol_sample
from SALib.analyze import sobol as sobol_analyze
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from common.common_stats import (
    calculate_ale,
    calculate_rosi,
    calculate_mode,
    find_first_non_zero_percentile,
    setup_sensitivity_problem,
    simulate_exposure_factor_sobol,
    simulate_annual_rate_of_occurrence_sobol,
    simulate_control_effectiveness_sobol,
    randomize_sobol_samples,
    convert_to_serializable,
)


RANDOM_SEED = 42
NUM_SAMPLES = 16384
KURTOSIS = 1.7
CURRENCY_SYMBOL = "\\$"


def _load_csv_data(
    file_path: str,
) -> dict[str, list[dict[str, int | float | list[float]]]]:
    """Helper function to load data from a CSV file containing input parameters for the risk calculation.

    The CSV file should have the following columns in order:
        - id
        - asset_value
        - exposure_factor_min/max or exposure_factor only
        - annual_rate_of_occurrence_min/max or annual_rate_of_occurrence only
        - control_reduction_i_min (alternating columns)
        - control_reduction_i_max (alternating columns)
        - control_cost_i (alternating columns)

    Args:
        file_path: The path to the CSV file.

    Returns:
        dict[str, list[dict[str, int | float | list[float]]]]: A dictionary with 'data' key containing list of risk dictionaries.

    Raises:
        FileNotFoundError: If CSV file not found
        ValueError: If control columns missing or invalid
    """
    result = {"data": []}

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise ValueError("CSV file is empty or has no headers")

            headers = reader.fieldnames

            # Extract and validate control numbers
            control_numbers = sorted(
                set(
                    int(col.split("_")[2])  # Get number after "control_reduction_"
                    for col in headers
                    if col.startswith("control_reduction_")
                    and not col.endswith(
                        "_max"
                    )  # Only process _min to avoid duplicates
                )
            )

            if not control_numbers:
                raise ValueError("No control columns found")

            # Process each row
            for row in reader:
                control_reductions = []
                control_costs = []

                # Process controls
                for num in control_numbers:
                    red_min_key = f"control_reduction_{num}_min"
                    red_max_key = f"control_reduction_{num}_max"
                    cost_key = f"control_cost_{num}"

                    if (
                        red_min_key not in row
                        or red_max_key not in row
                        or cost_key not in row
                    ):
                        raise ValueError(f"Missing control {num} data")

                    control_reductions.append(
                        [float(row[red_min_key]), float(row[red_max_key])]
                    )
                    control_costs.append(float(row[cost_key]))

                # Handle exposure factor (either range or single value)
                ef_range = (
                    [
                        float(row["exposure_factor_min"]),
                        float(row["exposure_factor_max"]),
                    ]
                    if "exposure_factor_min" in row
                    else [float(row["exposure_factor"]), float(row["exposure_factor"])]
                )

                # Handle annual rate of occurrence (either range or single value)
                aro_range = (
                    [
                        float(row["annual_rate_of_occurrence_min"]),
                        float(row["annual_rate_of_occurrence_max"]),
                    ]
                    if "annual_rate_of_occurrence_min" in row
                    else [
                        float(row["annual_rate_of_occurrence"]),
                        float(row["annual_rate_of_occurrence"]),
                    ]
                )

                # Build risk dictionary
                risk = {
                    "id": int(row["id"]),
                    "asset_value": float(row["asset_value"]),
                    "ef_range": ef_range,
                    "aro_range": aro_range,
                    "control_reduction_ranges": control_reductions,
                    "control_costs": control_costs,
                    "num_vendors": len(control_costs),
                }
                result["data"].append(risk)

    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {file_path}")
    except csv.Error as e:
        raise ValueError(f"CSV parsing error: {str(e)}")

    return result


def evaluate_model(
    asset_value: float,
    control_costs: list[float],
    X: np.ndarray,
    problem: dict[str, int | list[str] | list[float]],
) -> np.array:
    """Evaluate model for sensitivity analysis samples. The model calculates the ROSI for each sample. Each row in X corresponds to one set of parameter values, in the same order as problem["names"].

    For now, this function supports the following parameters:
    - EF_variance: Exposure factor variance
    - ARO_variance: Annual rate of occurrence variance
    - control_reduction_i_variance: Control effectiveness variance for vendor

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units
        control_costs: List of control costs, expressed in monetary units
        X: Samples generated for sensitivity analysis
        problem: Problem dictionary for sensitivity analysis

    Returns:
        np.array: ROSI values for each sample
    """
    # Initialize output array
    Y = []

    # Retrieve parameter names from the problem dictionary
    param_names = problem["names"]

    for row in X:
        # Extract parameter values from the row
        params = dict(zip(param_names, row))

        # Calculate ALE before controls
        ale_before = calculate_ale(asset_value, params["EF"], params["ARO"])

        # Calculate ALE after controls
        ale_after = ale_before
        for _, name in enumerate(param_names):
            if name.startswith("control_reduction_"):
                ale_after *= 1 - params[name]

        # Calculate ROSI
        rosi = calculate_rosi(ale_before, ale_after, control_costs)

        # Append ROSI to output array
        Y.append(rosi)

    return np.array(Y)


# def calculate_mode(values):
#     """Calculate mode using kernel density estimation and its percentage in the distribution

#     Args:
#         values: Array of values to analyze

#     Returns:
#         tuple: (mode value, percentage of values within 1% of mode)
#     """
#     if len(values) < 2:
#         return (values[0], 100.0) if len(values) == 1 else (None, None)

#     kde = gaussian_kde(values)
#     grid = np.linspace(min(values), max(values), 100)
#     mode_idx = np.argmax(kde(grid))
#     mode = grid[mode_idx]

#     # Calculate percentage of values within 1% of mode
#     mode_range = 0.01 * mode
#     count = np.sum((values >= mode - mode_range) & (values <= mode + mode_range))
#     percentage = (count / len(values)) * 100

#     return mode, percentage


def perform_sensitivity_analysis(
    asset_value: float,
    ef_range: list[float],
    aro_range: list[float],
    control_costs: list[float],
    control_reduction_ranges: list[list[float]],
    num_samples: int = NUM_SAMPLES,
) -> tuple[dict[str, dict[str, float]], dict[str, list[str]]]:
    """Perform Sobol sensitivity analysis on the model using the specified number of samples.

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units
        ef_range: Exposure factor range
        aro_range: Annual rate of occurrence range
        control_costs: List of control costs, expressed in monetary units
        control_reduction_ranges: List of control reduction ranges
        num_samples: Number of samples to generate for sensitivity analysis. Default is NUM_SAMPLES

    Returns:
        tuple[dict[str, dict[str, float]], dict[str, list[str]]]: Sensitivity analysis results and problem definition
    """
    # Ensure control_reduction_ranges is a list of lists
    if not all(
        isinstance(control_range, list) and len(control_range) == 2
        for control_range in control_reduction_ranges
    ):
        raise ValueError(
            "control_reduction_ranges must be a list of lists, each containing two floats"
        )

    # Skip fixed parameters in problem definition
    problem_dict = {}
    fixed_values = {}
    if ef_range[0] != ef_range[1]:
        problem_dict["EF"] = ef_range
    else:
        fixed_values["EF"] = ef_range[0]
    if aro_range[0] != aro_range[1]:
        problem_dict["ARO"] = aro_range
    else:
        fixed_values["ARO"] = aro_range[0]
    for i, control_range in enumerate(control_reduction_ranges):
        if control_range[0] != control_range[1]:
            problem_dict[f"control_reduction_{i+1}"] = control_range
        else:
            fixed_values[f"control_reduction_{i+1}"] = control_range[0]

    # If everything is fixed, sensitivity analysis is not relevant. Return empty results in that case
    if not problem_dict:
        return {}, {}

    # Setup sensitivity analysis problem
    problem = setup_sensitivity_problem(**problem_dict)

    # Generate samples using sobol sampler
    param_values = sobol_sample.sample(
        problem, num_samples, calc_second_order=False, seed=RANDOM_SEED
    )

    # Run model evaluations
    Y = evaluate_model(asset_value, control_costs, param_values, problem)

    # Create a copy of the problem dictionary to convert to numpy arrays
    problem_array = problem.copy()
    for key in problem_array.keys():
        if isinstance(problem_array[key], list):
            problem_array[key] = np.array(problem_array[key])

    # Calculate sensitivity indices using sobol analyzer
    Si = sobol_analyze.analyze(
        problem_array, Y, calc_second_order=False, seed=RANDOM_SEED
    )

    # Convert sensitivity analysis results to a dictionary of dictionaries
    sensitivity_analysis = {
        name: {
            "S1": Si["S1"][i],
            "S1_conf": Si["S1_conf"][i],
            "ST": Si["ST"][i],
            "ST_conf": Si["ST_conf"][i],
        }
        for i, name in enumerate(problem["names"])
    }

    return sensitivity_analysis, problem


def _plot_vendor_analysis(
    sensitivity_analysis: dict[str, dict[str, float]],
    problem: dict[str, list[str]],
    vendor_statistics: list[dict[str, float | int | list[float]]],
    output_file: str,
    currency_symbol: str = "$",
) -> None:
    """Generates plots for vendor assessment, including sensitivity analysis and vendor comparison.

    Args:
        sensitivity_analysis: Sensitivity analysis results
        problem: Problem definition used in the sensitivity analysis
        vendor_statistics: List of vendor statistics
        output_file: Output file to save the plot
        currency_symbol: Currency symbol to use in the statistics table. Default is CURRENCY_SYMBOL
    """
    # Set figure size and create a grid layout
    fig = plt.figure(figsize=(19.2, 10.8))
    gs = GridSpec(2, 2, figure=fig)

    # Sensitivity Analysis Plot (Top Left)
    ax1 = fig.add_subplot(gs[0, 0])

    # Only draw if there are at least two varying parameters
    if len(problem["names"]) < 2:
        ax1.axis("off")
        ax1.text(
            0.5,
            0.5,
            "Sensitivity Analysis not applicable",
            ha="center",
            va="center",
            fontsize=12,
        )
    else:
        # Set bar width
        bar_width = 0.35

        # Positions of the bars on the x-axis
        indices = np.arange(len(problem["names"]))

        # Extract sensitivity indices
        S1_percent = [
            sensitivity_analysis[name]["S1"] * 100 for name in problem["names"]
        ]
        ST_percent = [
            sensitivity_analysis[name]["ST"] * 100 for name in problem["names"]
        ]

        # Plot S1 and ST bars next to each other
        ax1.bar(
            indices - bar_width / 2,
            S1_percent,
            bar_width,
            label="First Order",
            color="blue",
        )
        ax1.bar(
            indices + bar_width / 2,
            ST_percent,
            bar_width,
            label="Total Order",
            color="orange",
            alpha=0.5,
        )

        # Add annotations to the bars
        for i, (s1, st) in enumerate(zip(S1_percent, ST_percent)):
            ax1.text(i - bar_width / 2, s1, f"{s1:.2f}%", ha="center", va="bottom")
            ax1.text(i + bar_width / 2, st, f"{st:.2f}%", ha="center", va="bottom")

        ax1.set_xlabel("Parameters")
        ax1.set_ylabel("Sensitivity Index (%)")
        ax1.set_xticks(indices)
        ax1.set_xticklabels(
            [
                name.replace("control_reduction_", "control_")
                for name in problem["names"]
            ]
        )
        ax1.set_xticklabels(
            [
                s.title() if s.startswith("control_") else s
                for s in [
                    name.replace("control_reduction_", "Control ")
                    for name in problem["names"]
                ]
            ]
        )
        ax1.legend()
        ax1.set_title("Parameter Sensitivity Analysis")

        # Set Y axis limit to the next value(s) up after the highest value to prevent text overlap with top of the plot
        max_value_sensitivity = max(max(S1_percent), max(ST_percent))
        base = int(max_value_sensitivity / 10)
        remainder = max_value_sensitivity % 10

        # If remainder is >= 9, add 2 steps, otherwise add 1 step
        if remainder >= 9:
            y_max = (base + 2) * 10
        else:
            y_max = (base + 1) * 10

        ax1.set_ylim(0, y_max)

    # Scatter Plot (Top Right)
    ax2 = fig.add_subplot(gs[0, 1])
    costs = [vendor["control_cost"] for vendor in vendor_statistics]
    ale_reduction_percentages = [
        vendor["mean_ale_reduction"] * 100 for vendor in vendor_statistics
    ]

    # Plot vendors and add ID annotations
    ax2.scatter(costs, ale_reduction_percentages, label="Vendors")
    for vendor in vendor_statistics:
        ax2.annotate(
            f"{vendor['vendor_id']}",
            (vendor["control_cost"], vendor["mean_ale_reduction"] * 100),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
        )
    # Find best and most effective vendors
    best_vendor = max(vendor_statistics, key=lambda x: x["mean_rosi"])
    most_effective_vendor = min(vendor_statistics, key=lambda x: x["mean_ale_after"])

    # Check if best and most effective are the same vendor
    is_same_vendor = best_vendor["vendor_id"] == most_effective_vendor["vendor_id"]

    # Highlight best and most effective vendors
    if is_same_vendor:
        # Plot combined point
        ax2.scatter(
            best_vendor["control_cost"],
            best_vendor["mean_ale_reduction"] * 100,
            color="purple",
            label="Best ROSI & Most Effective",
            zorder=6,
        )
    else:
        # Plot two separate points
        ax2.scatter(
            best_vendor["control_cost"],
            best_vendor["mean_ale_reduction"] * 100,
            color="red",
            label="Best Vendor (ROSI)",
            zorder=5,
        )
        ax2.scatter(
            most_effective_vendor["control_cost"],
            most_effective_vendor["mean_ale_reduction"] * 100,
            color="green",
            label="Most Effective (ALE Reduction)",
            zorder=5,
        )

    ax2.set_xlabel(f"Control Cost ({currency_symbol})")
    ax2.set_ylabel("Mean ALE Reduction (%)")
    ax2.set_title("Vendor Comparison: Cost vs. ALE Reduction")
    ax2.legend()
    ax2.grid(True)

    # Set y axis limit to the next value up after the highest value
    y_max = (int(max(ale_reduction_percentages) / 10) + 1) * 10
    ax2.set_ylim(0, y_max)

    # Statistics (Bottom)
    ax3 = fig.add_subplot(gs[1, :])  # Span both columns
    ax3.axis("off")

    if is_same_vendor:
        # Single column format for same vendor
        full_text = f"""
        Best ROSI & Most Effective Vendor (ID: {best_vendor['vendor_id']})
        ------------------------------------------
        ROSI Statistics:
          Mean: {next(v["mean_rosi"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}%
          Median: {next(v["median_rosi"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}%
          Mode: {next(v["mode_rosi"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}% ({next(v["mode_rosi_percentage"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}%)
          Std Dev: {currency_symbol}{next(v["std_dev_rosi"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}
        
        ALE Reduction: {next(v["mean_ale_reduction"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]) * 100:.2f}%
        ALE After Statistics:
          Mean: {currency_symbol}{next(v["mean_ale_after"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}
          Median: {currency_symbol}{next(v["median_ale_after"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}
          Mode: {currency_symbol}{next(v["mode_ale_after"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f} ({next(v["mode_ale_after_percentage"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}%)
          Std Dev: {currency_symbol}{next(v["std_dev_ale_after"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}
        """

        ax3.text(
            0.5,  # Centered
            0.95,
            full_text,
            ha="center",
            va="top",
            fontsize=10,
            transform=ax3.transAxes,
            linespacing=1.5,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=10),
        )
    else:
        # Two column format for different vendors
        best_text = f"""
        Best ROSI Vendor (ID: {best_vendor['vendor_id']})
        ------------------------------------------
        ROSI Statistics:
          Mean: {next(v["mean_rosi"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}%
          Median: {next(v["median_rosi"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}%
          Mode: {next(v["mode_rosi"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}% ({next(v["mode_rosi_percentage"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}%)
          Std Dev: {currency_symbol}{next(v["std_dev_rosi"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}
        
        ALE Reduction: {next(v["mean_ale_reduction"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]) * 100:.2f}%
        ALE After Statistics:
          Mean: {currency_symbol}{next(v["mean_ale_after"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}
          Median: {currency_symbol}{next(v["median_ale_after"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}
          Mode: {currency_symbol}{next(v["mode_ale_after"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f} ({next(v["mode_ale_after_percentage"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}%)
          Std Dev: {currency_symbol}{next(v["std_dev_ale_after"] for v in vendor_statistics if v["vendor_id"] == best_vendor["vendor_id"]):.2f}
        """

        effective_text = f"""
        Most Effective Vendor (ID: {most_effective_vendor['vendor_id']})
        ------------------------------------------
        ROSI Statistics:
          Mean: {next(v["mean_rosi"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}%
          Median: {next(v["median_rosi"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}%
          Mode: {next(v["mode_rosi"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}% ({next(v["mode_rosi_percentage"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}%)
          Std Dev: {currency_symbol}{next(v["std_dev_rosi"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}
        
        ALE Reduction: {next(v["mean_ale_reduction"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]) * 100:.2f}%
        ALE After Statistics:
          Mean: {currency_symbol}{next(v["mean_ale_after"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}
          Median: {currency_symbol}{next(v["median_ale_after"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}
          Mode: {currency_symbol}{next(v["mode_ale_after"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f} ({next(v["mode_ale_after_percentage"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}%)
          Std Dev: {currency_symbol}{next(v["std_dev_ale_after"] for v in vendor_statistics if v["vendor_id"] == most_effective_vendor["vendor_id"]):.2f}
        """

        # Position text in two columns
        ax3.text(
            0.25,  # Left column
            0.95,
            best_text,
            ha="center",
            va="top",
            fontsize=10,
            transform=ax3.transAxes,
            linespacing=1.5,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=10),
        )
        ax3.text(
            0.75,  # Right column
            0.95,
            effective_text,
            ha="center",
            va="top",
            fontsize=10,
            transform=ax3.transAxes,
            linespacing=1.5,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=10),
        )

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(output_file)
    plt.close()


def simulate_vendor_assessment_decision(
    asset_value: float,
    ef_range: list[float],
    aro_range: list[float],
    control_costs: list[float],
    control_reduction_ranges: list[list[float]],
    num_vendors: int,
    kurtosis: float = KURTOSIS,
    num_samples: int = NUM_SAMPLES,
    currency_symbol: str = CURRENCY_SYMBOL,
    output_json_file: str = None,
    output_png_file: str = None,
    output_json_response: bool = False,
) -> dict | None:
    """Given a set of security controls to be implemented that can be provided by multiple vendors, determine the optimal vendor(s) to minimize the risk to the asset, based on ROSI (used to determine the best vendor when prioritizing cost effectiveness) and ALE reduction (used to determine the most effective vendor regardless of cost), using RQMC and Sobol sensitivity analysis.

    The simulation uses:
        - Sobol samples for the exposure factor, annual rate of occurrence, and control effectiveness of each vendor
        - RQMC for adding randomness to the Sobol samples and generating multiple scenarios for each vendor
        - Beta distribution for introducing kurtosis to the exposure factor
        - Poisson distribution for simulating the annual rate of occurrence, with a specified number of decimal places to bypass the integer limitation of the distriubtion
        - Uniform distribution for the control effectiveness of each vendor based on the provided ranges given no reason to assume a specific distribution
        - Sobol sensitivity analysis as a global sensitivity analysis method to determine the impact of varying the exposure factor, annual rate of occurrence, and control costs on the ROSI
            - First order sensitivity index (S1) measures the impact of each parameter on the output
            - Total order sensitivity index (ST) measures the impact of each parameter, including interactions with other parameters

    The implementation performs a multivariate simulation to evaluate the ALE and ROSI for each vendor, given variability of EF, ARO, and control effectiveness, expressed as a range. The simulation results are then used to determine the best and most effective vendor(s) based on the calculated statistics. The simulation also performs a sensitivity analysis to determine the impact of varying the EF, ARO, and control effectiveness on the ROSI.

    An example scenario is as follows:
        - You have an asset value of X
        - You have 4 vendors providing security controls (referred to as 1, 2, 3, 4), with a cost of A, B, C, D
        - You predict the exposure factor to be between X_ef and Y_ef
        - You predict the annual rate of occurrence to be between X_aro and Y_aro
        - You don't know the exact control effectiveness, but you predict it to be between X_control and Y_control for each vendor
        - You want to know which vendor to choose, considering the best balance between cost and effectiveness (using ROSI)
        - You want to know which vendor to choose to minimize the risk to the asset, regardless of cost (using ALE reduction)
        - You want to know the impact of varying the exposure factor, annual rate of occurrence, and control effectiveness on the ROSI

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units.
        ef_range: The range of the exposure factor, representing the percentage of the asset value that is at risk during a risk event, expressed as decimals.
        aro_range: The range of the annual rate of occurrence, representing the frequency of the risk event over a year, expressed as decimals.
        control_costs: The base annualized cost of implementing each security control, expressed in monetary units as a list.
        control_reduction_ranges: The percentage reduction in risk for each vendor's control, expressed as a list of lists containing the minimum and maximum values
        num_vendors: Number of vendors to simulate.
        kurtosis: The kurtosis of the distribution for the exposure factor. Default is constant KURTOSIS.
        num_samples: The number of samples to generate for the simulation. Default is constant NUM_SAMPLES.
        currency_symbol: The currency symbol to use for displaying monetary values. Default is constant CURRENCY_SYMBOL.
        output_json_file: The output JSON file to save the simulation results. Default is None. Skipped if output_json_response is True.
        output_png_file: The output PNG file to save the simulation results. Default is None. Skipped if output_json_response is True.
        output_json_response: Whether to return the simulation results as a JSON response. Default is False. Overrides output_json_file and output_png_file if True.

    Returns:
        None
    """
    # Initialize results dictionary
    results = {
        "input_parameters": {
            "asset_value": asset_value,
            "ef_range": ef_range,
            "aro_range": aro_range,
            "control_reduction_ranges": control_reduction_ranges,
            "control_costs": control_costs,
            "num_vendors": num_vendors,
            "num_samples": num_samples,
            "kurtosis": kurtosis,
        },
        "vendor_statistics": [],
        "best_vendor": None,
        "most_effective_vendor": None,
    }

    # Set random seed for reproducibility
    np.random.seed(RANDOM_SEED)

    # Create a dictionary to store cost adjustment ranges
    cost_adj = {}

    # Determine if any ranges are fixed values by checking if the ranges are equal
    is_ef_fixed = ef_range[0] == ef_range[1]
    is_aro_fixed = aro_range[0] == aro_range[1]
    for i, control_reduction_range in enumerate(control_reduction_ranges):
        is_control_reduction_fixed = (
            control_reduction_range[0] == control_reduction_range[1]
        )
        cost_adj[i] = is_control_reduction_fixed

    # Build a list of (param_type, vendor_index) only for non-fixed parameters
    param_order = []
    for i in range(num_vendors):
        if not is_ef_fixed:
            param_order.append(("EF", i))
    for i in range(num_vendors):
        if not is_aro_fixed:
            param_order.append(("ARO", i))
    for i in range(num_vendors):
        for j, is_fixed in cost_adj.items():
            if not is_fixed:
                param_order.append(("CONTROL_E", (i, j)))

    # If param_order is empty, all parameters are fixed; fill slices with constants
    if not param_order:
        ef_slice = np.full((num_samples, num_vendors), ef_range[0])
        aro_slice = np.full((num_samples, num_vendors), aro_range[0])
        control_reduction_slices = {
            i: np.full((num_samples, num_vendors), control_reduction_ranges[i][0])
            for i in range(len(control_reduction_ranges))
        }
    else:
        # Generate multi-dimensional Sobol samples for only the parameters that vary
        combined_parameters = {
            name: rng
            for name, rng in itertools.chain(
                (
                    (f"EF_{i+1}", ef_range)
                    for i in range(num_vendors)
                    if not is_ef_fixed
                ),
                (
                    (f"ARO_{i+1}", aro_range)
                    for i in range(num_vendors)
                    if not is_aro_fixed
                ),
                (
                    (f"control_reduction_{i+1}_{j+1}", control_reduction_ranges[j])
                    for i in range(num_vendors)
                    for j in cost_adj
                    if not cost_adj[j]
                ),
            )
        }
        problem_combined = setup_sensitivity_problem(**combined_parameters)
        sobol_combined = sobol_sample.sample(
            problem_combined, num_samples, calc_second_order=False, seed=RANDOM_SEED
        )
        sobol_combined = randomize_sobol_samples(sobol_combined)
        sobol_combined = sobol_combined[:num_samples, :]

    # Initialize slices
    ef_slice = np.zeros((num_samples, num_vendors))
    aro_slice = np.zeros((num_samples, num_vendors))
    control_reduction_slices = {
        i: np.zeros((num_samples, num_vendors))
        for i in range(len(control_reduction_ranges))
    }

    # Copy Sobol columns into slices, or fill with a fixed value
    col = 0
    for i in range(num_vendors):
        if is_ef_fixed:
            ef_slice[:, i] = ef_range[0]
        else:
            ef_slice[:, i] = sobol_combined[:, col]
            col += 1
    for i in range(num_vendors):
        if is_aro_fixed:
            aro_slice[:, i] = aro_range[0]
        else:
            aro_slice[:, i] = sobol_combined[:, col]
            col += 1
    for i in range(num_vendors):
        for j, is_fixed in cost_adj.items():
            if is_fixed:
                control_reduction_slices[j][:, i] = control_reduction_ranges[j][0]
            else:
                control_reduction_slices[j][:, i] = sobol_combined[:, col]
                col += 1

    # Simulate EF, ARO, and control effectiveness using Sobol samples
    ef_samples = simulate_exposure_factor_sobol(ef_slice, ef_range, kurtosis)
    aro_samples = simulate_annual_rate_of_occurrence_sobol(aro_slice, aro_range)
    control_reduction_samples = np.zeros((num_samples, len(control_reduction_ranges)))

    for i in range(len(control_reduction_ranges)):
        control_reduction_samples[:, i] = simulate_control_effectiveness_sobol(
            control_reduction_slices[i][:, 0], control_reduction_ranges[i]
        )

    # Ensure control reduction samples are clamped to their respective ranges
    for i in range(len(control_reduction_ranges)):
        control_reduction_samples[:, i] = np.clip(
            control_reduction_samples[:, i],
            control_reduction_ranges[i][0],
            control_reduction_ranges[i][1],
        )

    # For each vendor, simulate num_samples scenarios and calculate ALE and ROSI
    for vendor in range(num_vendors):
        ale_before_values = []
        ale_after_values = []
        rosi_values = []
        for sample in range(num_samples):
            # Retrieve one sample from each of EF, ARO, and the vendor's control effectiveness
            ef_sample = ef_samples[sample][vendor]
            aro_sample = aro_samples[sample][vendor]
            control_reduction_sample = control_reduction_samples[sample][vendor]

            # Calculate ALE before applying controls
            ale_before = calculate_ale(asset_value, ef_sample, aro_sample)

            # Adjust the ARO based on the control effectiveness
            new_aro = aro_sample * (1 - control_reduction_sample)

            # Calculate ALE after applying controls
            ale_after = calculate_ale(asset_value, ef_sample, new_aro)

            # Calculate ROSI
            rosi = calculate_rosi(ale_before, ale_after, control_costs[vendor])

            # Store results for this iteration
            ale_before_values.append(ale_before)
            ale_after_values.append(ale_after)
            rosi_values.append(rosi)

        # Calculate statistics
        vendor_stat = {
            "vendor_id": vendor + 1,
            "control_cost": control_costs[vendor],
            "control_reduction_ranges": control_reduction_ranges[vendor],
        }

        percentiles = [1, 2.5, 5, 10, 25, 75, 90, 95, 97.5, 99]

        # Calculate stats for ALE before controls
        ale_before_values = np.array(ale_before_values)
        vendor_stat["mean_ale_before"] = np.mean(ale_before_values)
        vendor_stat["median_ale_before"] = np.median(ale_before_values)
        vendor_stat["mode_ale_before"], vendor_stat["mode_ale_before_percentage"] = (
            calculate_mode(ale_before_values)
        )
        vendor_stat["std_dev_ale_before"] = np.std(ale_before_values)
        for p in percentiles:
            vendor_stat[f"ale_before_percentile_{p}"] = np.percentile(
                ale_before_values, p
            )

        # Calculate stats for ALE after controls. Also add percentage reduction
        ale_after_values = np.array(ale_after_values)
        vendor_stat["mean_ale_after"] = np.mean(ale_after_values)
        vendor_stat["median_ale_after"] = np.median(ale_after_values)
        vendor_stat["mode_ale_after"], vendor_stat["mode_ale_after_percentage"] = (
            calculate_mode(ale_after_values)
        )
        vendor_stat["std_dev_ale_after"] = np.std(ale_after_values)
        vendor_stat["mean_ale_reduction"] = (
            vendor_stat["mean_ale_before"] - vendor_stat["mean_ale_after"]
        ) / vendor_stat["mean_ale_before"]
        (
            vendor_stat["first_nonzero_percentile_ale_after"],
            vendor_stat["first_nonzero_value_ale_after"],
        ) = find_first_non_zero_percentile(ale_after_values)
        for p in percentiles:
            vendor_stat[f"ale_after_percentile_{p}"] = np.percentile(
                ale_after_values, p
            )

        # Calculate stats for ROSI
        rosi_values = np.array(rosi_values)
        vendor_stat["mean_rosi"] = np.mean(rosi_values)
        vendor_stat["median_rosi"] = np.median(rosi_values)
        vendor_stat["mode_rosi"], vendor_stat["mode_rosi_percentage"] = calculate_mode(
            rosi_values
        )
        vendor_stat["std_dev_rosi"] = np.std(rosi_values)
        for p in percentiles:
            vendor_stat[f"rosi_percentile_{p}"] = np.percentile(rosi_values, p)

        # Append vendor statistics to results
        results["vendor_statistics"].append(vendor_stat)

    # Determine order of vendors based on mean ROSI/ALE reduction descending and return their IDs
    results["best_vendor"] = [
        vendor["vendor_id"]
        for vendor in sorted(
            results["vendor_statistics"], key=lambda x: x["mean_rosi"], reverse=True
        )
    ]
    results["most_effective_vendor"] = [
        vendor["vendor_id"]
        for vendor in sorted(
            results["vendor_statistics"],
            key=lambda x: x["mean_ale_after"],
            reverse=False,
        )
    ]

    # Perform sensitivity analysis
    sensitivity_results, problem = perform_sensitivity_analysis(
        asset_value,
        ef_range,
        aro_range,
        control_costs,
        control_reduction_ranges,
        num_samples,
    )

    # Add sensitivity analysis results to the output
    results["sensitivity_analysis"] = sensitivity_results
    # Serialize and save the results to a JSON file
    serialized_results = convert_to_serializable(results)

    if output_json_response:
        return results

    if output_json_file:
        with open(output_json_file, "w") as file:
            json.dump(serialized_results, file, indent=4)

    if output_png_file:
        _plot_vendor_analysis(
            sensitivity_results,
            problem,
            results["vendor_statistics"],
            output_png_file,
            currency_symbol=currency_symbol,
        )

    return None
