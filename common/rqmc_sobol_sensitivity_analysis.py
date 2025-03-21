import itertools
from textwrap import wrap
from matplotlib.gridspec import GridSpec
import numpy as np
from itertools import permutations
import matplotlib.pyplot as plt
import json
from SALib.sample import sobol as sobol_sample
from SALib.analyze import sobol as sobol_analyze
import csv


from common.common_stats import (
    calculate_ale,
    calculate_rosi,
    setup_sensitivity_problem,
    simulate_exposure_factor_sobol,
    simulate_annual_rate_of_occurrence_sobol,
    randomize_sobol_samples,
    convert_to_serializable,
)

RANDOM_SEED = 42
NUM_SAMPLES = 16384  # Number of Sobol samples 2^14
KURTOSIS = 1.7  # Results in alpha and beta of 0.5
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
        - cost_adjustment_min/max or cost_adjustment only
        - control_reduction_i (alternating columns)
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
                [
                    int(col.split("_")[-1])
                    for col in headers
                    if col.startswith("control_reduction_")
                ]
            )

            if not control_numbers:
                raise ValueError("No control columns found")

            # Process each row
            for row in reader:
                control_reductions = []
                control_costs = []

                # Process controls
                for num in control_numbers:
                    red_key = f"control_reduction_{num}"
                    cost_key = f"control_cost_{num}"

                    if red_key not in row or cost_key not in row:
                        raise ValueError(f"Missing control {num} data")

                    control_reductions.append(float(row[red_key]))
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

                # Handle cost adjustment (either range or single value)
                cost_adj_range = (
                    [
                        float(row["cost_adjustment_min"]),
                        float(row["cost_adjustment_max"]),
                    ]
                    if "cost_adjustment_min" in row
                    else [float(row["cost_adjustment"]), float(row["cost_adjustment"])]
                )

                # Build risk dictionary
                risk = {
                    "id": int(row["id"]),
                    "asset_value": float(row["asset_value"]),
                    "ef_range": ef_range,
                    "aro_range": aro_range,
                    "cost_adjustment_range": cost_adj_range,
                    "control_reductions": control_reductions,
                    "control_costs": control_costs,
                    "num_years": len(control_costs),
                }
                result["data"].append(risk)

    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {file_path}")
    except csv.Error as e:
        raise ValueError(f"CSV parsing error: {str(e)}")

    return result


def calculate_compounding_costs(
    control_costs: list[float],
    cost_adjustment_range: list[float],
    years: int,
    cost_adjustment_samples: np.ndarray,
    num_samples: int = NUM_SAMPLES,
) -> dict[str, dict[str, dict[str, np.float64]]]:
    """Given a list of control costs, a cost adjustment range, and a number of years, calculate the cost for each control for each year.

    Args:
        control_costs: Base annualized cost of controls
        cost_adjustment_range: Cost adjustment per year range
        years: Number of years to simulate
        cost_adjustment_samples: Simulated cost adjustments
        num_samples: Number of samples to simulate. Default is NUM_SAMPLES

    Returns:
        dict[str, dict[str, dict[str, np.float64]]]: Dictionary of costs and adjustments for each control, for each year
    """
    # Initialize costs dictionary
    costs = {}

    # Year 0 is the base cost and has no adjustment
    costs["year_0"] = {
        f"control_{index + 1}": {
            "cost": np.float64(control_cost),
            "adjustment": np.float64(0.0),
        }
        for index, control_cost in enumerate(control_costs)
    }

    # Dynamically compute how many samples we can average per control-year
    num_dimensions = len(control_costs) * years
    # Determine the number of samples to average for each control-year with a minimum of 1
    n_avg = max(1, num_samples // num_dimensions)

    # Calculate costs for each year on a compounding basis for each control
    for year in range(1, years + 1):
        costs[f"year_{year}"] = {}
        for index, _ in enumerate(control_costs):
            # Use mean of multiple Sobol samples for adjustment
            sample_start = ((year - 1) * len(control_costs) + index) * n_avg
            sample_end = sample_start + n_avg
            adjustment_values = cost_adjustment_samples[
                sample_start:sample_end, index % cost_adjustment_samples.shape[1]
            ]
            adjustment_mean = adjustment_values.mean()
            adjustment = np.float64(
                adjustment_mean * (cost_adjustment_range[1] - cost_adjustment_range[0])
                + cost_adjustment_range[0]
            )

            previous_year_cost = costs[f"year_{year - 1}"][f"control_{index + 1}"][
                "cost"
            ]
            costs[f"year_{year}"][f"control_{index + 1}"] = {
                "cost": np.float64(
                    previous_year_cost + (previous_year_cost * adjustment)
                ),
                "adjustment": adjustment,
            }
    return costs


def calculate_statistics_for_permutation_per_year(
    asset_value: float,
    costs: dict[str, dict[str, dict[str, np.float64]]],
    ef_samples: np.ndarray,
    aro_samples: np.ndarray,
    permutation: tuple[int],
    control_reductions: list,
    num_of_simulations: int = NUM_SAMPLES,
) -> dict[str, float]:
    """Given a permutation of controls, calculate the ROSI for each year and the total ROSI for the permutation.

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units
        costs: Dictionary of costs and adjustments for each control, for each year
        ef_samples: Simulated exposure factors
        aro_samples: Simulated annual rates of occurrence
        permutation: A single permutation of controls represented as a tuple of integers
        control_reductions: List of control reduction percentages
        num_of_simulations: Number of samples to simulate

    Returns:
        dict[str, float]: Dictionary of results for the permutation
    """
    # Initialize ROSI
    rosi_per_simulation = []

    for i in range(num_of_simulations):
        rosi_per_year = []
        results = {
            "permutation": permutation,
            "total_rosi": 0.0,
        }

        for year in range(len(permutation)):
            # Retrieve the appropriate control and its cost for the year
            control = permutation[year]
            control_cost = costs[f"year_{year + 1}"][f"control_{control}"]["cost"]

            # Calculate the total cost by summing the costs of all controls up to the current year, inclusive
            total_cost = sum(
                [
                    costs[f"year_{year + 1}"][f"control_{control}"]["cost"]
                    for control in permutation[: year + 1]
                ]
            )

            # Calculate the new ARO after applying the control
            aro_after = aro_samples[i][year] * (1 - control_reductions[control - 1])

            # Calculate the new ALE after applying the control
            ale_after = calculate_ale(asset_value, ef_samples[i][year], aro_after)

            # Calculate the ALE before applying the control
            if year == 0:
                ale_before = calculate_ale(
                    asset_value, ef_samples[i][year], aro_samples[i][year]
                )
            else:
                ale_before = results[f"year_{year}"]["ale_after"]

            # Calculate the ROSI after applying the control and save it
            rosi = calculate_rosi(ale_before, ale_after, total_cost)
            rosi_per_year.append(rosi)

            # Add year-by-year information to the results
            results[f"year_{year + 1}"] = {
                "ale_before": ale_before,
                "ale_after": ale_after,
                "control_cost": control_cost,
                "total_cost": total_cost,
                "rosi": rosi,
            }

        # Calculate the total ROSI for the permutation
        results["total_rosi"] = np.sum(rosi_per_year)
        rosi_per_simulation.append(results["total_rosi"])

    # Average the ROSI over all simulations
    average_rosi = np.mean(rosi_per_simulation)
    results["total_rosi"] = average_rosi

    return results


def calculate_statistics_for_permutation_aggregate(
    asset_value: float,
    costs: dict[str, dict[str, dict[str, np.float64]]],
    ef_samples: np.ndarray,
    aro_samples: np.ndarray,
    permutation: tuple[int],
    control_reductions: list,
    num_of_simulations: int = NUM_SAMPLES,
) -> dict[str, float]:
    """Given a permutation of controls, calculate the ROSI for the entire period. Currently not being used in the main simulation, as we are interested in year-by-year results.

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units
        costs: Dictionary of costs and adjustments for each control, for each year
        ef_samples: Simulated exposure factors
        aro_samples: Simulated annual rates of occurrence
        permutation: A single permutation of controls represented as tuple of integers
        control_reductions: List of control reduction percentages
        num_of_simulations: Number of samples to simulate. Default is NUM_SAMPLES

    Returns:
        dict[str, float]: Dictionary with permutation and total ROSI
    """
    rosi_per_simulation = []

    for i in range(num_of_simulations):
        results = {
            "permutation": permutation,
            "total_rosi": 0.0,
        }

        # Calculate initial ALE and yearly data
        for year in range(len(permutation)):
            control = permutation[year]
            control_cost = costs[f"year_{year + 1}"][f"control_{control}"]["cost"]

            # Calculate total cost up to this year
            total_cost = sum(
                costs[f"year_{y + 1}"][f"control_{permutation[y]}"]["cost"]
                for y in range(year + 1)
            )

            # Calculate ALE before and after for this year
            ale_before = calculate_ale(
                asset_value, ef_samples[i][year], aro_samples[i][year]
            )
            reduction = 1 - control_reductions[control - 1]
            ale_after = calculate_ale(
                asset_value, ef_samples[i][year], aro_samples[i][year] * reduction
            )

            # Store year data
            results[f"year_{year + 1}"] = {
                "ale_before": ale_before,
                "ale_after": ale_after,
                "control_cost": control_cost,
                "total_cost": total_cost,
            }

        # Calculate aggregate ROSI
        total_ale_before = sum(
            results[f"year_{y + 1}"]["ale_before"] for y in range(len(permutation))
        )
        total_ale_after = sum(
            results[f"year_{y + 1}"]["ale_after"] for y in range(len(permutation))
        )
        total_costs = results[f"year_{len(permutation)}"]["total_cost"]

        rosi = calculate_rosi(total_ale_before, total_ale_after, total_costs)
        rosi_per_simulation.append(rosi)

    # Set final ROSI value
    results["total_rosi"] = float(np.mean(rosi_per_simulation))

    return results


def evaluate_model(
    asset_value: float,
    control_costs: list[float],
    control_reductions: list[float],
    X: np.ndarray,
    problem: dict[str, int | list[str] | list[float]],
    fixed_values: dict[str, float] = None,
) -> np.array:
    """Evaluate model for sensitivity analysis samples. The model calculates the ROSI for each sample. Each row in X corresponds to one set of parameter values, in the same order as problem["names"].

    For now, this function supports the following parameters:
    - EF_variance: Exposure factor variance
    - ARO_variance: Annual rate of occurrence variance
    - cost_variance: Cost adjustment variance

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units
        control_costs: List of control costs, expressed in monetary units
        control_reductions: List of control reduction percentages, expressed as decimals
        X: Samples generated for sensitivity analysis
        problem: Problem dictionary for sensitivity analysis
        fixed_values: Dictionary of fixed parameter values. Default is None

    Returns:
        np.array: ROSI values for each sample
    """
    # Initialize output array
    Y = []

    # Retrieve parameter names from the problem dictionary
    param_names = problem["names"]

    for row in X:
        # Map each parameter name to its value
        param_values = dict(zip(param_names, row))

        # Retrieve parameters by name, using fixed values if provided
        ef = fixed_values.get("EF", param_values.get("EF"))
        aro = fixed_values.get("ARO", param_values.get("ARO"))
        cost_adj = fixed_values.get("cost_variance", param_values.get("cost_variance"))

        # Calculate base ALE
        ale = calculate_ale(asset_value, ef, aro)

        # Adjust costs
        adjusted_costs = [cost * (1 + cost_adj) for cost in control_costs]

        # Calculate ALE after applying first control
        ale_after = ale * (1 - control_reductions[0])

        # Calculate ROSI for demonstration
        rosi = calculate_rosi(ale, ale_after, adjusted_costs[0])
        Y.append(rosi)

    return np.array(Y)


def perform_sensitivity_analysis(
    asset_value: float,
    ef_range: list[float],
    aro_range: list[float],
    cost_adjustment_range: list[float],
    control_costs: list[float],
    control_reductions: list[float],
    num_samples: int = NUM_SAMPLES,
) -> tuple[dict[str, dict[str, float]], dict[str, list[str]]]:
    """Perform Sobol sensitivity analysis on the model using the specified number of samples.

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units
        ef_range: Exposure factor range
        aro_range: Annual rate of occurrence range
        cost_adjustment_range: Cost adjustment per year range
        control_costs: List of control costs, expressed in monetary units
        control_reductions: List of control reduction percentages, expressed as decimals
        num_samples: Number of samples to generate for sensitivity analysis. Default is NUM_SAMPLES

    Returns:
        tuple[dict[str, dict[str, float]], dict[str, list[str]]]: Sensitivity analysis results and problem definition
    """
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
    if cost_adjustment_range[0] != cost_adjustment_range[1]:
        problem_dict["cost_variance"] = cost_adjustment_range
    else:
        fixed_values["cost_variance"] = cost_adjustment_range[0]

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
    Y = evaluate_model(
        asset_value,
        control_costs,
        control_reductions,
        param_values,
        problem,
        fixed_values,
    )

    # Create a copy of the problem dictionary to convert to numpy arrays
    problem_array = problem.copy()
    for key in problem_array.keys():
        if key != "num_vars":
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


def _is_fixed_range(value_range: list[float]) -> bool:
    """Helper function to check if a range represents a fixed value.

    Args:
        value_range: List of two floats representing a range

    Returns:
        bool: True if the range represents a fixed value, False otherwise
    """
    return abs(value_range[0] - value_range[1]) < 1e-10


def _format_scenario_text(
    asset_value: float,
    num_years: int,
    ef_range: list[float],
    aro_range: list[float],
    cost_adjustment_range: list[float],
    currency_symbol: str = "$",
) -> str:
    """Helper function to format the scenario text based on fixed/range values.

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units
        num_years: Number of years to simulate
        ef_range: Exposure factor range
        aro_range: Annual rate of occurrence range
        cost_adjustment_range: Cost adjustment per year range
        currency_symbol: Currency symbol to use in the statistics table. Default is CURRENCY_SYMBOL

    Returns:
        str: Formatted scenario text
    """
    # Format EF text
    if _is_fixed_range(ef_range):
        ef_text = f"You predict the exposure factor to be {ef_range[0]:.1f}"
    else:
        ef_text = f"You predict the exposure factor to be between {ef_range[0]:.1f} and {ef_range[1]:.1f}"

    # Format ARO text
    if _is_fixed_range(aro_range):
        aro_text = f"You predict the annual rate of occurrence to be {aro_range[0]:.1f}"
    else:
        aro_text = f"You predict the annual rate of occurrence to be between {aro_range[0]:.1f} and {aro_range[1]:.1f}"

    # Format cost adjustment text
    if _is_fixed_range(cost_adjustment_range):
        cost_text = f"You predict an annual (compounding) cost adjustment of {cost_adjustment_range[0] * 100:.1f}%"
    else:
        cost_text = f"You predict an annual (compounding) cost adjustment between {cost_adjustment_range[0] * 100:.1f}% and {cost_adjustment_range[1] * 100:.1f}%"

    return f"""Scenario: You have an asset value of {currency_symbol}{asset_value:.2f} and want to implement {num_years} security controls over {num_years} years at a rate of one control per year. {ef_text}. {aro_text}. {cost_text}."""


def _plot_combined_analysis(
    sensitivity_analysis: dict[str, dict[str, float]],
    problem: dict[str, list[str]],
    exported_results: dict[str, any],
    output_file: str,
    currency_symbol: str = CURRENCY_SYMBOL,
) -> None:
    """Plot a combined analysis of sensitivity analysis, permutation effectiveness, and ALE progression for the best-performing permutation. Also provide statistics on the input parameters and simulation results.

    The results appear in a 2x2 grid layout with the following plots:
        - Top Left - Parameter Sensitivity Analysis: Bar plot showing the first order and total order sensitivity indices for each parameter
        - Top Right - Scatter Plot of Permutations: Scatter plot showing the permutations by weighted risk reduction and mean ROSI, highlighting the best-performing permutation
        - Bottom Left - Year-by-Year ALE Progression: Line plot showing the year-by-year ALE progression for the best-performing permutation
        - Bottom Right - Statistics: Table showing the input parameters and simulation results

    Args:
        sensitivity_analysis: Sensitivity analysis results
        problem: Problem definition used in the sensitivity analysis
        exported_results: Exported results from the simulation
        output_file: Output file to save the plot
        currency_symbol: Currency symbol to use in the statistics table. Default is CURRENCY_SYMBOL

    Returns:
        None
    """
    # Set figure size to 1920x1080 pixels and create a grid layout
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
        ax1.set_xticklabels(problem["names"])
        ax1.legend()
        ax1.set_title("Parameter Sensitivity Analysis")

        # Set Y axis limit to the next value up after the highest value
        max_value_sensitivity = max(max(S1_percent), max(ST_percent))
        y_max = (int(max_value_sensitivity / 10) + 1) * 10
        ax1.set_ylim(0, y_max)

    # Scatter Plot (Top Right)
    ax2 = fig.add_subplot(gs[0, 1])
    weighted_reductions = []
    mean_rosi_values = []
    permutations = []

    for permutation_data in exported_results["ranked_permutations"]:
        permutation = permutation_data["permutation"]
        mean_rosi = permutation_data["total_rosi"]

        # Calculate total weighted risk reduction for the permutation
        total_weighted_reduction = 0
        for year, control in enumerate(permutation, start=1):
            control_cost = exported_results["results"]["control_cost_values"][
                f"year_{year}"
            ][f"control_{control}"]["cost"]
            control_reduction = exported_results["simulation_parameters"][
                "control_reductions"
            ][control - 1]
            total_weighted_reduction += control_cost * control_reduction

        weighted_reductions.append(total_weighted_reduction)
        mean_rosi_values.append(mean_rosi)
        permutations.append(permutation)

    ax2.scatter(weighted_reductions, mean_rosi_values, alpha=0.7, label="Permutations")

    # Highlight best-performing permutation
    best_index = mean_rosi_values.index(max(mean_rosi_values))
    ax2.scatter(
        weighted_reductions[best_index],
        mean_rosi_values[best_index],
        color="red",
        label="Best Permutation",
        zorder=5,
    )

    # Show the best-performing permutation annotation
    ax2.text(
        weighted_reductions[best_index],
        mean_rosi_values[best_index],
        str(permutations[best_index]),
        fontsize=8,
        ha="right",
    )

    ax2.set_xlabel(f"Total Weighted Risk Reduction ({currency_symbol})")
    ax2.set_ylabel("Mean ROSI (%)")
    ax2.set_title("Scatter Plot of Permutations by Weighted Risk Reduction/ROSI")
    ax2.legend()
    ax2.grid(True)

    # ALE Progression Plot (Bottom Left)
    ax3 = fig.add_subplot(gs[1, 0])
    years = []
    ale_values = []

    # Extract ALE data year-by-year
    for year in range(1, len(exported_results["results"]["best_permutation"]) + 1):
        years.append(year)
        ale_values.append(
            exported_results["ranked_permutations"][0][f"year_{year}"]["ale_after"]
        )

    ax3.plot(
        years,
        ale_values,
        label="ALE After Controls",
        marker="o",
        linestyle="-",
        color="green",
    )

    # Add ALE values as annotations with smart positioning
    padding = 0.02 * (max(ale_values) - min(ale_values))
    for i, ale in enumerate(ale_values):
        # Check if the current ALE is lower than the previous and next ALE values
        if (i > 0 and ale_values[i - 1] < ale) and (
            i < len(ale_values) - 1 and ale_values[i + 1] < ale
        ):
            # Place annotation on top
            ax3.text(
                years[i],
                ale + padding,
                f"{currency_symbol}{ale:.2f}",
                fontsize=8,
                ha="center",
                va="bottom",
            )
        else:
            # Place annotation below
            ax3.text(
                years[i],
                ale - padding,
                f"{currency_symbol}{ale:.2f}",
                fontsize=8,
                ha="center",
                va="top",
            )

    ax3.set_xlabel("Year")
    ax3.set_ylabel(f"Annualized Loss Expectancy (ALE) ({currency_symbol})")
    ax3.set_title("Year-by-Year ALE Progression")
    ax3.legend()
    ax3.grid(True)
    ax3.set_xticks(years)

    # Statistics (Bottom Right)
    final_year = len(exported_results["results"]["best_permutation"])

    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis("off")

    # Define sections of text
    scenario_text = _format_scenario_text(
        exported_results["simulation_parameters"]["asset_value"],
        final_year,
        exported_results["simulation_parameters"]["ef_range"],
        exported_results["simulation_parameters"]["aro_range"],
        exported_results["simulation_parameters"]["cost_adjustment_range"],
        currency_symbol,
    )

    controls_text = f"""You are considering the following controls: {', '.join([
    f"Control {i} (yearly cost: {currency_symbol}{cost:.2f}, reduction: {reduction * 100:.1f}%)" 
    for i, (cost, reduction) in enumerate(
        zip(
            exported_results['simulation_parameters']['control_costs'],
            exported_results['simulation_parameters']['control_reductions']
        ),
        start=1
    )
])}."""

    purpose_text = """Given these parameters, you want to know the optimal sequence of controls to implement to maximize the Return on Security Investment (ROSI) over those years. You also want to know the impact of varying the exposure factor, annual rate of occurrence, and control costs on the ROSI."""

    results_text = f"""Result: Over {NUM_SAMPLES} simulations, we find that the best-performing permutation is {', '.join(map(str, exported_results["results"]["best_permutation"]))}, with a total ROSI of {exported_results["results"]["best_rosi"]:.2f}%. The total cost over {final_year} years is {currency_symbol}{sum(exported_results["ranked_permutations"][0][f"year_{year}"]["total_cost"] for year in range(1, final_year + 1)):.2f}.
    """

    # Add year costs
    yearly_costs = ""
    for year in range(1, final_year + 1):
        yearly_costs += f"\nYear {year} Cost: {currency_symbol}{exported_results['ranked_permutations'][0][f'year_{year}']['total_cost']:.2f}"

    # Wrap text sections (adjust wrap width based on your needs)
    wrap_width = 100
    wrapped_scenario = "\n".join(wrap(scenario_text, wrap_width))
    wrapped_controls = "\n".join(wrap(controls_text, wrap_width))
    wrapped_purpose = "\n".join(wrap(purpose_text, wrap_width))
    wrapped_results = "\n".join(wrap(results_text, wrap_width))

    # Combine all sections with spacing
    full_text = f"{wrapped_scenario}\n\n{wrapped_controls}\n\n{wrapped_purpose}\n\n{wrapped_results}{yearly_costs}"

    # Position text with proper alignment and smaller font
    ax4.text(
        0.05,
        0.95,
        full_text,
        ha="left",
        va="top",
        fontsize=10,
        transform=ax4.transAxes,
        linespacing=1.5,
        bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=10),
    )

    plt.tight_layout()
    plt.savefig(output_file)


def simulate_control_sequence_optimization(
    asset_value: float,
    ef_range: list[float],
    aro_range: list[float],
    control_costs: list[float],
    cost_adjustment_range: list[float],
    control_reductions: list[float],
    num_years: int,
    kurtosis: float = KURTOSIS,
    num_samples: int = NUM_SAMPLES,
    currency_symbol: str = CURRENCY_SYMBOL,
    output_json_file: str = None,
    output_png_file: str = None,
    output_json_response: bool = False,
) -> dict | None:
    """Given a set of security controls to be implemented, with one control per year, determine the optimal control implementation sequence to maximize the Return on Security Investment (ROSI) over a specified number of years, using Randomized Quasi-Monte Carlo (RQMC) and Sobol sensitivity analysis.

    The simulation uses:
        - Sobol samples for the exposure factor, annual rate of occurrence, and cost adjustments
        - RQMC for adding randomness to the Sobol samples and averaging multiple samples per control-year
        - Beta distribution for introducing kurtosis to the exposure factor
        - Poisson distribution for simulating the annual rate of occurrence, with a specified number of decimal places to bypass the integer limitation of the distribution
        - Sobol sensitivity analysis as a global sensitivity analysis method to determine the impact of varying the exposure factor, annual rate of occurrence, and control costs on the ROSI
            - First order sensitivity index (S1) measures the impact of each parameter on the output
            - Total order sensitivity index (ST) measures the impact of each parameter, including interactions with other parameters

    The implementation performs a multivariate time series simulation to evaluate the ROSI for each year, for each permutation of controls. The simulation takes into account variability in the exposure factor, annual rate of occurrence, and control costs. The total ROSI is derived from a summation of the ROSI for all years. The simulation also performs a sensitivity analysis to determine the impact of varying the exposure factor, annual rate of occurrence, and control costs on the ROSI.

    An example scenario is as follows:
        - You have an asset value of X
        - You have 4 security controls to implement (referred to as 1, 2, 3, 4), with a base annualized cost of A, B, C, D
        - You predict the exposure factor to be between X_ef and Y_ef
        - You predict the annual rate of occurrence to be between X_aro and Y_aro
        - You predict the cost adjustment for each control to be between X_adj and Y_adj per year
        - You know the reduction in risk for each control to be applied to the annual rate of occurrence
        - You want to know the optimal sequence of controls to implement to maximize the ROSI over those years
        - You want to know the impact of varying the exposure factor, annual rate of occurrence, and control costs on the ROSI

    Args:
        asset_value: The value of the asset at risk, expressed in monetary units.
        ef_range: The range of the exposure factor, representing the percentage of the asset value that is at risk during a risk event, expressed as decimals.
        aro_range: The range of the annual rate of occurrence, representing the frequency of the risk event over a year, expressed as decimals.
        control_costs: The base annualized cost of implementing each security control, expressed in monetary units.
        cost_adjustment_range: The range of the cost adjustment for each control per year, expressed as decimals.
        control_reductions: The percentage reduction in risk for each control, expressed as decimals.
        num_years: The number of years to simulate.
        kurtosis: The kurtosis of the distribution for the exposure factor. Default is constant KURTOSIS.
        num_samples: The number of samples to generate for the simulation. Default is constant NUM_SAMPLES.
        currency_symbol: The currency symbol to use for displaying monetary values. Default is constant CURRENCY_SYMBOL.
        output_json_file: The output JSON file to save the simulation results. Default is None. Skipped if output_json_response is True.
        output_png_file: The output PNG file to save the simulation results. Default is None. Skipped if output_json_response is True.
        output_json_response: Whether to return the simulation results as a JSON response. Default is False. Overrides output_json_file and output_png_file if True.

    Returns:
        None
    """
    # Set random seed for reproducibility
    np.random.seed(RANDOM_SEED)

    # Determine if any ranges are fixed values
    is_ef_fixed = ef_range[0] == ef_range[1]
    is_aro_fixed = aro_range[0] == aro_range[1]
    is_cost_fixed = cost_adjustment_range[0] == cost_adjustment_range[1]

    # Build a list of (param_type, year_index) only for non‐fixed parameters
    param_order = []
    for i in range(num_years):
        if not is_ef_fixed:
            param_order.append(("EF", i))
    for i in range(num_years):
        if not is_aro_fixed:
            param_order.append(("ARO", i))
    for i in range(num_years):
        if not is_cost_fixed:
            param_order.append(("COST", i))

    # If param_order is empty, all parameters are fixed; fill slices with constants
    if not param_order:
        ef_slice = np.full((num_samples, num_years), ef_range[0])
        aro_slice = np.full((num_samples, num_years), aro_range[0])
        cost_adj_slice = np.full((num_samples, num_years), cost_adjustment_range[0])
    else:
        # Generate multi-dimensional Sobol samples for only the parameters that vary
        combined_parameters = {
            name: rng
            for name, rng in itertools.chain(
                ((f"EF_{i+1}", ef_range) for i in range(num_years) if not is_ef_fixed),
                (
                    (f"ARO_{i+1}", aro_range)
                    for i in range(num_years)
                    if not is_aro_fixed
                ),
                (
                    (f"cost_adj_{i+1}", cost_adjustment_range)
                    for i in range(num_years)
                    if not is_cost_fixed
                ),
            )
        }
        problem_combined = setup_sensitivity_problem(**combined_parameters)
        sobol_combined = sobol_sample.sample(
            problem_combined, num_samples, calc_second_order=False, seed=RANDOM_SEED
        )
        sobol_combined = randomize_sobol_samples(sobol_combined)
        # Keep the first num_samples rows as you are trying to broadcast (N*(D+1)) rows into N rows
        # Results in shape (num_samples, D) such that later slices will work
        sobol_combined = sobol_combined[:num_samples, :]

    # Initialize slices
    ef_slice = np.zeros((num_samples, num_years))
    aro_slice = np.zeros((num_samples, num_years))
    cost_adj_slice = np.zeros((num_samples, num_years))

    # Copy Sobol columns into slices, or fill with a fixed value
    col = 0
    for i in range(num_years):
        if is_ef_fixed:
            ef_slice[:, i] = ef_range[0]
        else:
            ef_slice[:, i] = sobol_combined[:, col]
            col += 1
    for i in range(num_years):
        if is_aro_fixed:
            aro_slice[:, i] = aro_range[0]
        else:
            aro_slice[:, i] = sobol_combined[:, col]
            col += 1
    for i in range(num_years):
        if is_cost_fixed:
            cost_adj_slice[:, i] = cost_adjustment_range[0]
        else:
            cost_adj_slice[:, i] = sobol_combined[:, col]
            col += 1

    # Simulate EF, ARO, and cost adjustments using Sobol samples
    ef_samples = simulate_exposure_factor_sobol(ef_slice, ef_range, kurtosis)
    aro_samples = simulate_annual_rate_of_occurrence_sobol(aro_slice, aro_range)
    control_cost_values = calculate_compounding_costs(
        control_costs, cost_adjustment_range, num_years, cost_adj_slice
    )

    # Determine permutations of control orderings (starting from 1 instead of 0)
    all_permutations = list(permutations(range(1, num_years + 1)))

    # List to store total ROSI values for each permutation after calculating all samples
    simulate_all_permutations = [
        calculate_statistics_for_permutation_per_year(  # You can use either calculate_statistics_for_permutation_aggregate or calculate_statistics_for_permutation_per_year
            asset_value,
            control_cost_values,
            ef_samples,
            aro_samples,
            permutation,
            control_reductions,
            num_samples,
        )
        for permutation in all_permutations
    ]

    # Sort the permutations by total ROSI descending
    sorted_permutations = sorted(
        simulate_all_permutations, key=lambda x: x["total_rosi"], reverse=True
    )
    best_permutation = sorted_permutations[0]["permutation"]
    best_rosi = sorted_permutations[0]["total_rosi"]

    # Run sensitivity analysis
    sensitivity_results, problem = perform_sensitivity_analysis(
        asset_value,
        ef_range,
        aro_range,
        cost_adjustment_range,
        control_costs,
        control_reductions,
    )

    # Initialize a results dictionary
    exported_results = {
        "simulation_parameters": {
            "asset_value": asset_value,
            "ef_range": ef_range,
            "aro_range": aro_range,
            "control_reductions": control_reductions,
            "control_costs": control_costs,
            "cost_adjustment_range": cost_adjustment_range,
            "num_samples": num_samples,
            "num_years": num_years,
            "kurtosis": kurtosis,
        },
        "results": {
            "best_permutation": best_permutation,
            "best_rosi": best_rosi,
            "control_cost_values": control_cost_values,
        },
        "ranked_permutations": sorted_permutations,
        "sensitivity_results": sensitivity_results,
    }

    # Serialize and save the results to a JSON file
    serializable_results = convert_to_serializable(exported_results)

    if output_json_response:
        return serializable_results

    if output_json_file:
        with open(output_json_file, "w") as f:
            json.dump(serializable_results, f, indent=4)

    if output_png_file:
        _plot_combined_analysis(
            sensitivity_results,
            problem,
            exported_results,
            output_png_file,
            currency_symbol,
        )

    return None
