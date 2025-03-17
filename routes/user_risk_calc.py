from fastapi import APIRouter, HTTPException, Query
from common.risk_simulator import plot_risk_calculation_before_after
from common.rqmc_sobol_sensitivity_analysis import simulate_control_sequence_optimization

router = APIRouter()


@router.get("/before-after")
async def get_risk_calculation_before_after(
    asset_value: float = Query(gt=0, description="The value of the asset at risk"),
    exposure_factor: float = Query(ge=0, le=1, description="The exposure factor (0-1)"),
    annual_rate_of_occurrence: float = Query(
        gt=0, description="Annual rate of occurrence"
    ),
    percentage_reduction: float = Query(
        le=99, description="Percentage reduction (0-99)"
    ),
    cost_of_control: float = Query(gt=0, description="Cost of implementing controls"),
    simulation_method: int = Query(
        default=0,
        ge=0,
        le=1,
        description="Simulation method: 0 for Monte Carlo, 1 for Markov Chain Monte Carlo",
    ),
) -> dict:
    """Get the before and after risk calculation plots.

    Args:
        asset_value: Must be greater than 0.
        exposure_factor: Must be between 0 and 1.
        annual_rate_of_occurrence: Must be greater than 0.
        percentage_reduction: Must be less than or equal to 99.
        cost_of_control: Must be greater than 0.
        simulation_method: Must be 0 (Monte Carlo) or 1 (Markov Chain Monte Carlo).

    Returns:
        dict: Risk calculation results including statistics and simulation data.

    Raises:
        422 Unprocessable Entity: If input validation fails.
        500 Internal Server Error: If calculation process fails.
    """
    try:
        result = plot_risk_calculation_before_after(
            asset_value=asset_value,
            exposure_factor=exposure_factor,
            annual_rate_of_occurrence=annual_rate_of_occurrence,
            reduction_percentage=percentage_reduction,
            cost_of_controls=cost_of_control,
            output_json_response=True,
            simulation_method=simulation_method,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rqmc-sequence-analysis")
async def get_rqmc_control_sequence_analysis(
    asset_value: float = Query(gt=0, description="The value of the asset at risk"),
    exposure_factor_min: float = Query(ge=0, le=1, description="Minimum exposure factor (0-1)"),
    exposure_factor_max: float = Query(ge=0, le=1, description="Maximum exposure factor (0-1)"),
    annual_rate_of_occurrence_min: float = Query(gt=0, description="Minimum annual rate of occurrence"),
    annual_rate_of_occurrence_max: float = Query(gt=0, description="Maximum annual rate of occurrence"),
    cost_adjustment_min: float = Query(ge=-1, le=1, description="Minimum cost adjustment in decimal form (-1 to 1)"),
    cost_adjustment_max: float = Query(ge=-1, le=1, description="Maximum cost adjustment in decimal form (-1 to 1)"),
    control_reductions: list[float] = Query(description="List of control reduction decimals (0-0.99)"),
    control_costs: list[float] = Query(description="List of control costs (must be > 0)"),
) -> dict:
    """Given known asset values but uncertain exposure factors, annual rates of occurrence, control effectiveness, and control costs, determine the optimal sequence of controls to implement.

    Args:
        asset_value: Must be greater than 0.
        exposure_factor_min: Must be between 0 and 1.
        exposure_factor_max: Must be between 0 and 1.
        annual_rate_of_occurrence_min: Must be greater than 0.
        annual_rate_of_occurrence_max: Must be greater than 0.
        cost_adjustment_min: Must be between -1 and 1.
        cost_adjustment_max: Must be between -1 and 1.
        control_reductions: List of control reduction decimals (0-0.99).
        control_costs: List of control costs (must be > 0).

    Returns:
        dict: Simulation results including optimal sequence and sensitivity analysis.

    Raises:
        422 Unprocessable Entity: If input validation fails.
        500 Internal Server Error: If simulation process fails.
    """
    try:
        # Validate lists have same length and are not empty
        if len(control_reductions) != len(control_costs):
            raise ValueError("Control reductions and costs lists must have the same length")
        if not control_reductions:
            raise ValueError("At least one control must be provided")

        # Validate control reductions and costs
        for reduction in control_reductions:
            if not 0 <= reduction <= 0.99:
                raise ValueError("Control reductions must be between 0 and 0.99")
        for cost in control_costs:
            if cost <= 0:
                raise ValueError("Control costs must be greater than 0")

        # Do not attempt to reduce the num_samples as the RQMC method requires a large number of samples
        # Insufficient samples will result in failed calculations
        result = simulate_control_sequence_optimization(
            asset_value=asset_value,
            ef_range=[exposure_factor_min, exposure_factor_max],
            aro_range=[annual_rate_of_occurrence_min, annual_rate_of_occurrence_max],
            control_costs=control_costs,
            cost_adjustment_range=[cost_adjustment_min, cost_adjustment_max],
            control_reductions=control_reductions,
            num_years=len(control_costs),
            output_json_response=True,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rqmc-vendor-assessment")
async def get_rqmc_vendor_assessment(
    asset_value: float = Query(gt=0, description="The value of the asset at risk"),
    exposure_factor_min: float = Query(ge=0, le=1, description="Minimum exposure factor (0-1)"),
    exposure_factor_max: float = Query(ge=0, le=1, description="Maximum exposure factor (0-1)"),
    annual_rate_of_occurrence_min: float = Query(gt=0, description="Minimum annual rate of occurrence"),
    annual_rate_of_occurrence_max: float = Query(gt=0, description="Maximum annual rate of occurrence"),
    control_costs: list[float] = Query(
        description="List of control costs (must be > 0)",
    ),
    control_reduction_mins: list[float] = Query(
        description="List of minimum control reduction decimals (0-0.99)",
    ),
    control_reduction_maxs: list[float] = Query(
        description="List of maximum control reduction decimals (0-0.99)",
    ),
) -> dict:
    """Vendor assessment simulation endpoint."""
    try:
        # Validate lists have same length and are not empty
        if not (len(control_costs) == len(control_reduction_mins) == len(control_reduction_maxs)):
            raise ValueError("Control costs and reduction lists must have the same length")
        if not control_costs:
            raise ValueError("At least one control must be provided")

        # Validate ranges
        if exposure_factor_min > exposure_factor_max:
            raise ValueError("Exposure factor minimum must be less than or equal to maximum")
        if annual_rate_of_occurrence_min > annual_rate_of_occurrence_max:
            raise ValueError("Annual rate of occurrence minimum must be less than or equal to maximum")

        # Validate control reductions and costs with detailed messages
        for i, (min_red, max_red) in enumerate(zip(control_reduction_mins, control_reduction_maxs), 1):
            if not 0 <= min_red <= max_red <= 0.99:
                raise ValueError(
                    f"Control {i} reduction range invalid: min({min_red}) must be <= max({max_red}) "
                    "and both must be between 0 and 0.99"
                )
        for i, cost in enumerate(control_costs, 1):
            if cost <= 0:
                raise ValueError(f"Control {i} cost must be greater than 0, got: {cost}")

        # Create control reduction ranges list correctly
        control_reduction_ranges = [
            [min_red, max_red] 
            for min_red, max_red in zip(control_reduction_mins, control_reduction_maxs)
        ]

        from common.rqmc_vendor_assessment import simulate_vendor_assessment_decision
        result = simulate_vendor_assessment_decision(
            asset_value=asset_value,
            ef_range=[exposure_factor_min, exposure_factor_max],
            aro_range=[annual_rate_of_occurrence_min, annual_rate_of_occurrence_max],
            control_costs=control_costs,
            control_reduction_ranges=control_reduction_ranges,
            num_vendors=len(control_costs),
            output_json_response=True,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
